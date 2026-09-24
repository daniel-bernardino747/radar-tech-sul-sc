from datetime import datetime

import httpx

from radar.fontes.crio import Crio, links_de_evento


def test_links_da_agenda(fixtures):
    links = links_de_evento((fixtures / "crio_agenda.html").read_text(encoding="utf-8"))
    assert "https://supertixs.com/e/retailtech-crio-inovacao-e-futuro-do-varejo" in links
    assert "https://www.even3.com.br/inovascea-rumo-ao-topo-744903" in links
    assert sum("sympla.com.br/evento/" in link for link in links) == 3
    assert not any("unesc.net" in link or "lovable" in link for link in links)


def test_coleta_so_futuros_e_assume_criciuma_sem_cidade(fixtures):
    agenda = (fixtures / "crio_agenda.html").read_text(encoding="utf-8")
    supertixs = (fixtures / "supertixs_evento.html").read_text(encoding="utf-8")

    def responder(req: httpx.Request) -> httpx.Response:
        if req.url.host == "www.criocriciuma.com.br":
            return httpx.Response(200, text=agenda)
        if req.url.host == "supertixs.com":
            return httpx.Response(200, text=supertixs)
        return httpx.Response(404)  # os outros links já passaram ou não importam aqui

    http = httpx.Client(transport=httpx.MockTransport(responder))
    [a] = Crio().coletar(http, datetime.fromisoformat("2026-09-01T00:00:00-03:00"))
    assert a.titulo.startswith("RetailTech CRIO")
    assert a.cidade == "Criciúma" and a.local == "CRIO - Centro de Inovação Criciúma"
    assert a.fonte == "crio"
    assert not Crio().confiavel
