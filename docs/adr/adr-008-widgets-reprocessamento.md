# ADR-008 — Widgets e reprocessamento/backfill

**Status:** Aceito

## Contexto

O uso de `MERGE INTO` por chave natural (ADR sobre streaming vs. batch) garante idempotência, mas não resolve por si só como alguém dispara o reprocessamento de um dia específico. Sem um gatilho concreto, Widgets — um dos objetivos de aprendizado do projeto — corre o risco de virar parâmetro decorativo em vez de mecanismo real.

## Decisão

Parametrizar os notebooks de ingestão/transformação com três widgets, permitindo que o mesmo notebook sirva tanto a execução diária agendada quanto o reprocessamento manual:

| Widget | Tipo | Valores | Papel |
|---|---|---|---|
| `data_referencia` | texto/data | ex.: `2026-07-29` | Qual dia processar |
| `sistema` | dropdown | `erp`, `crm`, `tms`, `financeiro`, `todos` | Permite reprocessar 1 pipeline isoladamente |
| `modo_execucao` | dropdown | `agendado`, `reprocessamento_manual` | Não altera o processamento; é gravado em `observability.pipeline_runs`, tornando reprocessamentos consultáveis |

### Cenários de uso

```
Execução normal (Workflow agendado):
  data_referencia = hoje (injetado automaticamente pelo Job)
  sistema = todos
  modo_execucao = agendado

Reprocessamento manual ("Run now with different parameters"):
  data_referencia = 2026-07-15  (o dia com problema)
  sistema = tms                  (só o que precisa correção)
  modo_execucao = reprocessamento_manual
```

Mesmo notebook, mesmo código — apenas os parâmetros mudam.

## Por que isso não compromete a idempotência já garantida

Os widgets não substituem o `MERGE INTO` — eles apenas decidem qual dia/sistema entra no MERGE. Reprocessar o mesmo dia duas vezes continua seguro porque a idempotência já vem do MERGE por chave natural, não do widget.

## Consequências

- `modo_execucao` vira uma dimensão consultável em `observability.pipeline_runs`, permitindo responder "quantos reprocessamentos manuais tivemos esse mês" — informação de negócio, não apenas técnica.
- Reprocessar um sistema isoladamente exige que o notebook trate `sistema = todos` como caso especial de iteração sobre os 4 sistemas, e qualquer outro valor como execução única — detalhe a resolver na fase de código (`src/`).