# Imagens fixadas por digest (python:3.13-slim e uv:0.11 em 2026-09-24); atualizar de propósito.
FROM python:3.13-slim@sha256:8d9d0b8bcf6506481eae4907c18f5e3e7902e629f5f6d684f9e7c32e85e3ddf0

COPY --from=ghcr.io/astral-sh/uv@sha256:77280f2f771df71f90786c314fe1bbc1e023feac652969bbf139c280babf2eb7 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
# Semente do primeiro boot: o estado da época do GitHub Actions (ADR 0003).
COPY estado ./estado
RUN uv sync --frozen --no-dev

# Roda como root de propósito: o Railway monta o volume /data como root, e um usuário sem
# privilégios não conseguiria gravar o estado. O processo não abre porta nenhuma.
CMD ["/app/.venv/bin/python", "-m", "radar"]
