"""Um teste por achado da auditoria de segurança (ver o commit que introduziu este arquivo)."""

import json
import time
from datetime import datetime

import httpx
from conftest import anuncio, em
from test_ciclo import REVISOR, CanalFalso, ConversaFalsa, FonteFixa, Radar, clique, mensagem

from radar import ciclo, estado
from radar.dominio import Status
from radar.fontes.links import LIMITE_DE_BYTES, baixar, ler_link, permitido
from radar.jsonld import eventos_jsonld
from radar.revisao import MAX_LINKS_POR_MENSAGEM, SUGESTOES_POR_HORA, Saidas
from radar.telegram import ErroTelegram


class TestSugestaoNaoAlteraEventoExistente:
    def test_pagina_forjada_nao_cancela_post_publicado(self):
        r = Radar()
        r.rodar(FonteFixa([anuncio()]))
        r.links = {"https://evil.example/x": anuncio(cancelado=True, titulo="HACKEADO")}
        r.rodar(chegando=[mensagem("https://evil.example/x")])
        assert r.canal.editados == [] and r.canal.publicados == []
        assert r.est.eventos[0].status is Status.AGENDADO
        assert r.est.eventos[0].titulo.startswith("CriciumaOps")
        assert "já está no Radar" in r.conversa.respostas[0][1]

    def test_pagina_forjada_nao_troca_item_da_fila(self):
        r = Radar()
        r.rodar(FonteFixa([anuncio(url="https://sympla/1")], confiavel=False))
        r.links = {"https://evil.example/x": anuncio(url="https://sympla/1", titulo="Outra coisa")}
        r.rodar(chegando=[mensagem("https://evil.example/x")])
        assert r.est.fila[0].evento.titulo.startswith("CriciumaOps")

    def test_revisor_pode_corrigir(self):
        r = Radar()
        r.rodar(FonteFixa([anuncio()]))
        r.links = {"https://x": anuncio(cancelado=True)}
        r.rodar(chegando=[mensagem("https://x", de=REVISOR)])
        assert r.est.eventos[0].status is Status.CANCELADO


def cliente(responder) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(responder))


class TestLeituraDeLinks:
    def test_so_sites_permitidos(self):
        assert permitido("https://www.sympla.com.br/evento/x/1")
        assert permitido("https://www.meetup.com/g/events/1/")
        assert not permitido("http://localhost:8080/")
        assert not permitido("http://radar.railway.internal/")
        assert not permitido("http://169.254.169.254/latest/meta-data")
        assert not permitido("https://sympla.com.br.evil.com/")
        assert not permitido("https://evilsympla.com.br/")
        assert not permitido("https://user@sympla.com.br/")
        assert not permitido("https://www.sympla.com.br:8443/")

    def test_nem_chega_a_acessar_site_fora_da_lista(self):
        acessos = []
        http = cliente(lambda req: acessos.append(req) or httpx.Response(200, text="oi"))
        assert baixar(http, "http://127.0.0.1/") is None and acessos == []

    def test_redirecionamento_para_fora_da_lista_e_barrado(self):
        acessos = []

        def responder(req):
            acessos.append(str(req.url))
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})

        assert baixar(cliente(responder), "https://www.sympla.com.br/evento/x/1") is None
        assert acessos == ["https://www.sympla.com.br/evento/x/1"]

    def test_resposta_grande_demais(self):
        http = cliente(lambda req: httpx.Response(200, content=b"a" * (LIMITE_DE_BYTES + 1)))
        assert baixar(http, "https://www.even3.com.br/x") is None

    def test_jsonld_com_tipos_errados_nao_explode(self):
        pagina = '<script type="application/ld+json">%s</script>' % json.dumps(
            {"@type": "Event", "name": 1, "startDate": 5, "location": "texto"})
        http = cliente(lambda req: httpx.Response(200, text=pagina))
        assert ler_link(http, "https://www.even3.com.br/x", "sugestao") is None

    def test_varredura_de_jsonld_e_linear(self):
        hostil = '<script type="application/ld+json">' * 200_000  # ~7 MB sem nenhum fechamento
        inicio = time.monotonic()
        assert eventos_jsonld(hostil) == []
        assert time.monotonic() - inicio < 2


