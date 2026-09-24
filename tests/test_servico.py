from dataclasses import dataclass

import httpx
from conftest import anuncio, em
from test_ciclo import REVISOR, CanalFalso, ConversaFalsa, FonteFixa, FonteQuebrada, clique

from radar import estado
from radar.revisao import Saidas
from radar.servico import Servico, coleta_pendente, ultimo_horario_de_coleta


class TestHorarios:
    def test_ultimo_horario(self):
        assert ultimo_horario_de_coleta(em(12, 7, 59)) == em(11, 18)
        assert ultimo_horario_de_coleta(em(12, 8)) == em(12, 8)
        assert ultimo_horario_de_coleta(em(12, 17, 30)) == em(12, 8)
        assert ultimo_horario_de_coleta(em(12, 23)) == em(12, 18)

    def test_coleta_pendente(self):
        assert coleta_pendente(None, em(12, 3))  # primeiro boot coleta na hora
        assert not coleta_pendente(em(12, 8, 1), em(12, 17, 59))
        assert coleta_pendente(em(12, 8, 1), em(12, 18, 0))
        assert not coleta_pendente(em(12, 18, 5), em(13, 7, 0))
        assert coleta_pendente(em(11, 18, 5), em(13, 9, 0))  # ficou fora do ar um dia


@dataclass
class Relogio:
    atual: object

    def __call__(self):
        return self.atual


def servico(tmp_path, *fontes, agora=em(12, 8, 5)):
    canal, conversa = CanalFalso(), ConversaFalsa()
    relogio = Relogio(agora)
    s = Servico(fontes, httpx.Client(), Saidas(canal, conversa, REVISOR), tmp_path / "estado.json", agora=relogio)
    return s, canal, conversa, relogio


def test_coleta_so_nos_horarios(tmp_path):
    fonte = FonteFixa([anuncio()])
    coletas = []
    fonte.coletar = lambda http, agora: coletas.append(agora) or [anuncio()]
    s, canal, _, relogio = servico(tmp_path, fonte)
    s.passo(espera=0)
    relogio.atual = em(12, 12)
    s.passo(espera=0)
    relogio.atual = em(12, 18, 1)
    s.passo(espera=0)
    assert coletas == [em(12, 8, 5), em(12, 18, 1)]
    posts = [t for t, _ in canal.publicados if "Agenda da semana" not in t]  # 12/10 é segunda
    assert len(posts) == 1


def test_aprovacao_publica_no_mesmo_passo(tmp_path):
    s, canal, conversa, relogio = servico(tmp_path, FonteFixa([anuncio()], confiavel=False))
    s.passo(espera=0)
    assert canal.publicados == [] and len(conversa.pedidos) == 1

    relogio.atual = em(12, 8, 6)
    conversa.chegando = [clique("aprovar", s.estado.fila[0].evento.id)]
    s.passo(espera=0)
    assert len(canal.publicados) == 1


def test_grava_so_quando_muda_e_retoma_do_disco(tmp_path):
    s, _, _, relogio = servico(tmp_path, FonteFixa([anuncio()]))
    s.passo(espera=0)
    arquivo = tmp_path / "estado.json"
    gravado = arquivo.stat().st_mtime_ns
    relogio.atual = em(12, 9)
    s.passo(espera=0)
    assert arquivo.stat().st_mtime_ns == gravado

    retomado = Servico([], httpx.Client(), s.saidas, arquivo)
    assert retomado.estado == s.estado and retomado.estado.ultima_coleta == em(12, 8, 5)


def test_falha_de_fonte_alerta_o_revisor_uma_vez_por_hora(tmp_path):
    s, _, conversa, relogio = servico(tmp_path, FonteQuebrada())
    s.passo(espera=0)
    relogio.atual = em(12, 18, 1)
    s.passo(espera=0)  # nova falha 10h depois: alerta de novo
    s.estado.ultima_coleta = None
    relogio.atual = em(12, 18, 20)
    s.passo(espera=0)  # terceira falha em menos de 1h: silêncio
    alertas = [t for chat, t in conversa.respostas if chat == REVISOR and "falharam" in t]
    assert len(alertas) == 2 and "quebrada" in alertas[0]


def test_lembrete_sai_no_horario_mesmo_sem_coleta(tmp_path):
    s, canal, _, relogio = servico(tmp_path, FonteFixa([anuncio(inicio=em(14, 19), fim=em(14, 21))]))
    s.passo(espera=0)  # 12/10 8h05: coleta e publica
    relogio.atual = em(13, 10, 0)
    s.passo(espera=0)  # véspera, 10h: Lembrete, sem esperar a coleta das 18h
    assert any("Lembrete" in texto for texto, _ in canal.publicados)


def test_estado_do_arquivo_nao_corrompe_com_tmp(tmp_path):
    s, _, _, _ = servico(tmp_path, FonteFixa([anuncio()]))
    s.passo(espera=0)
    assert not (tmp_path / "estado.tmp").exists()
    assert estado.carregar(tmp_path / "estado.json").eventos
