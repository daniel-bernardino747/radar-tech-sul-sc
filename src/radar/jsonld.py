"""Lê um Anúncio a partir do JSON-LD schema.org/Event embutido numa página."""

import json
import re
from datetime import datetime

from radar.dominio import Anuncio

_SCRIPT = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)


def eventos_jsonld(html: str) -> list[dict]:
    achados = []
    for bloco in _SCRIPT.findall(html):
        try:
            dado = json.loads(bloco)
        except json.JSONDecodeError:
            continue
        itens = dado if isinstance(dado, list) else dado.get("@graph", [dado])
        achados += [i for i in itens if isinstance(i, dict) and i.get("@type") == "Event"]
    return achados


def anuncio_de_jsonld(ev: dict, fonte: str, url: str) -> Anuncio:
    inicio_bruto = ev["startDate"]
    tem_horario = "T" in inicio_bruto
    local = ev.get("location") or {}
    if isinstance(local, list):
        local = local[0] if local else {}
    endereco = local.get("address") or {}
    if isinstance(endereco, str):
        endereco = {}
    online = (
        ev.get("eventAttendanceMode", "").endswith("OnlineEventAttendanceMode")
        or local.get("@type") == "VirtualLocation"
    )
    organizador = ev.get("organizer") or {}
    if isinstance(organizador, list):
        organizador = organizador[0] if organizador else {}
    return Anuncio(
        fonte=fonte,
        url=ev.get("url") or url,
        titulo=ev["name"].strip(),
        inicio=datetime.fromisoformat(inicio_bruto),
        fim=datetime.fromisoformat(ev["endDate"]) if ev.get("endDate") else None,
        tem_horario=tem_horario,
        local=None if online else (local.get("name") or None),
        cidade=None if online else (endereco.get("addressLocality") or None),
        online=online,
        organizador=organizador.get("name") if isinstance(organizador, dict) else None,
        cancelado=ev.get("eventStatus", "").endswith("EventCancelled"),
    )
