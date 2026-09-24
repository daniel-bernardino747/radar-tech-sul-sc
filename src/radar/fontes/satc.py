"""Portal de eventos da SATC: o front em AngularJS lê um JSON que o Radar lê direto.

Fonte aberta com filtro de tema: a SATC publica de tudo (cálculo, clube do livro,
viagens) e só uma parte é de tecnologia. O portal não informa horário, só datas.
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import datetime, time

import httpx

from radar.dominio import FUSO, GRATUITO, Anuncio
from radar.relevancia import parece_curso, parece_tech

LISTA = "https://www1.satc.edu.br/eventos/index.php/eventos/getListaEventos"
PAGINA = "https://www1.satc.edu.br/eventos/index.php/inscricoes/evento/{slug}"


@dataclass(frozen=True)
class Satc:
    id: str = "satc"
    confiavel: bool = False

    def coletar(self, http: httpx.Client, agora: datetime) -> Iterator[Anuncio]:
        resposta = http.get(LISTA)
        resposta.raise_for_status()
        for ev in ler_lista(resposta.content):
            a = anuncio_da_satc(ev, self.id)
            if (a.fim or a.inicio) >= agora and parece_tech(a):
                yield replace(a, curso=parece_curso(a))


def ler_lista(conteudo: bytes) -> list[dict]:
    return json.loads(conteudo.decode("utf-8-sig"))["data"]  # a resposta vem com BOM


def anuncio_da_satc(ev: dict, fonte: str) -> Anuncio:
    inicio = _dia(ev["data_inicial"])
    fim = _dia(ev["data_final"]) if ev.get("data_final") else inicio
    valor = float(ev.get("valor_taxa") or 0)
    return Anuncio(
        fonte=fonte,
        url=PAGINA.format(slug=ev["slug"]),
        titulo=ev["descricao"].strip(),
        inicio=datetime.combine(inicio, time.min, FUSO),
        fim=datetime.combine(fim, time.max, FUSO),
        tem_horario=False,
        local=(ev.get("local") or "").strip() or None,
        cidade=(ev.get("cidade") or "").strip() or None,
        organizador="SATC",
        preco=GRATUITO if valor == 0 else f"R$ {valor:.2f}".replace(".", ","),
    )


def _dia(texto: str):
    return datetime.strptime(texto, "%d/%m/%Y").date()
