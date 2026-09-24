from pathlib import Path
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


def test_sugestao_pelo_servico_grava_o_ponteiro_antes_de_abrir_o_link(tmp_path):
    arquivo = tmp_path / "estado.json"
    offsets_gravados = []

    def ler(http, url, fonte):
        offsets_gravados.append(estado.carregar(arquivo).offset_telegram)
        return anuncio(url=url)

    canal, conversa = CanalFalso(), ConversaFalsa()
    s = Servico([], httpx.Client(), Saidas(canal, conversa, REVISOR), arquivo, agora=Relogio(em(12, 8, 5)), ler=ler)
    conversa.chegando = [{"update_id": 41, "message": {"chat": {"id": 7, "type": "private"}, "from": {"id": 7},
                                                        "text": "https://www.sympla.com.br/evento/x/1"}}]
    s.passo(espera=0)
    assert offsets_gravados == [42]
    assert len(s.estado.fila) == 1 and "revisão" in conversa.respostas[0][1]


class TestVolume:
    def test_fora_do_railway_nao_checa(self):
        from radar.__main__ import checar_volume

        assert checar_volume(Path("estado/estado.json"), {}) is None

    def test_railway_sem_volume_recusa(self):
        from radar.__main__ import checar_volume

        assert "Nenhum volume" in checar_volume(Path("/data/estado.json"), {"RAILWAY_ENVIRONMENT": "production"})

    def test_railway_com_estado_fora_do_volume_recusa(self, tmp_path):
        from radar.__main__ import checar_volume

        ambiente = {"RAILWAY_ENVIRONMENT": "production", "RAILWAY_VOLUME_MOUNT_PATH": str(tmp_path / "data")}
        assert "fora do volume" in checar_volume(tmp_path / "outro" / "estado.json", ambiente)
        assert checar_volume(tmp_path / "data" / "estado.json", ambiente) is None


def test_conflito_curto_nao_alerta_longo_alerta(tmp_path):
    from radar.telegram import ErroTelegram

    s, _, conversa, relogio = servico(tmp_path)
    conflito = ErroTelegram("getUpdates: Conflict: terminated by other getUpdates request")
    s.tratar_erro(conflito)
    relogio.atual = em(12, 8, 7)
    s.tratar_erro(conflito)
    assert conversa.respostas == []
    relogio.atual = em(12, 8, 9)
    s.tratar_erro(conflito)
    assert len(conversa.respostas) == 1 and "outra instância" in conversa.respostas[0][1]
