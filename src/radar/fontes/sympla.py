"""Sympla: a busca por cidade é Fonte aberta; a página de cada evento completa os dados.

A página de cidade de Criciúma já inclui as cidades vizinhas da Região. Os dados vêm do
payload do Next.js embutido no HTML, sem API oficial (a pública só lista eventos do
próprio produtor). O e-mail do organizador vem junto e é descartado.
"""

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import datetime

import httpx

from radar.dominio import FUSO, Anuncio
from radar.relevancia import parece_curso, parece_tech

_FLIGHT = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', re.S)
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
MAX_PAGINAS = 20


@dataclass(frozen=True)
class Sympla:
    id: str
    cidade: str  # slug da página de cidade, ex.: "criciuma-sc"
    confiavel: bool = False

    def coletar(self, http: httpx.Client, agora: datetime) -> Iterator[Anuncio]:
        for base in self._listar(http):
            if (base.fim or base.inicio) < agora or not parece_tech(base) or parece_curso(base):
                continue
            detalhado = _detalhar(http, base)
            if not detalhado.curso:
                yield detalhado

    def _listar(self, http: httpx.Client) -> Iterator[Anuncio]:
        pagina = 1
        while pagina <= MAX_PAGINAS:
            resposta = http.get(f"https://www.sympla.com.br/eventos/{self.cidade}", params={"page": pagina})
            resposta.raise_for_status()
            resultado = ler_busca(resposta.text)
            yield from (anuncio_da_busca(ev, self.id) for ev in resultado["data"])
            if pagina * resultado["limit"] >= resultado["total"] or not resultado["data"]:
                return
            pagina += 1


def ler_busca(html: str) -> dict:
    """O bloco searchDataResult ({data, total, limit, page}) da página de cidade."""
    flight = "".join(json.loads(f'"{m}"') for m in _FLIGHT.findall(html))
    inicio = flight.find('{"searchDataResult"')
    if inicio < 0:
        raise ValueError("Página de cidade da Sympla sem searchDataResult; o formato mudou?")
    dado, _ = json.JSONDecoder().raw_decode(flight, inicio)
    return dado["searchDataResult"]


def anuncio_da_busca(ev: dict, fonte: str) -> Anuncio:
    local = ev.get("location") or {}
    return Anuncio(
        fonte=fonte,
        url=ev["url"],
        titulo=ev["name"].strip(),
        inicio=datetime.fromisoformat(ev["start_date"]),
        fim=datetime.fromisoformat(ev["end_date"]) if ev.get("end_date") else None,
        local=local.get("name") or None,
        cidade=local.get("city") or None,
        online=ev.get("event_type") == "ONLINE",
        organizador=(ev.get("organizer") or {}).get("name") or None,
    )


def eh_pagina_de_evento(url: str) -> bool:
    return re.match(r"https?://(www\.)?sympla\.com\.br/(evento/|.+__\d+)", url) is not None


def ler_pagina_evento(html: str, fonte: str, url: str) -> Anuncio | None:
    achado = _NEXT_DATA.search(html)
    if not achado:
        return None
    ev = _procurar_evento(json.loads(achado.group(1)))
    if ev is None:
        return None
    endereco = ev.get("eventsAddress") or {}
    online = bool(ev.get("onlineInfo")) or ev.get("eventType") == "ONLINE"
    host = ev.get("eventsHost") or {}
    return Anuncio(
        fonte=fonte,
        url=ev.get("newUrl") or url,
        titulo=ev["name"].strip(),
        inicio=_local(ev["startDate"]),
        fim=_local(ev["endDate"]) if ev.get("endDate") else None,
        local=None if online else (endereco.get("name") or None),
        cidade=None if online else (endereco.get("city") or None),
        online=online,
        organizador=host.get("name") or None,
        preco={"free": "Gratuito", "paid": "Pago"}.get(ev.get("paymentEventType")),
        cancelado=bool(ev.get("cancelled")),
        curso=bool(ev.get("courseInfo")),
    )


def _detalhar(http: httpx.Client, base: Anuncio) -> Anuncio:
    """Completa com a página do evento; mantém os horários da busca, que já vêm com fuso."""
    if not eh_pagina_de_evento(base.url):
        return base
    try:
        resposta = http.get(base.url)
        resposta.raise_for_status()
    except httpx.HTTPError:
        return base
    pagina = ler_pagina_evento(resposta.text, base.fonte, base.url)
    if pagina is None:
        return base
    return replace(pagina, url=base.url, inicio=base.inicio, fim=base.fim)


def _procurar_evento(o: object) -> dict | None:
    if isinstance(o, dict):
        if {"id", "name", "startDate"} <= o.keys():
            return o
        filhos = o.values()
    elif isinstance(o, list):
        filhos = o
    else:
        return None
    for filho in filhos:
        if (achado := _procurar_evento(filho)) is not None:
            return achado
    return None


def _local(texto: str) -> datetime:
    """A página do evento traz "2026-11-09 18:00:00", sem fuso: é horário de Brasília."""
    return datetime.fromisoformat(texto).replace(tzinfo=FUSO)
