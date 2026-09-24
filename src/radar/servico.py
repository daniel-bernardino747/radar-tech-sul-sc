"""O Radar como processo sempre ligado (ADR 0003).

Um único loop, para que nada mexa no estado ao mesmo tempo:
1. roda o que estiver na hora (coleta às 8h e 18h; Lembretes e Agenda sempre);
2. espera mensagens do Telegram por até ESPERA segundos (long polling) e as atende;
3. grava o estado se algo mudou.
"""

import time as relogio_do_sistema
import traceback
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, time, timedelta
from html import escape
from pathlib import Path

import httpx

from radar import ciclo, estado
from radar.dominio import FUSO
from radar.fontes import Fonte
from radar.fontes.links import ler_link
from radar.revisao import Limites, Saidas, avisar

HORARIOS_DE_COLETA = (time(8), time(18))
ESPERA = 25  # segundos de long polling; também é o intervalo máximo entre checagens de Lembrete e Agenda
INTERVALO_ENTRE_ALERTAS = timedelta(hours=1)
PAUSA_APOS_ERRO = 10


def ultimo_horario_de_coleta(agora: datetime) -> datetime:
    local = agora.astimezone(FUSO)
    candidatos = (
        datetime.combine(local.date() - timedelta(days=d), h, FUSO) for d in (0, 1) for h in HORARIOS_DE_COLETA
    )
    return max(c for c in candidatos if c <= local)


def coleta_pendente(ultima: datetime | None, agora: datetime) -> bool:
    """Sem coleta registrada, coleta já; senão, quando passou um horário desde a última."""
    return ultima is None or ultima < ultimo_horario_de_coleta(agora)


class Servico:
    def __init__(
        self,
        fontes: Iterable[Fonte],
        http: httpx.Client,
        saidas: Saidas,
        caminho: Path,
        agora: Callable[[], datetime] = lambda: datetime.now(UTC),
        ler=ler_link,
    ):
        self.fontes = list(fontes)
        self.http = http
        self.saidas = saidas
        self.caminho = caminho
        self.agora = agora
        self.ler = ler
        self.estado = estado.carregar(caminho)
        self._salvo = estado.serializar(self.estado)
        self._ultimo_alerta: datetime | None = None
        self.limites = Limites()
        self.parar = False
        saidas.persistir = self.salvar

    def rodar(self) -> None:
        print(f"Radar no ar. Coletas às {', '.join(f'{h:%H:%M}' for h in HORARIOS_DE_COLETA)}.", flush=True)
        while not self.parar:
            try:
                self.passo()
            except Exception as erro:
                traceback.print_exc()
                self._alertar(f"⚠️ Erro no Radar: {escape(repr(erro))}")
                relogio_do_sistema.sleep(PAUSA_APOS_ERRO)
            finally:
                self.salvar()

    def passo(self, espera: int = ESPERA) -> None:
        agora = self.agora()
        if coleta_pendente(self.estado.ultima_coleta, agora):
            self.coletar(agora)
        ciclo.divulgar(self.estado, self.saidas, agora)
        self.salvar()
        ciclo.atender(self.estado, self.http, self.saidas, self.agora(), self.limites, self.ler, espera)

    def coletar(self, agora: datetime) -> None:
        print(f"Coletando ({agora.astimezone(FUSO):%d/%m %H:%M})...", flush=True)
        # Marca antes: se a coleta quebrar no meio, não é refeita a cada minuto, só no próximo horário.
        self.estado.ultima_coleta = agora
        self.salvar()
        falhas = ciclo.coletar(self.fontes, self.http, self.saidas, self.estado, agora)
        publicados = sum(e.post_id is not None for e in self.estado.eventos)
        print(f"{len(self.estado.eventos)} Eventos, {publicados} com Post, {len(self.estado.fila)} na Fila.", flush=True)
        if falhas:
            self._alertar(f"⚠️ Fontes que falharam na coleta: {', '.join(falhas)}. Detalhes no log do Railway.")

    def salvar(self) -> None:
        atual = estado.serializar(self.estado)
        if atual != self._salvo:
            estado.salvar(self.estado, self.caminho)
            self._salvo = atual

    def _alertar(self, texto: str) -> None:
        """Avisa o Revisor em privado, no máximo uma vez por hora para não inundar a conversa."""
        agora = self.agora()
        if self.saidas.revisor_id is None:
            return
        if self._ultimo_alerta and agora - self._ultimo_alerta < INTERVALO_ENTRE_ALERTAS:
            return
        self._ultimo_alerta = agora
        avisar(self.saidas, self.saidas.revisor_id, texto)
