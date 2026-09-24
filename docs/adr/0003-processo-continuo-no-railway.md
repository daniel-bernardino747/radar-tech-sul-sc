---
status: accepted
supersedes: ADR 0001
---

# Processo contínuo no Railway, com estado num volume

Depois de usar o Radar de verdade, esperar até 1h para uma Aprovação virar Post (ou para o bot responder uma Sugestão) ficou inaceitável. O Radar passou a rodar como um processo Python sempre ligado no Railway: faz long polling na Bot API, então conversa, Aprovação e publicação acontecem em segundos. A coleta das Fontes caiu para duas vezes por dia (8h e 18h), e Lembretes e Agenda da semana são checados a cada minuto. O estado continua sendo um JSON, agora num volume do Railway em vez de commitado no repositório.

## Considered Options

- **Continuar no GitHub Actions** (ADR 0001): custo zero, mas a latência de até 1h era o problema.
- **Actions disparado por webhook** (Telegram → função → `repository_dispatch`): ainda levaria ~30-60s por clique, gastaria minutos de Actions a cada mensagem e exigiria um endpoint público só para traduzir a chamada.
- **VPS no Brasil**: resolveria também o bloqueio de IP de CRIO, Unesc e ACATE, mas exige operar servidor. Continua sendo o próximo passo se esse bloqueio passar a pesar.

## Consequences

- Um único loop faz tudo, para que nada mexa no estado ao mesmo tempo; durante a coleta (~1 min, 2x/dia) o bot não responde.
- Sem execução vermelha no Actions para avisar de problemas, falhas de Fonte e erros viram mensagem privada para o Revisor (no máximo uma por hora).
- Perde-se o histórico do estado no Git.
- O Railway não tem região no Brasil: CRIO, Unesc e ACATE continuam bloqueados.
- Custo: plano Hobby do Railway.
