# Radar Tech Sul SC

Bot que acompanha as fontes de eventos de tecnologia do Sul de SC (Criciúma e região) e divulga tudo num único canal do Telegram.

> Vocabulário do domínio em [`CONTEXT.md`](./CONTEXT.md). Decisões de arquitetura em [`docs/adr/`](./docs/adr/).

## O problema

Criciúma tem uma cena tech ativa, mas a divulgação está espalhada. Cada comunidade anuncia no próprio canal:

- **AWS User Group CriciumaOps**: grupo de WhatsApp + Meetup, encontros a cada 30-45 dias no CRIO
- **Criciúma Dev**: Meetup + perfil de produtor na Sympla, meetups a cada ~45 dias (~110 pessoas)
- **CRIO (Centro de Inovação de Criciúma)**: agenda no site (com links para Sympla, Even3, Supertixs) + Instagram `@inovacaocrio`
- **SATC / Unesc**: portais institucionais (ex.: CyberSATC)
- **ACATE / SC Mais Inovação**: agendas estaduais, centradas em Florianópolis
- **Sympla**: busca por cidade, que mistura eventos de tech com todo o resto

Para ficar sabendo de tudo, hoje é preciso estar em todos esses canais. Quem não está num grupo específico simplesmente não fica sabendo.

## A proposta

Um sistema que:

1. **Coleta**: consulta periodicamente as Fontes (Meetup, Sympla, agendas institucionais) e recebe Sugestões por link
2. **Filtra**: mantém só Eventos de tecnologia na Região (AMREC + AMUREL + AMESC); cursos pagos ficam fora
3. **Normaliza**: extrai título, data, horário, local, organizador, preço e link de inscrição
4. **Deduplica**: vários Anúncios do mesmo Evento viram um Post só (mesma data + local + horário sobreposto; na dúvida, não junta)
5. **Revisa**: Anúncios de Fontes abertas passam por uma Fila de revisão antes de publicar
6. **Divulga**: publica no Canal, edita o Post quando o Evento muda, manda Lembrete na véspera e a Agenda da semana às segundas

## Por que Telegram (por enquanto)

Bots são nativos no Telegram: a Bot API é gratuita e oficial, sem aprovação nem risco de banimento. No WhatsApp, automação exige a Business API (paga e burocrática) ou soluções não oficiais que podem derrubar o número. Começamos pelo Telegram e reavaliamos o WhatsApp depois que o produto provar valor.

Formato: **canal** (só o bot publica) com **grupo de discussão vinculado** para conversa.

## Fontes do MVP

| Fonte | Tipo | Como ler |
|---|---|---|
| Meetup CriciumaOps | confiável | iCal do grupo |
| Meetup Criciúma Dev | confiável | iCal do grupo |
| Agenda do CRIO | confiável | HTML, seguindo os links para Sympla/Even3/Supertixs |
| Portal de eventos da SATC | confiável | HTML/XHR, com o RSS da UniSATC como reserva |
| Sympla, páginas de cidade (Criciúma, Tubarão, Araranguá, Içara) | aberta | JSON embutido na página |
| Agenda da ACATE | aberta | HTML |
| RSS de notícias da Unesc | aberta | RSS |
| Sugestão por link (conversa privada com o bot) | aberta | segue o link |

Fontes **confiáveis** são publicadas automaticamente. Fontes **abertas** passam pela Fila de revisão.

Fora do MVP: grupo de WhatsApp e Instagram (ver [ADR 0002](./docs/adr/0002-sem-whatsapp-e-instagram-como-fonte.md)), SC Mais Inovação (fora do ar em 2026-09), perfil de produtor do Criciúma Dev na Sympla (carrega via JS; já coberto por outras Fontes).

Nenhuma Fonte tem API pública útil para descoberta: a API da Sympla só lista eventos do próprio produtor, e a do Meetup exige Meetup Pro. Os dados da Sympla incluem e-mail de organizadores, que devem ser descartados na coleta.

## Escopo do MVP

- [ ] Coletor por Fonte (tabela acima): feito para os dois grupos do Meetup
- [x] Modelo de Evento normalizado, com Status (agendado / alterado / cancelado)
- [ ] Filtro de relevância (tech + Região, sem cursos)
- [x] Deduplicação entre Anúncios
- [ ] Fila de revisão no chat privado com o bot (aprovar/rejeitar; rejeição permanente; expira após a data)
- [ ] Sugestão por link
- [x] Publicação no Canal, com edição do Post em alterações e cancelamentos
- [ ] Lembrete na véspera e Agenda da semana às segundas
- [x] Execução agendada no GitHub Actions (~1h), em Python, com estado no repositório ([ADR 0001](./docs/adr/0001-github-actions-com-estado-no-repo.md))

## Fora do escopo (por ora)

- WhatsApp (como Canal ou como Fonte)
- Site/agenda pública (pode vir depois, reaproveitando os mesmos dados)
- Cadastro manual de eventos por organizadores (a Sugestão por link cobre o caso simples)
- Cursos e treinamentos pagos
- Eventos fora da Região, inclusive em Florianópolis

## Como rodar

```sh
uv sync
uv run pytest
uv run python -m radar   # sem TELEGRAM_BOT_TOKEN: só imprime, não publica nem salva estado
```

Em produção, o workflow `.github/workflows/radar.yml` roda um ciclo por hora e commita `estado/estado.json`. Ele precisa dos secrets `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CANAL_ID`.

## Decisões tomadas

- **Canal ou grupo?** Canal + grupo de discussão vinculado.
- **Raio da Região?** Sul de SC: AMREC + AMUREL + AMESC. Florianópolis fica fora.
- **API/feed ou scraping?** Ver "Fontes do MVP".
- **Onde roda?** GitHub Actions, em Python ([ADR 0001](./docs/adr/0001-github-actions-com-estado-no-repo.md)).
