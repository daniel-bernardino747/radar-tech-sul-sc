"""As três partes do trabalho do Radar, em ritmos diferentes (ADR 0003):

- atender: conversas com o bot (Revisor e Sugestões), ao vivo
- coletar: leitura das Fontes, duas vezes por dia
- divulgar: Lembretes e Agenda da semana, checados a cada minuto
"""

import sys
import traceback
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from enum import Enum, auto
from html import escape

import httpx

from radar import divulgacao, revisao
from radar.dominio import Anuncio, Evento, ItemFila, aplicar, eh_elegivel, mesmo_evento, plausivel, sanear
from radar.estado import Estado
from radar.fontes import Fonte
from radar.fontes.links import ler_link
from radar.post import texto_mudanca, texto_post
from radar.revisao import Limites, Saidas, Sugestao, avisar
from radar.telegram import ErroTelegram

RETENCAO = timedelta(days=30)

LerLink = Callable[[httpx.Client, str, str], Anuncio | None]


class Destino(Enum):
    PUBLICACAO = auto()
    FILA = auto()
    JA_NO_RADAR = auto()
    JA_NA_FILA = auto()
    REJEITADO_ANTES = auto()
    INELEGIVEL = auto()
    IMPLAUSIVEL = auto()


def executar(
    fontes: Iterable[Fonte],
    http: httpx.Client,
    saidas: Saidas,
    estado: Estado,
    agora: datetime,
    ler: LerLink = ler_link,
) -> list[str]:
    """As três partes em sequência, uma vez. Devolve os ids das Fontes que falharam."""
    atender(estado, http, saidas, agora, Limites(), ler)
    falhas = coletar(fontes, http, saidas, estado, agora)
    divulgar(estado, saidas, agora)
    return falhas


def atender(
    estado: Estado,
    http: httpx.Client,
    saidas: Saidas,
    agora: datetime,
    limites: Limites,
    ler: LerLink = ler_link,
    espera: int = 0,
) -> None:
    """Processa o que chegou na conversa com o bot; `espera` segura a conexão aguardando mensagens."""
    sugestoes = revisao.processar_conversas(estado, saidas, agora, limites, espera)
    # Grava o ponteiro antes de abrir qualquer link: se um link derrubar o processo, a
    # mesma mensagem não volta a ser processada no reinício.
    saidas.persistir()
    for sugestao in sugestoes:
        try:
            receber_sugestao(estado, sugestao, http, saidas, agora, ler)
        except Exception:
            traceback.print_exc()
            avisar(saidas, sugestao.chat_id, "Não consegui processar esse link.")
    _encaminhar(estado, saidas, agora)


def coletar(fontes: Iterable[Fonte], http: httpx.Client, saidas: Saidas, estado: Estado, agora: datetime) -> list[str]:
    falhas = []
    for fonte in fontes:
        try:
            anuncios = list(fonte.coletar(http, agora))
        except Exception as erro:  # uma Fonte quebrada não derruba as outras
            print(f"Fonte {fonte.id} falhou: {erro!r}", file=sys.stderr)
            falhas.append(fonte.id)
            continue
        for anuncio in anuncios:
            consolidar(estado, anuncio, fonte.confiavel, saidas, agora)
    _encaminhar(estado, saidas, agora)
    return falhas


def divulgar(estado: Estado, saidas: Saidas, agora: datetime) -> None:
    divulgacao.enviar_lembretes(estado, saidas.canal, agora, saidas.persistir)
    divulgacao.publicar_agenda(estado, saidas.canal, agora, saidas.persistir)
    esquecer_antigos(estado, agora)


def _encaminhar(estado: Estado, saidas: Saidas, agora: datetime) -> None:
    """Publica o que foi aprovado e leva ao Revisor o que entrou na Fila."""
    publicar_pendentes(estado, saidas, agora)
    revisao.expirar(estado, agora, saidas)
    revisao.pedir_revisoes(estado, saidas)