class TestDadosAbsurdos:
    def test_titulo_gigante_e_cortado(self):
        r = Radar()
        r.rodar(FonteFixa([anuncio(titulo="A" * 10_000)], confiavel=False))
        assert len(r.est.fila[0].evento.titulo) == 200
        assert len(r.conversa.pedidos[0][1]) < 4096

    def test_data_em_2099_e_recusada(self):
        r = Radar(links={"https://x": anuncio(inicio=datetime.fromisoformat("2099-01-01T19:00:00-03:00"), fim=None)})
        r.rodar(chegando=[mensagem("https://x")])
        assert r.est.fila == [] and "inválidos" in r.conversa.respostas[0][1]


class TestFlood:
    def test_no_maximo_3_links_por_mensagem(self):
        links = {f"https://s/{i}": anuncio(url=f"https://s/{i}", inicio=em(10 + i, 19), fim=em(10 + i, 21)) for i in range(10)}
        r = Radar(links=links)
        r.rodar(chegando=[mensagem(" ".join(links))])
        assert len(r.est.fila) == MAX_LINKS_POR_MENSAGEM

    def test_cota_por_hora_e_um_aviso_so(self):
        links = {f"https://s/{i}": anuncio(url=f"https://s/{i}", inicio=em(10 + i, 19), fim=em(10 + i, 21)) for i in range(10)}
        r = Radar(links=links)
        r.rodar(chegando=[mensagem(u, update_id=n) for n, u in enumerate(links)])
        assert len(r.est.fila) == SUGESTOES_POR_HORA
        avisos = [t for _, t in r.conversa.respostas if "muitas sugestões" in t]
        assert len(avisos) == 1

    def test_boas_vindas_uma_vez_por_hora(self):
        r = Radar()
        r.rodar(chegando=[mensagem("oi", update_id=n) for n in range(20)])
        assert len(r.conversa.respostas) == 1


class TestEscapeDeHtml:
    def test_link_ilegivel_repassado_escapado(self):
        r = Radar()
        r.rodar(chegando=[mensagem("https://x.com/<b>oi</b>&a")])
        repasse = [t for chat, t in r.conversa.respostas if chat == REVISOR][0]
        assert "&lt;b&gt;" in repasse and "<b>oi" not in repasse

    def test_titulo_na_aprovacao_escapado(self):
        r = Radar(links={"https://s/1": anuncio(url="https://s/1", titulo="P&D <script>")})
        r.rodar(chegando=[mensagem("https://s/1")])
        r.rodar(chegando=[clique("aprovar", r.est.fila[0].evento.id, update_id=2)])
        aviso = [t for chat, t in r.conversa.respostas if "entrou no Radar" in t][0]
        assert "P&amp;D &lt;script&gt;" in aviso


class CanalMeioQuebrado(CanalFalso):
    """Recusa Posts com "quebra" no texto, como o Telegram recusaria uma mensagem inválida."""

    def publicar(self, texto, resposta_a=None):
        if "quebra" in texto:
            raise ErroTelegram("sendMessage: Bad Request")
        return super().publicar(texto, resposta_a)


class TestFalhaIsolada:
    def test_um_post_que_falha_nao_trava_os_outros(self):
        canal, est = CanalMeioQuebrado(), estado.Estado()
        fonte = FonteFixa([anuncio(titulo="quebra", url="https://a"),
                           anuncio(titulo="ok", url="https://b", inicio=em(13, 19), fim=em(13, 21))])
        ciclo.coletar([fonte], httpx.Client(), Saidas(canal, ConversaFalsa(), REVISOR), est, em(1, 12))
        assert {e.titulo: e.post_id is not None for e in est.eventos} == {"quebra": False, "ok": True}

    def test_persiste_logo_apos_cada_post(self):
        chamadas = []
        saidas = Saidas(CanalFalso(), ConversaFalsa(), REVISOR, persistir=lambda: chamadas.append(1))
        fonte = FonteFixa([anuncio(url="https://a"), anuncio(url="https://b", inicio=em(13, 19), fim=em(13, 21))])
        ciclo.coletar([fonte], httpx.Client(), saidas, estado.Estado(), em(1, 12))
        assert len(chamadas) >= 2
