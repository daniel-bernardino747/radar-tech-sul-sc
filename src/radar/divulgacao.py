"""Lembretes e Agenda da semana, derivados dos Eventos já publicados."""

from datetime import date, datetime, time, timedelta
from html import escape

from radar.dominio import FUSO, Evento, Status
from radar.estado import Estado
from radar.post import quando
from radar.telegram import Canal

HORA_DO_LEMBRETE = time(10)
HORA_DA_AGENDA = time(8)
ANTECEDENCIA_MINIMA = timedelta(hours=48)  # Post mais recente que isso já faz as vezes de Lembrete
SEGUNDA = 0


def dia_do_lembrete(e: Evento) -> date:
    """Véspera do Evento; para Eventos de segunda, a sexta anterior."""
    dia = e.inicio.astimezone(FUSO).date()
    return dia - timedelta(days=3 if dia.weekday() == SEGUNDA else 1)


def precisa_de_lembrete(e: Evento) -> bool:
    return not (
        e.post_id is None
        or e.lembrete_enviado
        or e.status is Status.CANCELADO
        or (e.publicado_em is not None and e.inicio - e.publicado_em < ANTECEDENCIA_MINIMA)
    )


def enviar_lembretes(estado: Estado, canal: Canal, agora: datetime) -> None:
    for e in estado.eventos:
        if not precisa_de_lembrete(e) or agora >= e.inicio:
            continue
        if agora < datetime.combine(dia_do_lembrete(e), HORA_DO_LEMBRETE, FUSO):
            continue
        canal.publicar(texto_lembrete(e, agora), resposta_a=e.post_id)
        e.lembrete_enviado = True


def texto_lembrete(e: Evento, agora: datetime) -> str:
    return f"⏰ Lembrete: <b>{escape(e.titulo)}</b> é {_relativo(e, agora)}\n📅 {quando(e)}"


def _relativo(e: Evento, agora: datetime) -> str:
    dias = (e.inicio.astimezone(FUSO).date() - agora.astimezone(FUSO).date()).days
    if dias == 0:
        return "hoje!"
    if dias == 1:
        return "amanhã!"
    dia = e.inicio.astimezone(FUSO)
    return f"{_NOMES[dia.weekday()]}, {dia:%d/%m}!"


_NOMES = ["na segunda", "na terça", "na quarta", "na quinta", "na sexta", "no sábado", "no domingo"]


def publicar_agenda(estado: Estado, canal: Canal, agora: datetime) -> None:
    local = agora.astimezone(FUSO)
    segunda = local.date() - timedelta(days=local.weekday())
    if local.weekday() != SEGUNDA or local.time() < HORA_DA_AGENDA or estado.ultima_agenda == segunda.isoformat():
        return
    estado.ultima_agenda = segunda.isoformat()
    inicio = datetime.combine(segunda, time.min, FUSO)
    da_semana = sorted(
        (e for e in estado.eventos
         if e.post_id is not None and e.status is not Status.CANCELADO
         and inicio <= e.inicio < inicio + timedelta(days=7)),
        key=lambda e: e.inicio,
    )
    if da_semana:
        canal.publicar(texto_agenda(segunda, da_semana, canal))


def texto_agenda(segunda: date, eventos: list[Evento], canal: Canal) -> str:
    domingo = segunda + timedelta(days=6)
    linhas = [f"🗓️ <b>Agenda da semana</b> ({segunda:%d/%m} a {domingo:%d/%m})", ""]
    for e in eventos:
        onde = "online" if e.online else (e.cidade or "")
        link = escape(canal.link_do_post(e.post_id), quote=True)
        linhas.append(f'• {quando(e)} — <a href="{link}">{escape(e.titulo)}</a>' + (f" ({escape(onde)})" if onde else ""))
    return "\n".join(linhas)
