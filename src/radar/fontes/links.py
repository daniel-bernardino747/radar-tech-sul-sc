"""Lê o Anúncio por trás de um link qualquer, para Sugestões e para a agenda do CRIO."""

import httpx

from radar.dominio import Anuncio
from radar.fontes.sympla import eh_pagina_de_evento, ler_pagina_evento
from radar.jsonld import anuncio_de_jsonld, eventos_jsonld


def ler_link(http: httpx.Client, url: str, fonte: str) -> Anuncio | None:
    """Sympla pelo payload da página; o resto (Meetup, Even3...) por JSON-LD. None se não der."""
    try:
        resposta = http.get(url)
        resposta.raise_for_status()
    except httpx.HTTPError:
        return None
    final = str(resposta.url)
    if eh_pagina_de_evento(final):
        return ler_pagina_evento(resposta.text, fonte, final)
    eventos = eventos_jsonld(resposta.text)
    if not eventos:
        return None
    try:
        return anuncio_de_jsonld(eventos[0], fonte, final)
    except (KeyError, ValueError):
        return None
