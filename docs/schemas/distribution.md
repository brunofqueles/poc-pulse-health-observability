# Distribution

> Detalhamento de schema. Convenções gerais (sujeira intencional, calendário, chaves cross-sistema) em [`README.md`](README.md).
>
> Pipeline separado do ERP a partir do 5º pipeline (`ADR-017`, demonstração de escala) — antes vivia dentro do `SimuladorERP` (Opção A). Nomes de tabela mantidos sem alteração (`erp_posicoes_estoque`, `erp_notas_expedicao`) para não exigir mudança em Gold/observability/schemas que já as referenciam — só a origem na Landing Zone mudou (`distribution/`, não mais `erp/`).

### `bronze.erp_posicoes_estoque` (evento diário, snapshot)

| Campo | Tipo lógico | Sujeira injetada | Nota |
|---|---|---|---|
| `posicao_id` | string | — | Chave de negócio (adicionada após MERGE INTO exigir chave verdadeiramente única — `lote_id`+`centro_distribuicao_id` sozinhos não garantiam unicidade) |
| `lote_id` | string (FK cross-sistema, ERP) | — | referência sintética — sem memória entre dias, limitação conhecida (ADR-010) |
| `centro_distribuicao_id` | string | espaço/caixa inconsistente | |
| `quantidade` | int | número com vírgula; ocasionalmente negativo (de propósito) | testa regra de estoque negativo |
| `data_posicao` | date | formato misto | |

### `bronze.erp_notas_expedicao` (evento diário)

| Campo | Tipo lógico | Sujeira injetada | Nota |
|---|---|---|---|
| `nota_expedicao_id` | string | — | |
| `pedido_id` | string (FK cross-sistema, CRM) | — | lido da Landing Zone do CRM, mesma data |
| `lote_id` | string (FK cross-sistema, ERP) | — | lido da Landing Zone do ERP, mesma data — real quando Manufacturing produziu no dia, sintético caso contrário |
| `centro_distribuicao_id` | string | espaço/caixa inconsistente | |
| `quantidade_expedida` | int | número com vírgula | |
| `data_expedicao` | date | formato misto | |

## Dependência de execução (ADR-011, adendo)

`SimuladorDistribution` lê dois sistemas diferentes na mesma execução: `crm_pedidos` (para `pedido_id`) e `erp_lotes_producao` (para `lote_id` real, filtrando lotes aprovados via correspondência de texto — `"aprovado" in status_qc.lower()`, que nunca coincide com `"reprovado"` mesmo com a sujeira de caixa/espaço). Cadeia de dependência completa: CRM → ERP → **Distribution** → TMS → Financeiro.