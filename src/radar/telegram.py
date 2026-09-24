"""Bot API: publicação no Canal e conversa privada (Revisor e Sugestões)."""

from typing import Protocol

import httpx


class Canal(Protocol):
    def publicar(self, texto: str, resposta_a: int | None = None) -> int: ...

    def editar(self, post_id: int, texto: str) -> None: ...

    def link_do_post(self, post_id: int) -> str: ...

    def fixar(self, post_id: int) -> None: ...

    def desafixar(self, post_id: int) -> None: ...


class Conversa(Protocol):
    """Conversas privadas com o bot: o Revisor decide a Fila, qualquer pessoa manda Sugestões."""

    def atualizacoes(self, offset: int, espera: int = 0) -> list[dict]:
        """Long polling: segura a conexão até `espera` segundos aguardando mensagens."""
        ...

    def pedir_revisao(self, revisor_id: int, texto: str, item_id: str) -> int: ...

    def concluir_revisao(self, revisor_id: int, mensagem_id: int, texto: str) -> None: ...

    def responder(self, chat_id: int, texto: str) -> None: ...

    def confirmar_clique(self, callback_id: str, texto: str) -> None: ...


class ErroTelegram(Exception):
    pass


class _Bot:
    def __init__(self, token: str, http: httpx.Client):
        self._base = f"https://api.telegram.org/bot{token}"
        self._http = http

    def _chamar(self, metodo: str, corpo: dict, timeout: float | None = None) -> dict | list | bool:
        extra = {"timeout": timeout} if timeout else {}
        resposta = self._http.post(f"{self._base}/{metodo}", json=corpo, **extra)
        dado = resposta.json()
        if not dado.get("ok"):
            raise ErroTelegram(f"{metodo}: {dado.get('description')}")
        return dado["result"]

    def _editar(self, chat_id: int | str, mensagem_id: int, texto: str) -> None:
        try:
            self._chamar("editMessageText", {"chat_id": chat_id, "message_id": mensagem_id, "text": texto, **_FORMATO})
        except ErroTelegram as erro:
            if "message is not modified" not in str(erro):
                raise


class CanalTelegram(_Bot):
    def __init__(self, token: str, chat_id: str, http: httpx.Client):
        super().__init__(token, http)
        self._chat_id = chat_id

    def publicar(self, texto: str, resposta_a: int | None = None) -> int:
        corpo = {"chat_id": self._chat_id, "text": texto, **_FORMATO}
        if resposta_a:
            corpo["reply_parameters"] = {"message_id": resposta_a, "allow_sending_without_reply": True}
        return self._chamar("sendMessage", corpo)["message_id"]

    def editar(self, post_id: int, texto: str) -> None:
        self._editar(self._chat_id, post_id, texto)

    def link_do_post(self, post_id: int) -> str:
        canal = str(self._chat_id)
        if canal.startswith("@"):
            return f"https://t.me/{canal[1:]}/{post_id}"
        return f"https://t.me/c/{canal.removeprefix('-100')}/{post_id}"  # Canal privado

    def fixar(self, post_id: int) -> None:
        self._chamar("pinChatMessage", {"chat_id": self._chat_id, "message_id": post_id, "disable_notification": True})

    def desafixar(self, post_id: int) -> None:
        try:
            self._chamar("unpinChatMessage", {"chat_id": self._chat_id, "message_id": post_id})
        except ErroTelegram:
            pass  # já desafixada à mão, ou apagada

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


class ConversaTelegram(_Bot):
    def atualizacoes(self, offset: int, espera: int = 0) -> list[dict]:
        corpo = {"offset": offset, "timeout": espera, "allowed_updates": ["message", "callback_query"]}
        return self._chamar("getUpdates", corpo, timeout=espera + 15)

    def pedir_revisao(self, revisor_id: int, texto: str, item_id: str) -> int:
        botoes = [[
            {"text": "✅ Aprovar", "callback_data": f"aprovar:{item_id}"},
            {"text": "❌ Rejeitar", "callback_data": f"rejeitar:{item_id}"},
        ]]
        corpo = {"chat_id": revisor_id, "text": texto, "reply_markup": {"inline_keyboard": botoes}, **_FORMATO}
        return self._chamar("sendMessage", corpo)["message_id"]

    def concluir_revisao(self, revisor_id: int, mensagem_id: int, texto: str) -> None:
        self._editar(revisor_id, mensagem_id, texto)  # editar sem reply_markup remove os botões

    def responder(self, chat_id: int, texto: str) -> None:
        self._chamar("sendMessage", {"chat_id": chat_id, "text": texto, **_FORMATO})

    def confirmar_clique(self, callback_id: str, texto: str) -> None:
        try:
            self._chamar("answerCallbackQuery", {"callback_query_id": callback_id, "text": texto})
        except ErroTelegram:
            pass  # cliques com mais de alguns minutos expiram; a decisão vale mesmo assim


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

    def link_do_post(self, post_id: int) -> str:
        return f"https://t.me/teste/{post_id}"

    def fixar(self, post_id: int) -> None:
        print(f"[fixa post {post_id}]\n")

    def desafixar(self, post_id: int) -> None:
        print(f"[desafixa post {post_id}]\n")


class ConversaDeTeste:
    """Sem Telegram: não recebe nada e imprime o que iria para o Revisor."""

    def __init__(self):
        self._proximo = 0

    def atualizacoes(self, offset: int, espera: int = 0) -> list[dict]:
        return []

    def pedir_revisao(self, revisor_id: int, texto: str, item_id: str) -> int:
        self._proximo += 1
        print(f"[revisão {item_id}]\n{texto}\n")
        return self._proximo

    def concluir_revisao(self, revisor_id: int, mensagem_id: int, texto: str) -> None:
        print(f"[revisão concluída {mensagem_id}]\n{texto}\n")

    def responder(self, chat_id: int, texto: str) -> None:
        print(f"[resposta a {chat_id}] {texto}\n")

    def confirmar_clique(self, callback_id: str, texto: str) -> None:
        pass


_FORMATO = {"parse_mode": "HTML", "link_preview_options": {"is_disabled": True}}
