"""A Região: municípios da AMREC, AMUREL e AMESC."""

import re
import unicodedata

AMREC = {
    "Balneário Rincão", "Cocal do Sul", "Criciúma", "Forquilhinha", "Içara",
    "Lauro Müller", "Morro da Fumaça", "Nova Veneza", "Orleans", "Siderópolis",
    "Treviso", "Urussanga",
}

AMUREL = {
    "Armazém", "Braço do Norte", "Capivari de Baixo", "Grão Pará", "Gravatal",
    "Imaruí", "Imbituba", "Jaguaruna", "Laguna", "Pedras Grandes",
    "Pescaria Brava", "Rio Fortuna", "Sangão", "Santa Rosa de Lima",
    "São Ludgero", "São Martinho", "Treze de Maio", "Tubarão",
}

AMESC = {
    "Araranguá", "Balneário Arroio do Silva", "Balneário Gaivota", "Ermo",
    "Jacinto Machado", "Maracajá", "Meleiro", "Morro Grande", "Passo de Torres",
    "Praia Grande", "Santa Rosa do Sul", "São João do Sul", "Sombrio",
    "Timbé do Sul", "Turvo",
}


def normalizar(texto: str) -> str:
    """Minúsculas, sem acento, sem pontuação e com espaços colapsados."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).split())


_MUNICIPIOS = {normalizar(m) for m in AMREC | AMUREL | AMESC}


def eh_da_regiao(cidade: str | None) -> bool:
    """Aceita a UF junto ("Criciúma / SC", "Tubarão-SC"), que algumas Fontes incluem."""
    return cidade is not None and normalizar(cidade).removesuffix(" sc") in _MUNICIPIOS
