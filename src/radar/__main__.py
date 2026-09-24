"""python -m radar: roda um ciclo e sai.

Variáveis de ambiente:
  TELEGRAM_BOT_TOKEN    token do bot; sem ele, nada é publicado nem salvo (só impresso)
  TELEGRAM_CANAL_ID     @usuario ou id numérico do Canal
  TELEGRAM_REVISOR_ID   id numérico do Revisor no Telegram; sem ele, a Fila acumula sem pedir revisão
  RADAR_ESTADO          caminho do arquivo de estado (padrão: estado/estado.json)
"""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

from radar import ciclo, estado, fontes
from radar.revisao import Saidas
from radar.telegram import CanalDeTeste, CanalTelegram, ConversaDeTeste, ConversaTelegram

USER_AGENT = "Mozilla/5.0 (compatible; RadarTechSulSC/0.1; +https://github.com/daniel-bernardino747/radar-tech-sul-sc)"


def main() -> int:
    caminho = Path(os.environ.get("RADAR_ESTADO", "estado/estado.json"))
    atual = estado.carregar(caminho)
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True) as http:
        saidas = _saidas(http)
        real = isinstance(saidas.canal, CanalTelegram)
        if real:
            print(f"Canal verificado: {saidas.canal.verificar()}")
        if saidas.revisor_id is None:
            print("TELEGRAM_REVISOR_ID ausente: a Fila de revisão acumula sem pedir revisão.", file=sys.stderr)
        try:
            falhas = ciclo.executar(fontes.todas(), http, saidas, atual, datetime.now(UTC))
        finally:
            # Em modo de teste os ids de Post são falsos; salvar corromperia o estado.
            if real:
                estado.salvar(atual, caminho)
    publicados = sum(e.post_id is not None for e in atual.eventos)
    print(f"{len(atual.eventos)} Eventos acompanhados, {publicados} com Post, {len(atual.fila)} na Fila de revisão.")
    return 1 if falhas else 0


def _saidas(http: httpx.Client) -> Saidas:
    revisor = os.environ.get("TELEGRAM_REVISOR_ID")
    revisor_id = int(revisor) if revisor else None
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN ausente: modo de teste, nada é publicado nem salvo.\n", file=sys.stderr)
        return Saidas(CanalDeTeste(), ConversaDeTeste(), revisor_id or 0)
    return Saidas(
        CanalTelegram(token, os.environ["TELEGRAM_CANAL_ID"], http),
        ConversaTelegram(token, http),
        revisor_id,
    )


if __name__ == "__main__":
    sys.exit(main())
