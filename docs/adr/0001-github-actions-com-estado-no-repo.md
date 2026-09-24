# Rodar no GitHub Actions, em Python, com estado no repositório

O Radar roda como um job agendado do GitHub Actions (a cada ~1h), escrito em Python, sem servidor sempre ligado. Aprovações da Fila de revisão e Sugestões chegam como botões e mensagens no Telegram, mas só são processadas na execução seguinte (lendo as atualizações pendentes da Bot API, retidas por 24h). O estado (Posts publicados, Status, Rejeições) fica num arquivo versionado no próprio repositório. Escolhemos isso por custo zero e ausência de infraestrutura, aceitando até ~1h de atraso entre uma Aprovação e o Post, o que basta para um único Revisor.

## Considered Options

- **Serverless com webhook (Cloudflare Workers + D1)**: resposta imediata e banco de verdade, mas limita linguagem e scraping (sem bibliotecas nativas, pouco tempo de CPU).
- **VPS com bot sempre ligado + SQLite**: flexível e com resposta imediata, mas exige operar um servidor. É o caminho natural de migração se o volume ou o scraping (ex.: navegador headless) pedirem.

## Consequences

- Nenhuma Fonte levantada em 2026-09 exige navegador headless; se isso mudar, reavaliar a migração para VPS.
- Duas execuções simultâneas podem conflitar no arquivo de estado; o workflow deve impedir concorrência.
