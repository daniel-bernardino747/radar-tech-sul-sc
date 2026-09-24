"""Agenda do CRIO: uma página Wix com links para Sympla, Even3, Supertixs...

É Fonte aberta sem filtro de tema: o CRIO também cede espaço a eventos de outras áreas
(ex.: um congresso de Medicina), então tudo passa pelo Revisor. O volume é baixo.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import datetime

import httpx

from radar.dominio import Anuncio
from radar.fontes.links import ler_link

AGENDA = "https://www.criocriciuma.com.br/eventos"

_LINK_DE_EVENTO = re.compile(
    r'href="(https?://(?:www\.)?(?:'
    r"sympla\.com\.br/evento/[^\"]+"
    r"|even3\.com\.br/[^\"]+"
    r"|supertixs\.com/e/[^\"]+"
    r"|meetup\.com/[^\"]+/events/\d+[^\"]*"
    r'))"'
)


@dataclass(frozen=True)
class Crio:
    id: str = "crio"
    confiavel: bool = False

    def coletar(self, http: httpx.Client, agora: datetime) -> Iterator[Anuncio]:
        resposta = http.get(AGENDA)
        resposta.raise_for_status()
        for link in links_de_evento(resposta.text):
            anuncio = ler_link(http, link, self.id)
            if anuncio is None or (anuncio.fim or anuncio.inicio) < agora:
                continue
            if not anuncio.online and anuncio.cidade is None:
                # Algumas plataformas (ex.: Supertixs) não informam a cidade; a agenda é do CRIO.
                anuncio = replace(anuncio, cidade="Criciúma")
            yield anuncio


def links_de_evento(html: str) -> list[str]:
    return list(dict.fromkeys(_LINK_DE_EVENTO.findall(html)))
