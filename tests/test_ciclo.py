from dataclasses import dataclass, field

import httpx
from conftest import anuncio, em

from radar import ciclo, estado
from radar.dominio import Anuncio, Status
from radar.revisao import Saidas

REVISOR = 99
AGORA = em(1, 12)


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

    def link_do_post(self, post_id):
        return f"https://t.me/radar/{post_id}"

    def fixar(self, post_id):
        pass

    def desafixar(self, post_id):
        pass


@dataclass
class ConversaFalsa:
    chegando: list[dict] = field(default_factory=list)
    pedidos: list[tuple[str, str]] = field(default_factory=list)
    concluidos: list[tuple[int, str]] = field(default_factory=list)
    respostas: list[tuple[int, str]] = field(default_factory=list)
    offsets: list[int] = field(default_factory=list)

    def atualizacoes(self, offset, espera=0):
        self.offsets.append(offset)
        chegando, self.chegando = self.chegando, []
        return chegando

    def pedir_revisao(self, revisor_id, texto, item_id):
        self.pedidos.append((item_id, texto))
        return 1000 + len(self.pedidos)

    def concluir_revisao(self, revisor_id, mensagem_id, texto):
        self.concluidos.append((mensagem_id, texto))

    def responder(self, chat_id, texto):
        self.respostas.append((chat_id, texto))

    def confirmar_clique(self, callback_id, texto):
        pass


@dataclass
class Radar:
    """Um Radar com estado persistente entre rodadas e saídas falsas novas a cada rodada."""

    est: estado.Estado = field(default_factory=estado.Estado)
    links: dict[str, Anuncio] = field(default_factory=dict)

    def rodar(self, *fontes, chegando=(), revisor=REVISOR):
        self.canal, self.conversa = CanalFalso(), ConversaFalsa(chegando=list(chegando))
        saidas = Saidas(self.canal, self.conversa, revisor)
        return ciclo.executar(fontes, httpx.Client(), saidas, self.est, AGORA, ler=lambda h, u, f: self.links.get(u))


def clique(acao, item_id, de=REVISOR, update_id=1):
    return {"update_id": update_id, "callback_query": {"id": "c", "from": {"id": de}, "data": f"{acao}:{item_id}"}}


def mensagem(texto, de=7, update_id=1):
    return {"update_id": update_id, "message": {"chat": {"id": de, "type": "private"}, "from": {"id": de}, "text": texto}}


class TestFonteConfiavel:
    def test_evento_novo_e_publicado_uma_vez(self):
        r = Radar()
        r.rodar(FonteFixa([anuncio()]))
        assert len(r.canal.publicados) == 1 and "Kubernetes" in r.canal.publicados[0][0]
        r.rodar(FonteFixa([anuncio()]))
        assert r.canal.publicados == [] and r.canal.editados == []

    def test_mesmo_evento_em_duas_fontes_vira_um_post(self):
        r = Radar()
        crio = anuncio(url="https://crio/aws", titulo="Encontro AWS no CRIO", local="Centro de Inovação de Criciúma CRIO")
        r.rodar(FonteFixa([anuncio()]), FonteFixa([crio], id="crio"))
        assert len(r.canal.publicados) == 1
        assert len(r.est.eventos[0].urls) == 2

    def test_fora_da_regiao_nao_publica(self):
        r = Radar()
        r.rodar(FonteFixa([anuncio(cidade="Florianópolis")]))
        assert r.canal.publicados == []

    def test_curso_nao_publica(self):
        r = Radar()
        r.rodar(FonteFixa([anuncio(curso=True)]))
        assert r.canal.publicados == []

    def test_alteracao_de_data_edita_post_e_avisa_em_resposta(self):
        r = Radar()
        r.rodar(FonteFixa([anuncio()]))
        r.rodar(FonteFixa([anuncio(inicio=em(19, 19), fim=em(19, 21))]))
        assert r.canal.editados[0][0] == 1
        [(aviso, resposta_a)] = r.canal.publicados
        assert "Nova data" in aviso and resposta_a == 1

    def test_cancelamento_edita_e_avisa(self):
        r = Radar()
        r.rodar(FonteFixa([anuncio()]))
        r.rodar(FonteFixa([anuncio(cancelado=True)]))
        assert "CANCELADO" in r.canal.editados[0][1]
        assert r.est.eventos[0].status is Status.CANCELADO

    def test_anuncio_que_some_nao_cancela(self):
        r = Radar()
        r.rodar(FonteFixa([anuncio()]))
        r.rodar(FonteFixa([]))
        assert r.canal.publicados == [] and r.canal.editados == []
        assert r.est.eventos[0].status is Status.AGENDADO

    def test_fonte_quebrada_nao_derruba_as_outras(self):
        r = Radar()
        falhas = r.rodar(FonteQuebrada(), FonteFixa([anuncio()]))
        assert falhas == ["quebrada"] and len(r.canal.publicados) == 1


def aberta(*anuncios):
    return FonteFixa(list(anuncios), id="sympla", confiavel=False)


