"""Anúncio, Evento e as regras que ligam um ao outro. Termos em CONTEXT.md."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from radar.regiao import eh_da_regiao, normalizar

FUSO = ZoneInfo("America/Sao_Paulo")
GRATUITO = "Gratuito"


class Status(StrEnum):
    AGENDADO = "agendado"
    ALTERADO = "alterado"
    CANCELADO = "cancelado"


@dataclass(frozen=True)
class Anuncio:
    """O que uma Fonte publica sobre um Evento."""

    fonte: str
    url: str
    titulo: str
    inicio: datetime
    fim: datetime | None = None
    tem_horario: bool = True
    local: str | None = None
    cidade: str | None = None
    online: bool = False
    organizador: str | None = None
    preco: str | None = None
    link_inscricao: str | None = None
    cancelado: bool = False
    curso: bool = False  # é um curso/treinamento, pago ou não; só o gratuito é Evento


@dataclass
class Evento:
    id: str
    titulo: str
    inicio: datetime
    fim: datetime | None
    tem_horario: bool
    local: str | None
    cidade: str | None
    online: bool
    organizador: str | None
    preco: str | None
    link_inscricao: str | None
    urls: list[str] = field(default_factory=list)
    status: Status = Status.AGENDADO
    post_id: int | None = None
    publicado_em: datetime | None = None
    lembrete_enviado: bool = False
    curso: bool = False
    tentativas_de_post: int = 0

    @classmethod
    def de_anuncio(cls, a: Anuncio) -> Evento:
        return cls(
            id=hashlib.sha1(a.url.encode()).hexdigest()[:12],
            titulo=a.titulo,
            inicio=a.inicio,
            fim=a.fim,
            tem_horario=a.tem_horario,
            local=a.local,
            cidade=a.cidade,
            online=a.online,
            organizador=a.organizador,
            preco=a.preco,
            link_inscricao=a.link_inscricao or a.url,
            urls=[a.url],
            curso=a.curso,
            status=Status.CANCELADO if a.cancelado else Status.AGENDADO,
        )

    @property
    def link(self) -> str:
        return self.link_inscricao or self.urls[0]


@dataclass
class ItemFila:
    """Um Evento de Fonte aberta ou Sugestão aguardando o Revisor."""

    evento: Evento
    mensagem_id: int | None = None  # a mensagem com os botões, na conversa do Revisor
    sugerido_por: int | None = None  # conversa de quem mandou a Sugestão


# Anúncios podem vir de páginas de qualquer um (Sugestões): textos são cortados para
# caber nas mensagens do Telegram (limite de 4096 caracteres) e dados absurdos, recusados.
LIMITES_DE_TEXTO = {"titulo": 200, "local": 120, "cidade": 60, "organizador": 120, "preco": 40}
MAX_URL = 500
HORIZONTE = timedelta(days=365)


def sanear(a: Anuncio) -> Anuncio:
    return replace(a, **{campo: _cortar(getattr(a, campo), n) for campo, n in LIMITES_DE_TEXTO.items()})


def _cortar(texto: str | None, limite: int) -> str | None:
    if texto is None or len(texto) <= limite:
        return texto
    return texto[: limite - 1] + "…"


def plausivel(a: Anuncio, agora: datetime) -> bool:
    """Datas dentro de um ano e URLs de tamanho razoável."""
    return (
        len(a.url) <= MAX_URL
        and len(a.link_inscricao or "") <= MAX_URL
        and a.inicio <= agora + HORIZONTE
        and (a.fim is None or a.inicio <= a.fim <= a.inicio + HORIZONTE)
    )


def eh_elegivel(a: Anuncio) -> bool:
    """Não é Curso (curso só entra se gratuito) e é presencial na Região ou online.

    Se um Evento online é de Organizador regional, quem garante é a Fonte confiável
    ou o Revisor.
    """
    return (not a.curso or a.preco == GRATUITO) and (a.online or eh_da_regiao(a.cidade))


def mesmo_evento(a: Anuncio, e: Evento) -> bool:
    """Mesma data, mesmo local e horários sobrepostos. Na dúvida, não junta."""
    if a.url in e.urls:
        return True
    if not (a.tem_horario and e.tem_horario):
        return False
    if a.inicio.astimezone(FUSO).date() != e.inicio.astimezone(FUSO).date():
        return False
    if not _mesmo_local(a, e):
        return False
    return _sobrepoe(a.inicio, a.fim, e.inicio, e.fim)


def _mesmo_local(a: Anuncio, e: Evento) -> bool:
    if a.online or e.online:
        return a.online and e.online
    if not (a.cidade and e.cidade and a.local and e.local):
        return False
    if normalizar(a.cidade) != normalizar(e.cidade):
        return False
    return _semelhantes(a.local, e.local)


_IRRELEVANTES = {"de", "da", "do", "das", "dos", "e", "centro", "sc"}


def _semelhantes(x: str, y: str) -> bool:
    """Metade ou mais das palavras do nome mais curto aparece no outro."""
    px = {p for p in normalizar(x).split() if p not in _IRRELEVANTES}
    py = {p for p in normalizar(y).split() if p not in _IRRELEVANTES}
    menor = min(len(px), len(py))
    return menor > 0 and len(px & py) / menor >= 0.5


def _sobrepoe(i1: datetime, f1: datetime | None, i2: datetime, f2: datetime | None) -> bool:
    f1 = f1 or i1
    f2 = f2 or i2
    return i1 <= f2 and i2 <= f1


# O que muda no Evento quando um Anúncio dele muda.
MUDANCA_RELEVANTE = ("inicio", "fim", "local", "cidade", "online")
MUDANCA_DETALHE = ("titulo", "organizador", "preco", "link_inscricao")


@dataclass(frozen=True)
class Mudanca:
    relevantes: tuple[str, ...]
    detalhes: tuple[str, ...]
    cancelou: bool

    @property
    def houve(self) -> bool:
        return bool(self.relevantes or self.detalhes or self.cancelou)


def aplicar(e: Evento, a: Anuncio) -> Mudanca:
    """Atualiza o Evento com um Anúncio que já é dele e diz o que mudou.

    Só o Anúncio que originou o Evento (primeira URL) pode alterar data e local;
    os demais apenas preenchem campos vazios.
    """
    if a.url not in e.urls:
        e.urls.append(a.url)

    if e.status is Status.CANCELADO:
        return Mudanca((), (), False)

    if a.url != e.urls[0]:
        for campo in MUDANCA_RELEVANTE + MUDANCA_DETALHE:
            if getattr(e, campo) in (None, False) and getattr(a, campo) not in (None, False):
                setattr(e, campo, getattr(a, campo))
        return Mudanca((), (), False)

    if a.cancelado:
        e.status = Status.CANCELADO
        return Mudanca((), (), True)

    relevantes = tuple(c for c in MUDANCA_RELEVANTE if getattr(a, c) != getattr(e, c))
    novo_link = a.link_inscricao or a.url
    detalhes = tuple(
        c for c in MUDANCA_DETALHE
        if (novo_link if c == "link_inscricao" else getattr(a, c)) != getattr(e, c)
    )
    for c in relevantes + detalhes:
        setattr(e, c, novo_link if c == "link_inscricao" else getattr(a, c))
    e.tem_horario = a.tem_horario
    if relevantes:
        e.status = Status.ALTERADO
        e.lembrete_enviado = False
    return Mudanca(relevantes, detalhes, False)


__all__ = [
    "Anuncio", "Evento", "ItemFila", "Mudanca", "plausivel", "sanear", "Status", "aplicar", "eh_elegivel", "mesmo_evento",
]
