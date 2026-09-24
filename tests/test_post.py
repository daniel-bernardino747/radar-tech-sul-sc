from conftest import anuncio, em

from radar.dominio import Evento, Status
from radar.post import quando, texto_post


def test_post_completo():
    e = Evento.de_anuncio(anuncio(preco="Gratuito", titulo="IA & <dados>"))
    texto = texto_post(e)
    assert "<b>IA &amp; &lt;dados&gt;</b>" in texto
    assert "📅 seg, 12/10 · 19:00–21:00" in texto
    assert "📍 CRIO - Centro de Inovação Criciúma, Criciúma" in texto
    assert "💰 Gratuito" in texto
    assert 'href="https://www.meetup.com/criciumaops/events/1/"' in texto


def test_evento_de_varios_dias_sem_horario():
    e = Evento.de_anuncio(anuncio(inicio=em(20, 0), fim=em(22, 0), tem_horario=False))
    assert quando(e) == "ter, 20/10 a qui, 22/10"


def test_curso_gratuito_e_sinalizado():
    texto = texto_post(Evento.de_anuncio(anuncio(curso=True, preco="Gratuito")))
    assert "🎓 Curso gratuito" in texto and "💰" not in texto


def test_online_e_cancelado():
    e = Evento.de_anuncio(anuncio(online=True, local=None, cidade=None))
    e.status = Status.CANCELADO
    texto = texto_post(e)
    assert texto.startswith("❌ <b>CANCELADO</b>") and "📍 Online" in texto
