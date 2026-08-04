# Schemas detalhados por sistema

> Define os campos físicos de cada tabela Bronze, a chave de negócio, e a sujeira intencional injetada pelo simulador para tornar a Silver genuinamente necessária. Contexto de negócio (entidades, regras, KPIs) vive em `business-context.md`; aqui é o detalhamento técnico de campo.

## Convenções gerais

- **Toda coluna nasce como `string` na camada Bronze**, mesmo quando o tipo lógico final é `int`, `date` ou `boolean` — Bronze é cópia fiel, sem tratamento algum. O tipo lógico indicado nas tabelas abaixo só existe a partir da Silver.
- **Sujeira é intencional e repetível**, não ruído aleatório: cada campo sujo testa um caso específico de tratamento na Silver (formato de data, número com vírgula decimal, acentuação, nulo representado de formas diferentes, espaço/caixa inconsistente).
- **Calendário de operação por sistema** (ver `business-context.md`): cada `SimuladorDeSistema` só gera evento diário nos dias operacionais do seu sistema — ausência de arquivo num dia não operacional não é falha.

| Sistema | Calendário |
|---|---|
| ERP — Manufacturing | Segunda a sexta |
| ERP — Distribution | Segunda a sábado |
| CRM — Commercial | Todos os dias |
| TMS — Logistics | Segunda a sábado |
| Financeiro — SSC | Segunda a sexta |

---

## Chaves de negócio — resumo cross-sistema

| Chave | Nasce em | Propaga até |
|---|---|---|
| `lote_id` | ERP (Manufacturing) | ERP (Distribution), CRM (atendimento, opcional), TMS |
| `pedido_id` | CRM | ERP (Distribution), TMS, Financeiro |
| `produto_id` | ERP (catálogo fixo) | CRM (itens de pedido), TMS (via lote) |
| `nota_expedicao_id` | ERP (Distribution) | TMS |
| `remessa_id` | TMS | Financeiro |

## Arquivos por sistema

- [`erp.md`](erp.md) — Manufacturing + Distribution
- [`crm.md`](crm.md) — Commercial
- [`tms.md`](tms.md) — Logistics
- [`financeiro.md`](financeiro.md) — SSC