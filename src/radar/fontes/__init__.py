"""Fontes do Radar. Ver a tabela "Fontes do MVP" no README."""

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol

import httpx

from radar.dominio import Anuncio


class Fonte(Protocol):
    id: str
    confiavel: bool

    def coletar(self, http: httpx.Client, agora: datetime) -> Iterable[Anuncio]:
        """Anúncios de Eventos que ainda não terminaram."""
        ...


def todas() -> list[Fonte]:
    from radar.fontes.meetup import Meetup
    from radar.fontes.sympla import Sympla

    return [
        Meetup(id="meetup-criciumaops", grupo="criciumaops"),
        Meetup(id="meetup-criciumadev", grupo="criciumadev"),
        # A página de Criciúma já traz Tubarão, Araranguá e o resto da Região.
        Sympla(id="sympla-criciuma", cidade="criciuma-sc"),
    ]
