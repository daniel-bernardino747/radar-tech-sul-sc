"""Publicação no Canal via Bot API."""

from typing import Protocol

import httpx


class Canal(Protocol):
    def publicar(self, texto: str, resposta_a: int | None = None) -> int: ...

    def editar(self, post_id: int, texto: str) -> None: ...


class CanalTelegram:
    def __init__(self, token: str, chat_id: str, http: httpx.Client):
        self._base = f"https://api.telegram.org/bot{token}"
        self._chat_id = chat_id
        self._http = http

    def publicar(self, texto: str, resposta_a: int | None = None) -> int:
        corpo = {"chat_id": self._chat_id, "text": texto, **_FORMATO}
        if resposta_a:
            corpo["reply_parameters"] = {"message_id": resposta_a, "allow_sending_without_reply": True}
        return self._chamar("sendMessage", corpo)["message_id"]

    def editar(self, post_id: int, texto: str) -> None:
        try:
            self._chamar("editMessageText", {"chat_id": self._chat_id, "message_id": post_id, "text": texto, **_FORMATO})
        except ErroTelegram as erro:
            if "message is not modified" not in str(erro):
                raise

    def verificar(self) -> str:
        """Confirma, sem postar, que o bot pode publicar no Canal. Devolve o nome do Canal."""
        bot = self._chamar("getMe", {})
        canal = self._chamar("getChat", {"chat_id": self._chat_id})
        membro = self._chamar("getChatMember", {"chat_id": self._chat_id, "user_id": bot["id"]})
        if membro["status"] != "administrator" or not membro.get("can_post_messages"):
            raise ErroTelegram(f"@{bot['username']} precisa ser administrador do Canal com permissão de postar")
        if not membro.get("can_edit_messages"):
            raise ErroTelegram(f"@{bot['username']} precisa de permissão para editar mensagens no Canal")
        return canal.get("title") or str(self._chat_id)

    def _chamar(self, metodo: str, corpo: dict) -> dict:
        resposta = self._http.post(f"{self._base}/{metodo}", json=corpo)
        dado = resposta.json()
        if not dado.get("ok"):
            raise ErroTelegram(f"{metodo}: {dado.get('description')}")
        return dado["result"]


class CanalDeTeste:
    """Imprime em vez de publicar. Usado sem TELEGRAM_BOT_TOKEN."""

    def __init__(self):
        self._proximo = 0

    def publicar(self, texto: str, resposta_a: int | None = None) -> int:
        self._proximo += 1
        cabecalho = f"[post {self._proximo}]" + (f" (resposta a {resposta_a})" if resposta_a else "")
        print(f"{cabecalho}\n{texto}\n")
        return self._proximo

    def editar(self, post_id: int, texto: str) -> None:
        print(f"[edita post {post_id}]\n{texto}\n")


class ErroTelegram(Exception):
    pass


_FORMATO = {"parse_mode": "HTML", "link_preview_options": {"is_disabled": True}}
