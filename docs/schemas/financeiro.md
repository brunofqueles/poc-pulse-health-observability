# Financeiro — SSC

> Detalhamento de schema. Convenções gerais em [`README.md`](README.md).

### `bronze.financeiro_centros_custo` (dimensão, seed pequeno)

| Campo | Gerador |
|---|---|
| `centro_custo_id` | dbldatagen |
| `nome_centro_custo` | dbldatagen (categórico: Manufacturing, Distribution, Logistics, Commercial) |

### `bronze.financeiro_faturas` (evento diário — derivado de outros sistemas, não gerado do zero)

| Campo | Origem / Sujeira injetada | Nota |
|---|---|---|
| `fatura_id` | gerado | — |
| `pedido_id` (FK cross-sistema, CRM) | só existe fatura para pedido com POD confirmado | reforça regra "fatura só após entrega confirmada" |
| `remessa_id` (FK cross-sistema, TMS) | — | |
| `valor_faturado` | número com vírgula; ocasionalmente divergente do `valor_total` do pedido, de propósito | gatilho do eixo de negócio da observabilidade |
| `data_faturamento` | formato misto | derivada de entrega + defasagem |
| `centro_custo_id` (FK) | ocasionalmente nulo/inválido, de propósito | testa regra de lançamento sem centro de custo |

### `bronze.financeiro_contas_receber` (evento diário, filho de fatura)

| Campo | Sujeira injetada | Nota |
|---|---|---|
| `conta_receber_id` | — | |
| `fatura_id` (FK) | — | |
| `data_vencimento` | formato misto | |
| `data_recebimento` | ocasionalmente nula | usado no cálculo de DSO |
| `status_conta` | acentuação/caixa | |

### `bronze.financeiro_fechamento_mensal` (evento mensal — gerado pelo Job mensal, ADR-006, não pelo Job diário)

| Campo | Nota |
|---|---|
| `periodo_referencia` | mês/ano fechado |
| `total_faturado` | agregado do período |
| `total_divergencias` | conta faturas do período com `valor_faturado` divergente — métrica que prova a reconciliação funcionando |
| `status_fechamento` | sucesso apenas se `pipeline_runs` confirmar que os 4 pipelines rodaram todos os dias operacionais do mês |