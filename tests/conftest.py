from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from radar.dominio import Anuncio

FUSO = ZoneInfo("America/Sao_Paulo")
FIXTURES = Path(__file__).parent / "fixtures"


def em(dia: int, hora: int, minuto: int = 0, mes: int = 10) -> datetime:
    return datetime(2026, mes, dia, hora, minuto, tzinfo=FUSO)


def anuncio(**campos) -> Anuncio:
    padrao = dict(
        fonte="meetup-criciumaops",
        url="https://www.meetup.com/criciumaops/events/1/",
        titulo="CriciumaOps #14 — Kubernetes na prática",
        inicio=em(12, 19),
        fim=em(12, 21),
        local="CRIO - Centro de Inovação Criciúma",
        cidade="Criciúma",
        organizador="AWS User Group Criciúma",
    )
    return Anuncio(**(padrao | campos))


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES
