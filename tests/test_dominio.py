from conftest import anuncio, em

from radar.dominio import Evento, Status, aplicar, eh_elegivel, mesmo_evento
from radar.regiao import eh_da_regiao


class TestRegiao:
    def test_cidades_das_tres_associacoes(self):
        assert eh_da_regiao("Criciúma")
        assert eh_da_regiao("TUBARAO")
        assert eh_da_regiao("Araranguá")

    def test_florianopolis_fica_fora(self):
        assert not eh_da_regiao("Florianópolis")
        assert not eh_da_regiao(None)

    def test_online_e_elegivel_presencial_fora_nao(self):
        assert eh_elegivel(anuncio(online=True, cidade=None, local=None))
        assert not eh_elegivel(anuncio(cidade="Florianópolis"))


class TestMesmoEvento:
    def test_mesma_url(self):
        e = Evento.de_anuncio(anuncio())
        assert mesmo_evento(anuncio(titulo="outro"), e)

    def test_titulos_diferentes_mesma_data_e_local_juntam(self):
        e = Evento.de_anuncio(anuncio())
        instagram_do_crio = anuncio(
            fonte="crio", url="https://crio/agenda/aws", titulo="Encontro AWS User Group no CRIO",
            local="Centro de Inovação de Criciúma (CRIO)", inicio=em(12, 19, 30), fim=None,
        )
        assert mesmo_evento(instagram_do_crio, e)

    def test_mesmo_local_mesmo_dia_horarios_distintos_nao_juntam(self):
        meetup = Evento.de_anuncio(anuncio())
        pitch = anuncio(url="https://crio/pitch", titulo="Pitch de startups", inicio=em(12, 14), fim=em(12, 17))
        assert not mesmo_evento(pitch, meetup)

    def test_sem_horario_na_duvida_nao_junta(self):
        e = Evento.de_anuncio(anuncio())
        assert not mesmo_evento(anuncio(url="https://outra", tem_horario=False), e)

    def test_locais_diferentes_nao_juntam(self):
        e = Evento.de_anuncio(anuncio())
        assert not mesmo_evento(anuncio(url="https://outra", local="Auditório da SATC"), e)


class TestAplicar:
    def test_mudanca_de_data_marca_alterado(self):
        e = Evento.de_anuncio(anuncio())
        m = aplicar(e, anuncio(inicio=em(19, 19), fim=em(19, 21)))
        assert set(m.relevantes) == {"inicio", "fim"}
        assert e.status is Status.ALTERADO
        assert e.inicio == em(19, 19)

    def test_detalhe_muda_sem_alterar_status(self):
        e = Evento.de_anuncio(anuncio())
        m = aplicar(e, anuncio(titulo="CriciumaOps #14 — Kubernetes (com palestrante novo)"))
        assert m.detalhes == ("titulo",) and not m.relevantes
        assert e.status is Status.AGENDADO

    def test_cancelamento_explicito(self):
        e = Evento.de_anuncio(anuncio())
        m = aplicar(e, anuncio(cancelado=True))
        assert m.cancelou and e.status is Status.CANCELADO

    def test_anuncio_secundario_so_enriquece(self):
        e = Evento.de_anuncio(anuncio(organizador=None))
        sympla = anuncio(url="https://sympla/x", inicio=em(12, 19, 30), preco="Gratuito", organizador="CriciumaOps")
        m = aplicar(e, sympla)
        assert not m.houve
        assert e.inicio == em(12, 19)
        assert (e.preco, e.organizador) == ("Gratuito", "CriciumaOps")
        assert e.urls == ["https://www.meetup.com/criciumaops/events/1/", "https://sympla/x"]

    def test_sem_mudanca(self):
        e = Evento.de_anuncio(anuncio())
        assert not aplicar(e, anuncio()).houve
