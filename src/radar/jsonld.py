"""Lê um Anúncio a partir do JSON-LD schema.org/Event embutido numa página.

A página pode ser de qualquer um (Sugestões), então nada aqui confia no formato:
tipos são conferidos e a URL do Anúncio é sempre a informada por quem chamou.
"""

import json
from datetime import datetime

from radar.dominio import FUSO, Anuncio


def eventos_jsonld(html: str) -> list[dict]:
    achados = []
    for bloco in _blocos_jsonld(html):
        try:
            dado = json.loads(bloco)
        except json.JSONDecodeError:
            continue
        if isinstance(dado, dict):
            itens = dado.get("@graph", [dado])
        else:
            itens = dado if isinstance(dado, list) else []
        achados += [i for i in itens if isinstance(i, dict) and i.get("@type") == "Event"]
    return achados


def _blocos_jsonld(html: str):
    """Conteúdo de cada <script type="application/ld+json">, numa varredura linear.

    Uma expressão regular aqui fica quadrática em páginas grandes e maliciosas.
    """
    minusculo = html.lower()
    pos = 0
    while (inicio := minusculo.find("<script", pos)) != -1:
        fim_da_tag = minusculo.find(">", inicio)
        if fim_da_tag == -1:
            return
        fecha = minusculo.find("</script>", fim_da_tag)
        if fecha == -1:
            return
        if "application/ld+json" in minusculo[inicio:fim_da_tag]:
            yield html[fim_da_tag + 1:fecha]
        pos = fecha + len("</script>")


def anuncio_de_jsonld(ev: dict, fonte: str, url: str) -> Anuncio:
    """`url` é a página de fato lida; a "url" declarada no JSON-LD é ignorada de propósito:
    senão uma página qualquer poderia se passar por um Evento já publicado."""
    nome, inicio_bruto = ev["name"], ev["startDate"]
    if not isinstance(nome, str) or not isinstance(inicio_bruto, str):
        raise ValueError("JSON-LD sem name/startDate em texto")
    local = _objeto(ev.get("location"))
    endereco = _objeto(local.get("address"))
    online = (
        _texto(ev.get("eventAttendanceMode")).endswith("OnlineEventAttendanceMode")
        or local.get("@type") == "VirtualLocation"
    )
    return Anuncio(
        fonte=fonte,
        url=url,
        titulo=nome.strip(),
        inicio=_data(inicio_bruto),
        fim=_data_ou_nada(ev.get("endDate")),
        tem_horario="T" in inicio_bruto,
        local=None if online else (_texto(local.get("name")) or None),
        cidade=None if online else (_texto(endereco.get("addressLocality")) or None),
        online=online,
        organizador=_texto(_objeto(ev.get("organizer")).get("name")) or None,
        cancelado=_texto(ev.get("eventStatus")).endswith("EventCancelled"),
    )


def _objeto(valor: object) -> dict:
    if isinstance(valor, list):
        valor = valor[0] if valor else {}
    return valor if isinstance(valor, dict) else {}


def _texto(valor: object) -> str:
    return valor.strip() if isinstance(valor, str) else ""


def _data(texto: str) -> datetime:
    valor = datetime.fromisoformat(texto)
    return valor if valor.tzinfo else valor.replace(tzinfo=FUSO)


def _data_ou_nada(texto: object) -> datetime | None:
    """Algumas páginas (ex.: Even3) publicam endDate malformado; nesse caso, sem fim."""
    if not isinstance(texto, str) or not texto:
        return None
    try:
        return _data(texto)
    except ValueError:
        return None
