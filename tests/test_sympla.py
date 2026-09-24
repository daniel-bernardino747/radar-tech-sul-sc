from datetime import datetime

import httpx
from conftest import anuncio

from radar.fontes.links import ler_link
from radar.fontes.sympla import Sympla, eh_pagina_de_evento, ler_busca, ler_pagina_evento
from radar.relevancia import parece_curso, parece_tech


def test_busca_da_pagina_de_cidade(fixtures):
    resultado = ler_busca((fixtures / "sympla_busca_criciuma.html").read_text(encoding="utf-8"))
    assert (resultado["total"], resultado["limit"], len(resultado["data"])) == (286, 24, 24)


def test_pagina_de_evento(fixtures):
    html = (fixtures / "sympla_evento.html").read_text(encoding="utf-8")
    a = ler_pagina_evento(html, "s", "https://fallback")
    assert a.titulo == "Conferência de Direito do Trabalho  Etapa Sul Catarinense"
    assert a.inicio == datetime.fromisoformat("2026-11-09T18:00:00-03:00")
    assert (a.local, a.cidade) == ("Associação Empresarial de Criciúma", "Criciúma")
    assert a.organizador == "Ordem dos Advogados do Brasil - Subseção de Criciúma"
    assert a.preco == "Pago" and not a.cancelado and not a.curso


def test_coleta_filtra_por_tema_e_nao_guarda_email(fixtures):
    busca = (fixtures / "sympla_busca_criciuma.html").read_text(encoding="utf-8")
    evento = (fixtures / "sympla_evento.html").read_text(encoding="utf-8")
    pedidos = []

    def responder(req: httpx.Request) -> httpx.Response:
        pedidos.append(str(req.url))
        if "/eventos/criciuma-sc" in req.url.path:
            return httpx.Response(200, text=busca)
        return httpx.Response(200, text=evento)

    http = httpx.Client(transport=httpx.MockTransport(responder))
    # A fixture é a página 1 (total 286); para não paginar 12 vezes, o teste responde sempre a mesma.
    coletados = list(Sympla(id="s", cidade="criciuma-sc").coletar(http, datetime.fromisoformat("2026-09-24T00:00:00+00:00")))
    assert coletados, "a página 1 tem o Unesc Summit"
    assert all("email" not in repr(a) for a in coletados)
    assert sum("page=" in p for p in pedidos) == 12


def test_urls_de_evento():
    assert eh_pagina_de_evento("https://www.sympla.com.br/evento/unesc-summit-2026/3150000")
    assert eh_pagina_de_evento("https://www.sympla.com.br/conferencia__3570491")
    assert not eh_pagina_de_evento("https://bileto.sympla.com.br/event/126679")
    assert not eh_pagina_de_evento("https://www.sympla.com.br/eventos/criciuma-sc")


def test_relevancia():
    assert parece_tech(anuncio(titulo="Unesc Summit 2026", organizador="Agência de Inovação da Unesc"))
    assert parece_tech(anuncio(titulo="Workshop de IA para Advogados", organizador="OAB"))
    assert not parece_tech(anuncio(titulo="Lily Yoga", organizador="Lívia"))
    assert not parece_tech(anuncio(titulo="Recepção da Jovem Advocacia", organizador="OAB"))
    assert parece_curso(anuncio(titulo="Curso Completo de Python"))
    assert not parece_curso(anuncio(titulo="Python Meetup"))


def test_link_de_even3_com_data_malformada(fixtures):
    html = (fixtures / "even3_evento.html").read_text(encoding="utf-8")
    http = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=html)))
    a = ler_link(http, "https://www.even3.com.br/inovascea-rumo-ao-topo-744903", "sugestao")
    assert a is not None and a.titulo and a.fim is None


def test_link_fora_do_ar():
    http = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(404)))
    assert ler_link(http, "https://x.com/y", "sugestao") is None
