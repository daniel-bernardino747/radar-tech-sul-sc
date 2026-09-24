"""Fila de revisão e conversa com o bot: pedidos ao Revisor, Aprovação, Rejeição, expiração
e recebimento de Sugestões.

Qualquer pessoa pode falar com o bot, então tudo aqui assume entrada hostil: limites por
pessoa, texto sempre escapado e falha de um envio isolada das demais.
"""

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from html import escape

from radar.dominio import ItemFila
from radar.estado import Estado
from radar.post import texto_post
from radar.telegram import Canal, Conversa, ErroTelegram

BOAS_VINDAS = (
    "Oi! Eu sou o Radar Tech Sul SC.\n\n"
    "Viu um evento de tecnologia no Sul de SC que não apareceu no canal? "
    "Me mande o link (Sympla, Meetup, Even3 ou Supertixs) que ele passa pela revisão.\n\n"
    "Seu id no Telegram: <code>{id}</code>"
)
MAX_LINKS_POR_MENSAGEM = 3
SUGESTOES_POR_HORA = 5

_URL = re.compile(r"https?://\S+")


@dataclass
class Saidas:
    canal: Canal
    conversa: Conversa
    revisor_id: int | None
    # Chamado logo após cada envio que muda o estado (Post, pedido de revisão, ponteiro de
    # mensagens), para que um processo derrubado no meio não repita envios ao voltar.
    persistir: Callable[[], None] = field(default=lambda: None)


@dataclass(frozen=True)
class Sugestao:
    chat_id: int
    url: str


class Cota:
    """Quantas vezes cada pessoa pode fazer algo por hora. Vive só na memória."""

    def __init__(self, por_hora: int):
        self.por_hora = por_hora
        self._usos: dict[int, list[datetime]] = {}

    def permite(self, chat_id: int, agora: datetime) -> bool:
        recentes = [t for t in self._usos.get(chat_id, []) if agora - t < timedelta(hours=1)]
        self._usos[chat_id] = recentes
        if len(recentes) >= self.por_hora:
            return False
        recentes.append(agora)
        return True


@dataclass
class Limites:
    sugestoes: Cota = field(default_factory=lambda: Cota(SUGESTOES_POR_HORA))
    avisos: Cota = field(default_factory=lambda: Cota(1))  # "você mandou demais" e boas-vindas


def processar_conversas(
    estado: Estado, saidas: Saidas, agora: datetime, limites: Limites, espera: int = 0
) -> list[Sugestao]:
    """Aplica os cliques do Revisor e devolve os links recebidos como Sugestão."""
    sugestoes = []
    for update in saidas.conversa.atualizacoes(estado.offset_telegram, espera):
        estado.offset_telegram = update["update_id"] + 1
        if clique := update.get("callback_query"):
            _decidir(estado, clique, saidas)
        elif (msg := update.get("message")) and msg.get("chat", {}).get("type") == "private":
            sugestoes += _ler_mensagem(msg, saidas, agora, limites)
    return sugestoes


def _ler_mensagem(msg: dict, saidas: Saidas, agora: datetime, limites: Limites) -> list[Sugestao]:
    chat_id = msg["chat"]["id"]
    urls = [u.rstrip(").,") for u in _URL.findall(msg.get("text") or msg.get("caption") or "")]
    eh_revisor = chat_id == saidas.revisor_id
    if not urls:
        if eh_revisor or limites.avisos.permite(chat_id, agora):
            avisar(saidas, chat_id, BOAS_VINDAS.format(id=msg.get("from", {}).get("id", chat_id)))
        return []
    if eh_revisor:
        return [Sugestao(chat_id, u) for u in urls]
    aceitas = []
    for url in urls[:MAX_LINKS_POR_MENSAGEM]:
        if not limites.sugestoes.permite(chat_id, agora):
            if limites.avisos.permite(chat_id, agora):
                avisar(saidas, chat_id, "Recebi muitas sugestões suas na última hora. Tente de novo mais tarde.")
            break
        aceitas.append(Sugestao(chat_id, url))
    if len(urls) > MAX_LINKS_POR_MENSAGEM and aceitas:
        avisar(saidas, chat_id, f"Li só os {MAX_LINKS_POR_MENSAGEM} primeiros links da sua mensagem.")
    return aceitas


def _decidir(estado: Estado, clique: dict, saidas: Saidas) -> None:
    acao, _, item_id = str(clique.get("data", "")).partition(":")
    confirmar = lambda texto: _tentar(saidas.conversa.confirmar_clique, clique["id"], texto)  # noqa: E731
    if clique.get("from", {}).get("id") != saidas.revisor_id:
        confirmar("Só o Revisor pode decidir.")
        return
    item = next((i for i in estado.fila if i.evento.id == item_id), None)
    if item is None:
        confirmar("Esse item já saiu da Fila.")
        return

    estado.fila.remove(item)
    if acao == "aprovar":
        estado.eventos.append(item.evento)
        concluir(item, "✅ Aprovado", saidas)
        confirmar("Aprovado")
        if item.sugerido_por and item.sugerido_por != saidas.revisor_id:
            avisar(saidas, item.sugerido_por, f"✅ Sua sugestão entrou no Radar: {escape(item.evento.titulo)}")
    else:
        estado.rejeitados.append(item.evento)
        concluir(item, "❌ Rejeitado", saidas)
        confirmar("Rejeitado")


def pedir_revisoes(estado: Estado, saidas: Saidas) -> None:
    if saidas.revisor_id is None:
        return
    for item in estado.fila:
        if item.mensagem_id is None:
            try:
                item.mensagem_id = saidas.conversa.pedir_revisao(saidas.revisor_id, texto_revisao(item), item.evento.id)
            except ErroTelegram as erro:  # um item problemático não trava os outros
                print(f"Pedido de revisão de {item.evento.id} falhou: {erro}", file=sys.stderr)
                continue
            saidas.persistir()


def expirar(estado: Estado, agora: datetime, saidas: Saidas) -> None:
    for item in [i for i in estado.fila if (i.evento.fim or i.evento.inicio) < agora]:
        estado.fila.remove(item)
        concluir(item, "⌛ Expirou sem revisão", saidas)


def concluir(item: ItemFila, desfecho: str, saidas: Saidas) -> None:
    if item.mensagem_id is not None and saidas.revisor_id is not None:
        _tentar(saidas.conversa.concluir_revisao, saidas.revisor_id, item.mensagem_id,
                f"{texto_revisao(item)}\n\n{desfecho}")


def texto_revisao(item: ItemFila) -> str:
    origem = "💡 Sugestão enviada ao bot" if item.sugerido_por else "🔎 Fonte aberta"
    fontes = "\n".join(escape(u) for u in item.evento.urls)
    return f"{texto_post(item.evento)}\n\n{origem}\n{fontes}"


def avisar(saidas: Saidas, chat_id: int, texto: str) -> None:
    """Mensagem de cortesia: se falhar (usuário bloqueou o bot, limite do Telegram), segue."""
    _tentar(saidas.conversa.responder, chat_id, texto)


def _tentar(envio: Callable, *args) -> None:
    try:
        envio(*args)
    except ErroTelegram as erro:
        print(f"Envio ignorado: {erro}", file=sys.stderr)
