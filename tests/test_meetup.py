from datetime import datetime, timedelta

import httpx

from radar.fontes.meetup import Meetup, ler_ical
from radar.jsonld import anuncio_de_jsonld, eventos_jsonld


def test_le_ical_real(fixtures):
    anuncios = ler_ical((fixtures / "meetup_bostonpython.ics").read_text(encoding="utf-8"), "x")
    assert len(anuncios) == 10
    primeiro = anuncios[0]
    assert primeiro.titulo == "Python Over Coffee"
    assert primeiro.url == "https://www.meetup.com/bostonpython/events/316459189/"
    assert primeiro.inicio.utcoffset() is not None
    assert (primeiro.fim - primeiro.inicio) == timedelta(hours=1)


def test_jsonld_da_pagina_do_evento(fixtures):
    html = (fixtures / "meetup_evento_criciumaops.html").read_text(encoding="utf-8")
    [ev] = eventos_jsonld(html)
    a = anuncio_de_jsonld(ev, "meetup-criciumaops", "https://fallback")
    assert a.titulo.startswith("6° Meetup")
    assert a.url == "https://www.meetup.com/criciumaops/events/315515560/"
    assert a.inicio == datetime.fromisoformat("2026-07-25T09:00:00-03:00")
    assert a.local == "CRIO - Centro de Inovação Criciúma"
    assert a.cidade == "Criciúma"
    assert a.organizador == "AWS User Group Criciúma"
    assert not a.online and not a.cancelado


def test_coleta_ignora_passados_e_detalha_pela_pagina(fixtures):
    ical = (fixtures / "meetup_bostonpython.ics").read_text(encoding="utf-8")
    pagina = (fixtures / "meetup_evento_criciumaops.html").read_text(encoding="utf-8")

    def responder(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/ical/"):
            return httpx.Response(200, text=ical)
        return httpx.Response(200, text=pagina)

    http = httpx.Client(transport=httpx.MockTransport(responder))
    todos = ler_ical(ical, "x")
    agora = todos[5].inicio
    coletados = list(Meetup(id="m", grupo="g").coletar(http, agora))
    assert len(coletados) == 5
    assert all(a.local == "CRIO - Centro de Inovação Criciúma" for a in coletados)


def test_pagina_fora_do_ar_mantem_dados_do_ical(fixtures):
    ical = (fixtures / "meetup_bostonpython.ics").read_text(encoding="utf-8")

    def responder(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=ical) if req.url.path.endswith("/ical/") else httpx.Response(503)

    http = httpx.Client(transport=httpx.MockTransport(responder))
    [primeiro, *_] = Meetup(id="m", grupo="g").coletar(http, datetime.fromisoformat("2026-01-01T00:00:00+00:00"))
    assert primeiro.titulo == "Python Over Coffee" and primeiro.local is None
