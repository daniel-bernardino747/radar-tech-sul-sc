FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

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

CMD ["/app/.venv/bin/python", "-m", "radar"]
