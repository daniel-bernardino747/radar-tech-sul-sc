import json

import httpx
import pytest

from radar.telegram import CanalTelegram, ErroTelegram


def canal_com(membro: dict) -> CanalTelegram:
    def responder(req: httpx.Request) -> httpx.Response:
        metodo = req.url.path.rsplit("/", 1)[-1]
        resultado = {
            "getMe": {"id": 42, "username": "radar_bot"},
            "getChat": {"id": -100, "title": "Radar Tech Sul SC"},
            "getChatMember": membro,
        }[metodo]
        return httpx.Response(200, text=json.dumps({"ok": True, "result": resultado}))

    return CanalTelegram("t", "@radar", httpx.Client(transport=httpx.MockTransport(responder)))


def test_verifica_admin_que_posta_e_edita():
    membro = {"status": "administrator", "can_post_messages": True, "can_edit_messages": True}
    assert canal_com(membro).verificar() == "Radar Tech Sul SC"


def test_bot_que_nao_e_admin_falha():
    with pytest.raises(ErroTelegram, match="administrador"):
        canal_com({"status": "left"}).verificar()


def test_admin_sem_permissao_de_editar_falha():
    with pytest.raises(ErroTelegram, match="editar"):
        canal_com({"status": "administrator", "can_post_messages": True}).verificar()


def test_token_invalido_falha():
    def responder(req):
        return httpx.Response(401, text=json.dumps({"ok": False, "description": "Unauthorized"}))

    canal = CanalTelegram("errado", "@radar", httpx.Client(transport=httpx.MockTransport(responder)))
    with pytest.raises(ErroTelegram, match="Unauthorized"):
        canal.verificar()
