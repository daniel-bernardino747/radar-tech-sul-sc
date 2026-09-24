"""Estado persistido entre execuções: um JSON versionado no repositório (ADR 0001)."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from radar.dominio import Evento, ItemFila, Status


@dataclass
class Estado:
    eventos: list[Evento] = field(default_factory=list)
    fila: list[ItemFila] = field(default_factory=list)
    rejeitados: list[Evento] = field(default_factory=list)
    # Próximo update_id a pedir ao Telegram; o que vem antes já foi processado.
    offset_telegram: int = 0


def carregar(caminho: Path) -> Estado:
    if not caminho.exists():
        return Estado()
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    return Estado(
        eventos=[_evento(e) for e in bruto.get("eventos", [])],
        fila=[_item(i) for i in bruto.get("fila", [])],
        rejeitados=[_evento(e) for e in bruto.get("rejeitados", [])],
        offset_telegram=bruto.get("offset_telegram", 0),
    )


def salvar(estado: Estado, caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conteudo = {
        "offset_telegram": estado.offset_telegram,
        "eventos": [asdict(e) for e in _ordenados(estado.eventos)],
        "fila": [asdict(i) for i in sorted(estado.fila, key=lambda i: (i.evento.inicio, i.evento.id))],
        "rejeitados": [asdict(e) for e in _ordenados(estado.rejeitados)],
    }
    caminho.write_text(
        json.dumps(conteudo, ensure_ascii=False, indent=2, default=_serializar) + "\n",
        encoding="utf-8",
    )


def _ordenados(eventos: list[Evento]) -> list[Evento]:
    return sorted(eventos, key=lambda e: (e.inicio, e.id))


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


def _item(d: dict) -> ItemFila:
    return ItemFila(**{**d, "evento": _evento(d["evento"])})
