"""Infraestrutura do Radar no Railway, como código (ADR 0003).

Tudo o que o projeto tem no Railway está declarado aqui: o que sair deste arquivo é
removido no `railway config apply`. Em especial, NÃO remova o volume: ele guarda o estado.

    railway config plan    # mostra o que mudaria, sem mudar nada
    railway config apply   # aplica
"""

from railway_sdk import define_railway, github, preserve, project, service, volume

REGIAO = "us-east4-eqdc4a"  # US East; o Railway não tem região no Brasil


@define_railway
def main(ctx=None):
    dados = volume(
        "radar-tech-sul-sc-volume",
        alerts={"usage": {"80": {}, "95": {}, "100": {}}},
        allowOnlineResize=True,
        region=REGIAO,
        sizeMB=5000,
    )
    radar = service(
        "radar-tech-sul-sc",
        source=github("daniel-bernardino747/radar-tech-sul-sc", checkSuites=False),
        build={"builder": "DOCKERFILE", "dockerfilePath": "Dockerfile"},
        # Processo contínuo: se sair por qualquer motivo, volta. Uma réplica só, porque duas
        # disputariam as mensagens do bot (Conflict no getUpdates).
        deploy={"restartPolicyType": "ALWAYS"},
        replicas={REGIAO: 1},
        volumeMounts={"/data": dados},
        # preserve(): mantém o valor que já está no Railway, sem escrever segredo no repositório.
        env={
            "RADAR_ESTADO": preserve(),
            "RAILWAY_DEPLOYMENT_DRAINING_SECONDS": preserve(),
            "TELEGRAM_BOT_TOKEN": preserve(),
            "TELEGRAM_CANAL_ID": preserve(),
            "TELEGRAM_REVISOR_ID": preserve(),
        },
    )
    return project("radar-tech-sul-sc", resources=[radar, dados])
