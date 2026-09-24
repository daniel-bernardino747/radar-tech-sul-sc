"""python -m radar: roda um ciclo e sai.

Variáveis de ambiente:
  TELEGRAM_BOT_TOKEN  token do bot; sem ele, os Posts só são impressos
  TELEGRAM_CANAL_ID   @usuario ou id numérico do Canal
  RADAR_ESTADO        caminho do arquivo de estado (padrão: estado/estado.json)
"""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

from radar import ciclo, estado, fontes
from radar.telegram import Canal, CanalDeTeste, CanalTelegram

USER_AGENT = "RadarTechSulSC/0.1 (+https://github.com/daniel-bernardino747/radar-tech-sul-sc)"


def main() -> int:
    caminho = Path(os.environ.get("RADAR_ESTADO", "estado/estado.json"))
    atual = estado.carregar(caminho)
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True) as http:
        canal = _canal(http)
        try:
            falhas = ciclo.executar(fontes.todas(), http, canal, atual, datetime.now(UTC))
        finally:
            # Em modo de teste os ids de Post são falsos; salvar corromperia o estado.
            if isinstance(canal, CanalTelegram):
                estado.salvar(atual, caminho)
    return 1 if falhas else 0


def _canal(http: httpx.Client) -> Canal:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN ausente: modo de teste, nada é publicado nem salvo.\n", file=sys.stderr)
        return CanalDeTeste()
    return CanalTelegram(token, os.environ["TELEGRAM_CANAL_ID"], http)


if __name__ == "__main__":
    sys.exit(main())
