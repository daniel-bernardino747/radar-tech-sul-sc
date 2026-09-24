"""python -m radar: sobe o Radar como processo contínuo (ADR 0003).

    python -m radar            serviço: conversa ao vivo, coleta às 8h e 18h
    python -m radar --uma-vez  roda conversa, coleta e divulgação uma vez e sai

Sem TELEGRAM_BOT_TOKEN, roda uma vez em modo de teste: imprime em vez de publicar e não salva.

Variáveis de ambiente:
  TELEGRAM_BOT_TOKEN    token do bot
  TELEGRAM_CANAL_ID     @usuario ou id numérico do Canal
  TELEGRAM_REVISOR_ID   id numérico do Revisor no Telegram; sem ele, a Fila acumula sem pedir revisão
  RADAR_ESTADO          arquivo de estado (padrão: estado/estado.json, fora do Git; no Railway, /data/estado.json)
"""

import os
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

from radar import ciclo, estado, fontes
from radar.revisao import Saidas
from radar.servico import Servico
from radar.telegram import CanalDeTeste, CanalTelegram, ConversaDeTeste, ConversaTelegram

USER_AGENT = "Mozilla/5.0 (compatible; RadarTechSulSC/0.1; +https://github.com/daniel-bernardino747/radar-tech-sul-sc)"


def main() -> int:
    caminho = Path(os.environ.get("RADAR_ESTADO", "estado/estado.json"))
    if erro := checar_volume(caminho, os.environ):
        print(erro, file=sys.stderr)
        return 2

    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True) as http:
        saidas = _saidas(http)
        if not isinstance(saidas.canal, CanalTelegram):
            return _uma_vez(saidas, http, caminho, salvar=False)
        print(f"Canal verificado: {saidas.canal.verificar()}", flush=True)
        if saidas.revisor_id is None:
            print("TELEGRAM_REVISOR_ID ausente: a Fila de revisão acumula sem pedir revisão.", file=sys.stderr)
        if "--uma-vez" in sys.argv:
            return _uma_vez(saidas, http, caminho, salvar=True)
        servico = Servico(fontes.todas(), http, saidas, caminho)
        # O Railway encerra com SIGTERM a cada deploy: o loop termina o passo em curso (no
        # máximo o tempo do long polling) e sai, sem cortar um envio no meio.
        signal.signal(signal.SIGTERM, lambda *_: setattr(servico, "parar", True))
        servico.rodar()
    return 0


def _uma_vez(saidas: Saidas, http: httpx.Client, caminho: Path, salvar: bool) -> int:
    atual = estado.carregar(caminho)
    try:
        falhas = ciclo.executar(fontes.todas(), http, saidas, atual, datetime.now(UTC))
    finally:
        # Em modo de teste os ids de Post são falsos; salvar corromperia o estado.
        if salvar:
            estado.salvar(atual, caminho)
    publicados = sum(e.post_id is not None for e in atual.eventos)
    print(f"{len(atual.eventos)} Eventos acompanhados, {publicados} com Post, {len(atual.fila)} na Fila de revisão.")
    return 1 if falhas else 0


def checar_volume(caminho: Path, ambiente) -> str | None:
    """No Railway, o estado precisa estar num volume: fora dele, some a cada deploy (e sem
    volume o Railway sobrepõe a instância nova à antiga, e duas leem o bot ao mesmo tempo)."""
    if "RAILWAY_ENVIRONMENT" not in ambiente:
        return None
    volume = ambiente.get("RAILWAY_VOLUME_MOUNT_PATH")
    if not volume:
        return ("Nenhum volume montado neste serviço do Railway: o estado se perderia a cada deploy. "
                "Crie um volume em /data (Settings → Volumes) e mantenha RADAR_ESTADO=/data/estado.json.")
    if not caminho.resolve().is_relative_to(Path(volume).resolve()):
        return f"RADAR_ESTADO ({caminho}) está fora do volume montado em {volume}: o estado se perderia a cada deploy."
    return None


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
