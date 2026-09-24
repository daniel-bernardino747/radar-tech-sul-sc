"""Uma execução do Radar: coleta das Fontes, consolidação em Eventos e divulgação no Canal."""

import sys
from collections.abc import Iterable
from datetime import datetime, timedelta

import httpx

from radar.dominio import Anuncio, Evento, aplicar, eh_elegivel, mesmo_evento
from radar.estado import Estado
from radar.fontes import Fonte
from radar.post import texto_mudanca, texto_post
from radar.telegram import Canal

RETENCAO = timedelta(days=30)


def executar(
    fontes: Iterable[Fonte], http: httpx.Client, canal: Canal, estado: Estado, agora: datetime
) -> list[str]:
    """Roda um ciclo e devolve os ids das Fontes que falharam."""
    falhas = []
    for fonte in fontes:
        try:
            anuncios = list(fonte.coletar(http, agora))
        except Exception as erro:  # uma Fonte quebrada não derruba as outras
            print(f"Fonte {fonte.id} falhou: {erro!r}", file=sys.stderr)
            falhas.append(fonte.id)
            continue
        for anuncio in anuncios:
            consolidar(estado, anuncio, fonte.confiavel, canal)
    publicar_pendentes(estado, canal)
    esquecer_antigos(estado, agora)
    return falhas


def consolidar(estado: Estado, a: Anuncio, confiavel: bool, canal: Canal) -> None:
    existente = next((e for e in estado.eventos if mesmo_evento(a, e)), None)
    if existente is None:
        # Fontes abertas vão para a Fila de revisão, que ainda não existe.
        if confiavel and eh_elegivel(a) and not a.cancelado:
            estado.eventos.append(Evento.de_anuncio(a))
        return

    mudanca = aplicar(existente, a)
    if existente.post_id is None or not mudanca.houve:
        return
    canal.editar(existente.post_id, texto_post(existente))
    if mudanca.relevantes or mudanca.cancelou:
        canal.publicar(texto_mudanca(existente, mudanca), resposta_a=existente.post_id)


def publicar_pendentes(estado: Estado, canal: Canal) -> None:
    for e in sorted(estado.eventos, key=lambda e: e.inicio):
        if e.post_id is None:
            e.post_id = canal.publicar(texto_post(e))


def esquecer_antigos(estado: Estado, agora: datetime) -> None:
    estado.eventos = [e for e in estado.eventos if (e.fim or e.inicio) > agora - RETENCAO]
