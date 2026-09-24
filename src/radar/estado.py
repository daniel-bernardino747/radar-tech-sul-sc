"""Estado persistido entre execuções: um JSON versionado no repositório (ADR 0001)."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from radar.dominio import Evento, Status


@dataclass
class Estado:
    eventos: list[Evento] = field(default_factory=list)


def carregar(caminho: Path) -> Estado:
    if not caminho.exists():
        return Estado()
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    return Estado(eventos=[_evento(e) for e in bruto.get("eventos", [])])


def salvar(estado: Estado, caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    eventos = sorted(estado.eventos, key=lambda e: (e.inicio, e.id))
    conteudo = {"eventos": [asdict(e) for e in eventos]}
    caminho.write_text(
        json.dumps(conteudo, ensure_ascii=False, indent=2, default=_serializar) + "\n",
        encoding="utf-8",
    )


def _serializar(valor: object) -> str:
    if isinstance(valor, datetime):
        return valor.isoformat()
    raise TypeError(type(valor))


def _evento(d: dict) -> Evento:
    d = dict(d)
    d["inicio"] = datetime.fromisoformat(d["inicio"])
    d["fim"] = datetime.fromisoformat(d["fim"]) if d.get("fim") else None
    d["status"] = Status(d["status"])
    return Evento(**d)
