from dataclasses import dataclass, field

import httpx
from conftest import anuncio, em

from radar import ciclo, estado
from radar.dominio import Anuncio, Status


@dataclass
class FonteFixa:
    anuncios: list[Anuncio]
    id: str = "fixa"
    confiavel: bool = True

    def coletar(self, http, agora):
        return self.anuncios


class FonteQuebrada:
    id = "quebrada"
    confiavel = True

    def coletar(self, http, agora):
        raise httpx.ConnectError("fora do ar")


@dataclass
class CanalFalso:
    publicados: list[tuple[str, int | None]] = field(default_factory=list)
    editados: list[tuple[int, str]] = field(default_factory=list)

    def publicar(self, texto, resposta_a=None):
        self.publicados.append((texto, resposta_a))
        return len(self.publicados)

    def editar(self, post_id, texto):
        self.editados.append((post_id, texto))


AGORA = em(1, 12)


def rodar(est, *fontes, canal=None):
    canal = canal or CanalFalso()
    falhas = ciclo.executar(fontes, httpx.Client(), canal, est, AGORA)
    return canal, falhas


def test_evento_novo_de_fonte_confiavel_e_publicado_uma_vez():
    est = estado.Estado()
    canal, _ = rodar(est, FonteFixa([anuncio()]))
    assert len(canal.publicados) == 1 and "Kubernetes" in canal.publicados[0][0]
    canal, _ = rodar(est, FonteFixa([anuncio()]))
    assert canal.publicados == [] and canal.editados == []


def test_mesmo_evento_em_duas_fontes_vira_um_post():
    est = estado.Estado()
    crio = anuncio(url="https://crio/aws", titulo="Encontro AWS no CRIO", local="Centro de Inovação de Criciúma CRIO")
    canal, _ = rodar(est, FonteFixa([anuncio()]), FonteFixa([crio], id="crio"))
    assert len(canal.publicados) == 1
    assert len(est.eventos[0].urls) == 2


def test_fonte_aberta_nao_publica_sozinha():
    est = estado.Estado()
    canal, _ = rodar(est, FonteFixa([anuncio()], confiavel=False))
    assert canal.publicados == [] and est.eventos == []


def test_fora_da_regiao_nao_publica():
    canal, _ = rodar(estado.Estado(), FonteFixa([anuncio(cidade="Florianópolis")]))
    assert canal.publicados == []


def test_alteracao_de_data_edita_post_e_avisa_em_resposta():
    est = estado.Estado()
    rodar(est, FonteFixa([anuncio()]))
    canal, _ = rodar(est, FonteFixa([anuncio(inicio=em(19, 19), fim=em(19, 21))]))
    assert canal.editados and canal.editados[0][0] == 1
    [(aviso, resposta_a)] = canal.publicados
    assert "Nova data" in aviso and resposta_a == 1


def test_cancelamento_edita_e_avisa():
    est = estado.Estado()
    rodar(est, FonteFixa([anuncio()]))
    canal, _ = rodar(est, FonteFixa([anuncio(cancelado=True)]))
    assert "CANCELADO" in canal.editados[0][1]
    assert est.eventos[0].status is Status.CANCELADO


def test_anuncio_que_some_nao_cancela():
    est = estado.Estado()
    rodar(est, FonteFixa([anuncio()]))
    canal, _ = rodar(est, FonteFixa([]))
    assert canal.publicados == [] and canal.editados == []
    assert est.eventos[0].status is Status.AGENDADO


def test_fonte_quebrada_nao_derruba_as_outras():
    canal, falhas = rodar(estado.Estado(), FonteQuebrada(), FonteFixa([anuncio()]))
    assert falhas == ["quebrada"] and len(canal.publicados) == 1


def test_estado_sobrevive_ida_e_volta(tmp_path):
    est = estado.Estado()
    rodar(est, FonteFixa([anuncio()]))
    arquivo = tmp_path / "estado.json"
    estado.salvar(est, arquivo)
    assert estado.carregar(arquivo) == est
