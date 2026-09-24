import json
from datetime import datetime

import httpx

from radar.dominio import Evento, eh_elegivel
from radar.fontes.satc import Satc, anuncio_da_satc, ler_lista
from radar.post import quando
from radar.regiao import eh_da_regiao


def test_lista_com_bom(fixtures):
    eventos = ler_lista((fixtures / "satc_lista_eventos.json").read_bytes())
    assert len(eventos) == 6


def test_anuncio_sem_horario_ocupa_o_dia_inteiro(fixtures):
    [ev] = [e for e in ler_lista((fixtures / "satc_lista_eventos.json").read_bytes()) if e["id"] == "329"]
    a = anuncio_da_satc(ev, "satc")
    assert a.titulo.startswith("2º Congresso Internacional de Inovação")
    assert not a.tem_horario
    assert a.inicio == datetime.fromisoformat("2026-09-24T00:00:00-03:00")
    assert a.fim.date().isoformat() == "2026-09-25" and a.fim.hour == 23
    assert a.url.endswith("/inscricoes/evento/2-congresso-internacional-de-inovacao-em-materiais-e-processos-de-manufatura-inovamat-329")
    assert a.preco == "Gratuito" and eh_elegivel(a)
    assert quando(Evento.de_anuncio(a)) == "qui, 24/09 a sex, 25/09"


def test_coleta_so_o_que_parece_tech_e_nao_passou(fixtures):
    conteudo = (fixtures / "satc_lista_eventos.json").read_bytes()
    http = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, content=conteudo)))
    titulos = [a.titulo for a in Satc().coletar(http, datetime.fromisoformat("2026-09-24T12:00:00-03:00"))]
    assert titulos == [
        "2º Congresso Internacional de Inovação em Materiais e Processos de Manufatura (INOVAMAT)",
        "Introdução à Computação em Nuvem - AWS",
    ]


def test_curso_gratuito_da_satc_segue_marcado():
    ev = {"descricao": "Curso de Python para Iniciantes", "data_inicial": "05/10/2026", "data_final": "09/10/2026",
          "local": "SATC", "cidade": "Criciúma", "valor_taxa": "0.00", "slug": "python-1"}
    corpo = json.dumps({"count": 1, "data": [ev]}).encode()
    http = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, content=corpo)))
    [a] = Satc().coletar(http, datetime.fromisoformat("2026-10-01T00:00:00-03:00"))
    assert a.curso and a.preco == "Gratuito" and eh_elegivel(a)


def test_cidade_com_uf():
    assert eh_da_regiao("Criciúma / SC") and eh_da_regiao("Tubarão-SC") and eh_da_regiao("Criciuma")
    assert not eh_da_regiao("Curitiba/PR")
