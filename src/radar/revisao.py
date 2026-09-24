"""Fila de revisão: pedidos ao Revisor, Aprovação, Rejeição e expiração."""

import re
from dataclasses import dataclass
from datetime import datetime
from html import escape

from radar.dominio import ItemFila
from radar.estado import Estado
from radar.post import texto_post
from radar.telegram import Canal, Conversa

BOAS_VINDAS = (
    "Oi! Eu sou o Radar Tech Sul SC.\n\n"
    "Viu um evento de tecnologia no Sul de SC que não apareceu no canal? "
    "Me mande o link (Sympla, Meetup, Even3...) que ele passa pela revisão.\n\n"
    "Seu id no Telegram: <code>{id}</code>"
)

_URL = re.compile(r"https?://\S+")


@dataclass
class Saidas:
    canal: Canal
    conversa: Conversa
    revisor_id: int | None


@dataclass(frozen=True)
class Sugestao:
    chat_id: int
    url: str


def processar_conversas(estado: Estado, saidas: Saidas) -> list[Sugestao]:
    """Aplica os cliques do Revisor e devolve os links recebidos como Sugestão."""
    sugestoes = []
    for update in saidas.conversa.atualizacoes(estado.offset_telegram):
        estado.offset_telegram = update["update_id"] + 1
        if clique := update.get("callback_query"):
            _decidir(estado, clique, saidas)
        elif (msg := update.get("message")) and msg["chat"]["type"] == "private":
            urls = _URL.findall(msg.get("text") or msg.get("caption") or "")
            if urls:
                sugestoes += [Sugestao(msg["chat"]["id"], u.rstrip(").,")) for u in urls]
            else:
                saidas.conversa.responder(msg["chat"]["id"], BOAS_VINDAS.format(id=msg["from"]["id"]))
    return sugestoes


def _decidir(estado: Estado, clique: dict, saidas: Saidas) -> None:
    acao, _, item_id = clique.get("data", "").partition(":")
    if clique["from"]["id"] != saidas.revisor_id:
        saidas.conversa.confirmar_clique(clique["id"], "Só o Revisor pode decidir.")
        return
    item = next((i for i in estado.fila if i.evento.id == item_id), None)
    if item is None:
        saidas.conversa.confirmar_clique(clique["id"], "Esse item já saiu da Fila.")
        return

    estado.fila.remove(item)
    if acao == "aprovar":
        estado.eventos.append(item.evento)
        concluir(item, "✅ Aprovado", saidas)
        saidas.conversa.confirmar_clique(clique["id"], "Aprovado")
        if item.sugerido_por and item.sugerido_por != saidas.revisor_id:
            saidas.conversa.responder(item.sugerido_por, f"✅ Sua sugestão entrou no Radar: {item.evento.titulo}")
    else:
        estado.rejeitados.append(item.evento)
        concluir(item, "❌ Rejeitado", saidas)
        saidas.conversa.confirmar_clique(clique["id"], "Rejeitado")


def pedir_revisoes(estado: Estado, saidas: Saidas) -> None:
    if saidas.revisor_id is None:
        return
    for item in estado.fila:
        if item.mensagem_id is None:
            item.mensagem_id = saidas.conversa.pedir_revisao(saidas.revisor_id, texto_revisao(item), item.evento.id)


def expirar(estado: Estado, agora: datetime, saidas: Saidas) -> None:
    for item in [i for i in estado.fila if (i.evento.fim or i.evento.inicio) < agora]:
        estado.fila.remove(item)
        concluir(item, "⌛ Expirou sem revisão", saidas)


def concluir(item: ItemFila, desfecho: str, saidas: Saidas) -> None:
    if item.mensagem_id is not None and saidas.revisor_id is not None:
        saidas.conversa.concluir_revisao(saidas.revisor_id, item.mensagem_id, f"{texto_revisao(item)}\n\n{desfecho}")


def texto_revisao(item: ItemFila) -> str:
    origem = "💡 Sugestão enviada ao bot" if item.sugerido_por else "🔎 Fonte aberta"
    fontes = "\n".join(escape(u) for u in item.evento.urls)
    return f"{texto_post(item.evento)}\n\n{origem}\n{fontes}"
