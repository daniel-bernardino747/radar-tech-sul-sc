"""Lê o Anúncio por trás de um link, para Sugestões e para a agenda do CRIO.

Links vêm de qualquer pessoa, então a leitura é defensiva: só sites da lista de
permitidos (inclusive a cada redirecionamento), tamanho e tempo totais limitados, e a
URL do Anúncio é sempre a que foi de fato lida, nunca a que a página declara.
"""

import time
from urllib.parse import urljoin, urlsplit

import httpx

from radar.dominio import Anuncio
from radar.fontes.sympla import eh_pagina_de_evento, ler_pagina_evento
from radar.jsonld import anuncio_de_jsonld, eventos_jsonld

SITES_PERMITIDOS = ("sympla.com.br", "meetup.com", "even3.com.br", "supertixs.com")
LIMITE_DE_BYTES = 2_000_000
PRAZO_TOTAL = 15.0  # segundos, somando redirecionamentos e download
MAX_REDIRECIONAMENTOS = 3


def permitido(url: str) -> bool:
    partes = urlsplit(url)
    host = (partes.hostname or "").lower()
    return (
        partes.scheme in ("http", "https")
        and partes.port in (None, 80, 443)
        and not partes.username
        and any(host == site or host.endswith("." + site) for site in SITES_PERMITIDOS)
    )


def baixar(http: httpx.Client, url: str) -> tuple[str, str] | None:
    """(URL final, HTML) de um site permitido, ou None. Nunca sai da lista de permitidos."""
    prazo = time.monotonic() + PRAZO_TOTAL
    for _ in range(MAX_REDIRECIONAMENTOS + 1):
        if not permitido(url):
            return None
        restante = prazo - time.monotonic()
        if restante <= 0:
            return None
        try:
            with http.stream("GET", url, follow_redirects=False, timeout=min(restante, 10.0)) as resposta:
                if resposta.is_redirect:
                    url = urljoin(url, resposta.headers.get("location", ""))
                    continue
                if resposta.status_code != 200:
                    return None
                corpo = bytearray()
                for pedaco in resposta.iter_bytes():
                    corpo += pedaco
                    if len(corpo) > LIMITE_DE_BYTES or time.monotonic() > prazo:
                        return None
                return url, corpo.decode(resposta.encoding or "utf-8", errors="replace")
        except httpx.HTTPError:
            return None
    return None


def ler_link(http: httpx.Client, url: str, fonte: str) -> Anuncio | None:
    """Sympla pelo payload da página; o resto (Meetup, Even3...) por JSON-LD. None se não der."""
    baixado = baixar(http, url)
    if baixado is None:
        return None
    final, html = baixado
    try:
        if eh_pagina_de_evento(final):
            anuncio = ler_pagina_evento(html, fonte, final)
        else:
            eventos = eventos_jsonld(html)
            anuncio = anuncio_de_jsonld(eventos[0], fonte, final) if eventos else None
    except (KeyError, ValueError, TypeError, AttributeError, IndexError):
        return None  # página com dados fora do formato esperado
    return anuncio
