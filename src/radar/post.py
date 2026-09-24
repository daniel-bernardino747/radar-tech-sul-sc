"""Texto dos Posts e das mensagens de alteração, em HTML do Telegram."""

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from radar.dominio import Evento, Mudanca, Status

FUSO = ZoneInfo("America/Sao_Paulo")
DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def texto_post(e: Evento) -> str:
    titulo = f"<b>{escape(e.titulo)}</b>"
    if e.status is Status.CANCELADO:
        titulo = f"❌ <b>CANCELADO</b>\n<s>{escape(e.titulo)}</s>"
    linhas = [titulo, "", f"📅 {quando(e)}", f"📍 {onde(e)}"]
    if e.organizador:
        linhas.append(f"👥 {escape(e.organizador)}")
    if e.curso:
        linhas.append("🎓 Curso gratuito")
    elif e.preco:
        linhas.append(f"💰 {escape(e.preco)}")
    linhas.append(f'🔗 <a href="{escape(e.link, quote=True)}">Inscrição</a>')
    return "\n".join(linhas)


def texto_mudanca(e: Evento, m: Mudanca) -> str:
    if m.cancelou:
        return f"❌ Evento cancelado: <b>{escape(e.titulo)}</b>"
    partes = []
    if {"inicio", "fim"} & set(m.relevantes):
        partes.append(f"📅 Nova data: {quando(e)}")
    if {"local", "cidade", "online"} & set(m.relevantes):
        partes.append(f"📍 Novo local: {onde(e)}")
    return "⚠️ Evento alterado\n" + "\n".join(partes)


def quando(e: Evento) -> str:
    inicio = e.inicio.astimezone(FUSO)
    fim = e.fim.astimezone(FUSO) if e.fim else None
    texto = _dia(inicio)
    if fim and fim.date() != inicio.date():
        texto += f" a {_dia(fim)}"
    if e.tem_horario:
        texto += f" · {inicio:%H:%M}"
        if fim and fim.date() == inicio.date() and fim != inicio:
            texto += f"–{fim:%H:%M}"
    return texto


def onde(e: Evento) -> str:
    if e.online:
        return "Online"
    partes = [p for p in (e.local, e.cidade) if p]
    return escape(", ".join(partes)) if partes else "Local a confirmar"


def _dia(d: datetime) -> str:
    return f"{DIAS[d.weekday()]}, {d:%d/%m}"
