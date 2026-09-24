"""Filtro de relevância das Fontes abertas: decide o que vale a pena mandar para a Fila de revisão.

Erra de propósito para o lado de deixar passar; quem decide de fato é o Revisor.
"""

import re

from radar.dominio import Anuncio
from radar.regiao import normalizar

TECH = [
    "tecnologia", "tech", "inovacao", "innovation", "startup", "startups", "software",
    "dev", "devs", "developer", "desenvolvedor", "desenvolvedores", "desenvolvimento de software",
    "programacao", "programador", "codigo", "code", "hackathon", "game jam", "games",
    "dados", "data", "ia", "inteligencia artificial", "machine learning", "cloud", "aws",
    "azure", "devops", "python", "java", "javascript", "react", "cyber", "ciberseguranca",
    "seguranca da informacao", "blockchain", "meetup", "ti", "hub", "ecossistema",
    "transformacao digital", "robotica", "automacao", "saas",
]

CURSO = ["curso", "formacao", "treinamento", "capacitacao", "certificacao", "mentoria", "imersao"]

_TECH = re.compile(r"\b(" + "|".join(re.escape(t) for t in TECH) + r")\b")
_CURSO = re.compile(r"\b(" + "|".join(re.escape(t) for t in CURSO) + r")\b")


def parece_tech(a: Anuncio) -> bool:
    texto = normalizar(f"{a.titulo} {a.organizador or ''}")
    return bool(_TECH.search(texto))


def parece_curso(a: Anuncio) -> bool:
    return bool(_CURSO.search(normalizar(a.titulo)))