def consolidar(
    estado: Estado,
    a: Anuncio,
    confiavel: bool,
    saidas: Saidas,
    agora: datetime,
    sugerido_por: int | None = None,
    pode_alterar: bool = True,
) -> Destino:
    """Leva o Anúncio ao lugar certo. `pode_alterar=False` (Sugestões de terceiros) impede que
    ele mude um Evento já publicado ou na Fila: senão qualquer um cancelaria um Post."""
    a = sanear(a)
    if not plausivel(a, agora):
        return Destino.IMPLAUSIVEL

    if existente := next((e for e in estado.eventos if mesmo_evento(a, e)), None):
        if pode_alterar:
            _atualizar(existente, a, saidas)
        return Destino.JA_NO_RADAR

    na_fila = next((i for i in estado.fila if mesmo_evento(a, i.evento)), None)
    if na_fila and confiavel and not a.cancelado:
        # Uma Fonte confiável confirmou o que estava esperando revisão.
        estado.fila.remove(na_fila)
        revisao.concluir(na_fila, "☑️ Publicado automaticamente: veio de uma Fonte confiável", saidas)
        evento = Evento.de_anuncio(a)
        evento.urls += [u for u in na_fila.evento.urls if u not in evento.urls]
        estado.eventos.append(evento)
        return Destino.PUBLICACAO
    if na_fila:
        if pode_alterar:
            aplicar(na_fila.evento, a)
        return Destino.JA_NA_FILA

    if any(mesmo_evento(a, r) for r in estado.rejeitados):
        return Destino.REJEITADO_ANTES
    if not eh_elegivel(a) or a.cancelado:
        return Destino.INELEGIVEL
    if confiavel:
        estado.eventos.append(Evento.de_anuncio(a))
        return Destino.PUBLICACAO
    estado.fila.append(ItemFila(Evento.de_anuncio(a), sugerido_por=sugerido_por))
    return Destino.FILA


def _atualizar(existente: Evento, a: Anuncio, saidas: Saidas) -> None:
    mudanca = aplicar(existente, a)
    if existente.post_id is None or not mudanca.houve:
        return
    try:
        saidas.canal.editar(existente.post_id, texto_post(existente))
        if mudanca.relevantes or mudanca.cancelou:
            saidas.canal.publicar(texto_mudanca(existente, mudanca), resposta_a=existente.post_id)
    except ErroTelegram as erro:
        print(f"Atualização do Post de {existente.id} falhou: {erro}", file=sys.stderr)
    saidas.persistir()


RESPOSTAS = {
    Destino.PUBLICACAO: "✅ Publicado no canal. Obrigado!",
    Destino.FILA: "Recebido! Vai passar pela revisão antes de ir para o canal.",
    Destino.JA_NO_RADAR: "Esse evento já está no Radar. Obrigado!",
    Destino.JA_NA_FILA: "Esse evento já está esperando revisão. Obrigado!",
    Destino.REJEITADO_ANTES: "Esse evento já foi avaliado e não entrou no Radar.",
    Destino.IMPLAUSIVEL: "Os dados desse link parecem inválidos (datas ou tamanho fora do normal).",
}


def receber_sugestao(
    estado: Estado, s: Sugestao, http: httpx.Client, saidas: Saidas, agora: datetime, ler: LerLink
) -> None:
    anuncio = ler(http, s.url, "sugestao")
    if anuncio is None:
        avisar(saidas, s.chat_id, "Não consegui ler esse link automaticamente (só leio Sympla, Meetup, Even3 "
                                  "e Supertixs). Vou repassar para o Revisor.")
        if saidas.revisor_id is not None and s.chat_id != saidas.revisor_id:
            avisar(saidas, saidas.revisor_id, f"💡 Sugestão que não consegui ler: {escape(s.url)}")
        return
    if (anuncio.fim or anuncio.inicio) < agora:
        avisar(saidas, s.chat_id, "Esse evento já aconteceu.")
        return

    # Sugestão do próprio Revisor dispensa revisão e pode corrigir Eventos; a de terceiros, não.
    do_revisor = s.chat_id == saidas.revisor_id
    destino = consolidar(estado, anuncio, do_revisor, saidas, agora, sugerido_por=s.chat_id, pode_alterar=do_revisor)
    if destino is Destino.INELEGIVEL:
        resposta = _motivo_inelegivel(anuncio)
    else:
        resposta = RESPOSTAS[destino]
    avisar(saidas, s.chat_id, resposta)


def _motivo_inelegivel(a: Anuncio) -> str:
    if a.cancelado:
        return "Esse evento está cancelado."
    if a.curso:
        return "Cursos e treinamentos pagos não entram no Radar."
    return "O Radar só divulga eventos no Sul de SC (AMREC, AMUREL e AMESC) ou online."


def publicar_pendentes(estado: Estado, saidas: Saidas, agora: datetime) -> None:
    for e in sorted(estado.eventos, key=lambda e: e.inicio):
        if e.post_id is None:
            try:
                e.post_id = saidas.canal.publicar(texto_post(e))
            except ErroTelegram as erro:  # um Evento problemático não trava os outros
                print(f"Post de {e.id} falhou: {erro}", file=sys.stderr)
                continue
            e.publicado_em = agora
            saidas.persistir()


def esquecer_antigos(estado: Estado, agora: datetime) -> None:
    def vigente(e: Evento) -> bool:
        return (e.fim or e.inicio) > agora - RETENCAO

    estado.eventos = [e for e in estado.eventos if vigente(e)]
    estado.rejeitados = [e for e in estado.rejeitados if vigente(e)]
