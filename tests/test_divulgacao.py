from dataclasses import dataclass, field

from conftest import anuncio, em

from radar.divulgacao import enviar_lembretes, publicar_agenda
from radar.dominio import Evento, Status
from radar.estado import Estado


@dataclass
class CanalFalso:
    publicados: list[tuple[str, int | None]] = field(default_factory=list)
    fixados: set[int] = field(default_factory=set)

    def publicar(self, texto, resposta_a=None):
        self.publicados.append((texto, resposta_a))
        return 500 + len(self.publicados)

    def editar(self, post_id, texto):
        pass

    def link_do_post(self, post_id):
        return f"https://t.me/radar/{post_id}"

    def fixar(self, post_id):
        self.fixados.add(post_id)

    def desafixar(self, post_id):
        self.fixados.discard(post_id)


def publicado(post_id=1, publicado_em=None, **campos) -> Evento:
    e = Evento.de_anuncio(anuncio(**campos))
    e.post_id = post_id
    e.publicado_em = publicado_em or em(1, 9)
    return e


class TestLembrete:
    # 15/10/2026 é quinta; 12/10 e 19/10 são segundas.

    def test_na_vespera_a_partir_das_10h(self):
        e = publicado(inicio=em(15, 19), fim=em(15, 21))
        est, canal = Estado(eventos=[e]), CanalFalso()
        enviar_lembretes(est, canal, em(14, 9, 59))
        assert canal.publicados == []
        enviar_lembretes(est, canal, em(14, 10, 17))
        [(texto, resposta_a)] = canal.publicados
        assert resposta_a == 1 and "é amanhã!" in texto and "Kubernetes" in texto
        enviar_lembretes(est, canal, em(14, 11, 17))
        assert len(canal.publicados) == 1

    def test_evento_de_segunda_lembra_na_sexta(self):
        e = publicado(inicio=em(19, 19), fim=em(19, 21))
        est, canal = Estado(eventos=[e]), CanalFalso()
        enviar_lembretes(est, canal, em(16, 9, 17))  # sexta antes das 10h
        assert canal.publicados == []
        enviar_lembretes(est, canal, em(16, 10, 17))
        assert "na segunda, 19/10!" in canal.publicados[0][0]

    def test_post_recente_dispensa_lembrete(self):
        e = publicado(inicio=em(15, 19), publicado_em=em(14, 8))
        canal = CanalFalso()
        enviar_lembretes(Estado(eventos=[e]), canal, em(14, 10, 17))
        assert canal.publicados == []

    def test_cancelado_ou_ja_comecou_nao_lembra(self):
        cancelado = publicado(inicio=em(15, 19))
        cancelado.status = Status.CANCELADO
        comecou = publicado(post_id=2, inicio=em(14, 9), fim=em(16, 18))
        canal = CanalFalso()
        enviar_lembretes(Estado(eventos=[cancelado, comecou]), canal, em(14, 10, 17))
        assert canal.publicados == []

    def test_alteracao_de_data_permite_novo_lembrete(self):
        from radar.dominio import aplicar

        e = publicado(inicio=em(15, 19), fim=em(15, 21))
        e.lembrete_enviado = True
        aplicar(e, anuncio(inicio=em(22, 19), fim=em(22, 21)))
        canal = CanalFalso()
        enviar_lembretes(Estado(eventos=[e]), canal, em(21, 10, 17))
        assert len(canal.publicados) == 1


class TestAgendaDaSemana:
    def test_segunda_de_manha_lista_a_semana_com_links(self):
        dentro = publicado(post_id=7, titulo="Meetup A", inicio=em(14, 19), fim=em(14, 21))
        primeiro = publicado(post_id=3, titulo="Meetup B", inicio=em(12, 9), fim=em(12, 11))
        fora = publicado(post_id=9, titulo="Semana que vem", inicio=em(19, 19), fim=em(19, 21))
        cancelado = publicado(post_id=4, titulo="Cancelado", inicio=em(13, 19), fim=em(13, 21))
        cancelado.status = Status.CANCELADO
        est, canal = Estado(eventos=[dentro, fora, cancelado, primeiro]), CanalFalso()

        publicar_agenda(est, canal, em(12, 7, 59))
        assert canal.publicados == []
        publicar_agenda(est, canal, em(12, 8, 17))
        [(texto, _)] = canal.publicados
        assert texto.startswith("🗓️ <b>Agenda da semana</b> (12/10 a 18/10)")
        assert texto.index("Meetup B") < texto.index("Meetup A")
        assert 'href="https://t.me/radar/7"' in texto and "(Criciúma)" in texto
        assert "Semana que vem" not in texto and "Cancelado" not in texto
        assert est.ultima_agenda == "2026-10-12"

        publicar_agenda(est, canal, em(12, 9, 17))
        assert len(canal.publicados) == 1

    def test_so_na_segunda(self):
        est, canal = Estado(eventos=[publicado(inicio=em(14, 19))]), CanalFalso()
        publicar_agenda(est, canal, em(13, 8, 17))
        assert canal.publicados == [] and est.ultima_agenda is None

    def test_semana_vazia_nao_publica(self):
        est, canal = Estado(), CanalFalso()
        publicar_agenda(est, canal, em(12, 8, 17))
        assert canal.publicados == [] and est.ultima_agenda == "2026-10-12"

    def test_fixa_a_nova_e_desafixa_a_anterior(self):
        est = Estado(eventos=[publicado(post_id=1, inicio=em(14, 19)), publicado(post_id=2, inicio=em(21, 19))])
        canal = CanalFalso()
        publicar_agenda(est, canal, em(12, 8, 17))
        assert canal.fixados == {501} and est.agenda_fixada == 501
        publicar_agenda(est, canal, em(19, 8, 17))
        assert canal.fixados == {502} and est.agenda_fixada == 502

    def test_semana_vazia_desafixa_a_anterior(self):
        est = Estado(eventos=[publicado(inicio=em(14, 19))])
        canal = CanalFalso()
        publicar_agenda(est, canal, em(12, 8, 17))
        publicar_agenda(est, canal, em(19, 8, 17))
        assert canal.fixados == set() and est.agenda_fixada is None