class TestFilaDeRevisao:
    def test_fonte_aberta_vai_para_a_fila_e_pede_revisao_uma_vez(self):
        r = Radar()
        r.rodar(aberta(anuncio()))
        assert r.canal.publicados == []
        [(item_id, texto)] = r.conversa.pedidos
        assert "Kubernetes" in texto and "Fonte aberta" in texto
        r.rodar(aberta(anuncio()))
        assert r.conversa.pedidos == [] and len(r.est.fila) == 1

    def test_aprovacao_publica_na_rodada_seguinte(self):
        r = Radar()
        r.rodar(aberta(anuncio()))
        item_id = r.est.fila[0].evento.id
        r.rodar(chegando=[clique("aprovar", item_id)])
        assert len(r.canal.publicados) == 1 and r.est.fila == []
        assert "Aprovado" in r.conversa.concluidos[0][1]
        assert r.est.offset_telegram == 2

    def test_rejeicao_e_permanente(self):
        r = Radar()
        r.rodar(aberta(anuncio()))
        r.rodar(chegando=[clique("rejeitar", r.est.fila[0].evento.id)])
        r.rodar(aberta(anuncio()))
        assert r.canal.publicados == [] and r.conversa.pedidos == [] and r.est.fila == []

    def test_so_o_revisor_decide(self):
        r = Radar()
        r.rodar(aberta(anuncio()))
        r.rodar(chegando=[clique("aprovar", r.est.fila[0].evento.id, de=123)])
        assert r.canal.publicados == [] and len(r.est.fila) == 1

    def test_anuncio_de_evento_ja_publicado_nao_vai_para_a_fila(self):
        r = Radar()
        r.rodar(FonteFixa([anuncio()]))
        r.rodar(aberta(anuncio(url="https://sympla/1", inicio=em(12, 19, 30))))
        assert r.conversa.pedidos == [] and r.est.fila == []
        assert "https://sympla/1" in r.est.eventos[0].urls

    def test_fonte_confiavel_resolve_item_da_fila(self):
        r = Radar()
        r.rodar(aberta(anuncio(url="https://sympla/1")))
        r.rodar(FonteFixa([anuncio()]))
        assert len(r.canal.publicados) == 1 and r.est.fila == []
        assert "Fonte confiável" in r.conversa.concluidos[0][1]

    def test_item_expira_quando_o_evento_passa(self):
        r = Radar()
        r.rodar(aberta(anuncio(inicio=em(1, 8), fim=em(1, 10))))
        assert r.est.fila == [] and r.conversa.pedidos == []
        # nem chegou a ser pedido: expirou na mesma rodada
        r2 = Radar()
        r2.rodar(aberta(anuncio()))
        r2.est.fila[0].evento.inicio = em(1, 8)
        r2.est.fila[0].evento.fim = em(1, 10)
        r2.rodar()
        assert r2.est.fila == [] and "Expirou" in r2.conversa.concluidos[0][1]

    def test_sem_revisor_a_fila_acumula(self):
        r = Radar()
        r.rodar(aberta(anuncio()), revisor=None)
        assert len(r.est.fila) == 1 and r.conversa.pedidos == []
        r.rodar()
        assert len(r.conversa.pedidos) == 1


class TestSugestao:
    def test_sugestao_valida_vai_para_a_fila(self):
        r = Radar(links={"https://sympla/x": anuncio(url="https://sympla/x")})
        r.rodar(chegando=[mensagem("olha esse: https://sympla/x")])
        assert len(r.est.fila) == 1 and r.est.fila[0].sugerido_por == 7
        assert "revisão" in r.conversa.respostas[0][1]
        assert "Sugestão" in r.conversa.pedidos[0][1]

    def test_aprovacao_avisa_quem_sugeriu(self):
        r = Radar(links={"https://sympla/x": anuncio(url="https://sympla/x")})
        r.rodar(chegando=[mensagem("https://sympla/x")])
        r.rodar(chegando=[clique("aprovar", r.est.fila[0].evento.id, update_id=2)])
        assert (7, "✅ Sua sugestão entrou no Radar: CriciumaOps #14 — Kubernetes na prática") in r.conversa.respostas

    def test_sugestao_do_revisor_publica_direto(self):
        r = Radar(links={"https://sympla/x": anuncio(url="https://sympla/x")})
        r.rodar(chegando=[mensagem("https://sympla/x", de=REVISOR)])
        assert len(r.canal.publicados) == 1 and r.est.fila == []

    def test_link_ilegivel_avisa_e_repassa_ao_revisor(self):
        r = Radar()
        r.rodar(chegando=[mensagem("https://instagram.com/p/abc")])
        assert "Não consegui" in r.conversa.respostas[0][1]
        assert (REVISOR, "💡 Sugestão que não consegui ler: https://instagram.com/p/abc") in r.conversa.respostas

    def test_fora_da_regiao_explica(self):
        r = Radar(links={"https://x": anuncio(url="https://x", cidade="Florianópolis")})
        r.rodar(chegando=[mensagem("https://x")])
        assert "Sul de SC" in r.conversa.respostas[0][1] and r.est.fila == []

    def test_curso_explica(self):
        r = Radar(links={"https://x": anuncio(url="https://x", curso=True)})
        r.rodar(chegando=[mensagem("https://x")])
        assert "Cursos" in r.conversa.respostas[0][1]

    def test_mensagem_sem_link_recebe_boas_vindas_com_id(self):
        r = Radar()
        r.rodar(chegando=[mensagem("/start", de=555)])
        assert "<code>555</code>" in r.conversa.respostas[0][1]


def test_estado_sobrevive_ida_e_volta(tmp_path):
    r = Radar()
    r.rodar(FonteFixa([anuncio()]), aberta(anuncio(url="https://s/2", inicio=em(20, 19), fim=em(20, 21))))
    r.rodar(aberta(anuncio(url="https://s/3", local="SATC", inicio=em(21, 19), fim=em(21, 21))))
    r.rodar(chegando=[clique("rejeitar", r.est.fila[-1].evento.id)])
    arquivo = tmp_path / "estado.json"
    estado.salvar(r.est, arquivo)
    carregado = estado.carregar(arquivo)
    assert carregado == r.est
    assert carregado.fila and carregado.rejeitados and carregado.offset_telegram == 2
