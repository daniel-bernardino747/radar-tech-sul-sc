"""Grupos do Meetup: o iCal lista os Eventos, a página de cada um dá local e Status."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import httpx
from icalendar import Calendar

from radar.dominio import Anuncio
from radar.jsonld import anuncio_de_jsonld, eventos_jsonld

FUSO = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True)
class Meetup:
    id: str
    grupo: str
    confiavel: bool = True

    def coletar(self, http: httpx.Client, agora: datetime) -> Iterator[Anuncio]:
        resposta = http.get(f"https://www.meetup.com/{self.grupo}/events/ical/")
        resposta.raise_for_status()
        for base in ler_ical(resposta.text, self.id):
            if (base.fim or base.inicio) < agora:
                continue
            yield _detalhar(http, base)


def ler_ical(texto: str, fonte: str) -> list[Anuncio]:
    anuncios = []
    for ev in Calendar.from_ical(texto).walk("VEVENT"):
        inicio, tem_horario = _instante(ev.decoded("DTSTART"))
        fim = _instante(ev.decoded("DTEND"))[0] if ev.get("DTEND") else None
        anuncios.append(Anuncio(
            fonte=fonte,
            url=str(ev.get("URL") or ev.get("UID")),
            titulo=str(ev.get("SUMMARY", "")).strip(),
            inicio=inicio,
            fim=fim,
            tem_horario=tem_horario,
            cancelado=str(ev.get("STATUS", "")).upper() == "CANCELLED",
        ))
    return anuncios


def _instante(valor: date | datetime) -> tuple[datetime, bool]:
    if isinstance(valor, datetime):
        return (valor if valor.tzinfo else valor.replace(tzinfo=FUSO)), True
    return datetime.combine(valor, time.min, FUSO), False


def _detalhar(http: httpx.Client, base: Anuncio) -> Anuncio:
    """Completa o Anúncio do iCal com o JSON-LD da página. Sem página, fica o do iCal."""
    try:
        resposta = http.get(base.url)
        resposta.raise_for_status()
    except httpx.HTTPError:
        return base
    eventos = eventos_jsonld(resposta.text)
    if not eventos:
        return base
    return anuncio_de_jsonld(eventos[0], base.fonte, base.url)
