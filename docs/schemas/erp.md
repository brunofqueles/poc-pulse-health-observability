# ERP — Manufacturing + Distribution

> Detalhamento de schema. Convenções gerais (sujeira intencional, calendário, chaves cross-sistema) em [`README.md`](README.md).

### `bronze.erp_produtos` (dimensão fixa, seed único — catálogo controlado, sem sujeira injetada)

| Campo | Valor |
|---|---|
| `produto_id` | `PROD-001` / `PROD-002` / `PROD-003` |
| `nome_produto` | Vitalectra 500mg / Imunorax / Pulmoxil |
| `forma_farmaceutica` | comprimido / injetável / xarope |
| `exige_cadeia_fria` | false / **true** / false |
| `validade_padrao_dias` | 730 / 365 / 180 |

### `bronze.erp_lotes_producao` (evento diário)

| Campo | Tipo lógico (Silver) | Sujeira injetada | Nota |
|---|---|---|---|
| `lote_id` | string | — | **Chave de negócio** — propaga para Distribution e Logistics |
| `produto_id` | string (FK) | — | referencia os 3 produtos fixos |
| `centro_producao_id` | string | espaço/caixa inconsistente | |
| `data_fabricacao` | date | formato misto (`29/07/2026` / `2026-07-29`) | |
| `data_validade` | date | mesma inconsistência de formato | derivada de fabricação + `validade_padrao_dias` |
| `quantidade_produzida` | int | número com vírgula (`1.250,00`) | |
| `status_qc` | string | acentuação/caixa | 90% aprovado / 10% reprovado |
| `data_liberacao` | date/null | nulo representado de formas diferentes | nulo se reprovado |

### `bronze.erp_posicoes_estoque` (evento diário, snapshot)

| Campo | Tipo lógico | Sujeira injetada | Nota |
|---|---|---|---|
| `lote_id` | string (FK) | — | só lotes com QC aprovado |
| `centro_distribuicao_id` | string | espaço/caixa inconsistente | |
| `quantidade` | int | número com vírgula; ocasionalmente negativo (de propósito) | testa regra de estoque negativo |
| `data_posicao` | date | formato misto | |

### `bronze.erp_notas_expedicao` (evento diário)

| Campo | Tipo lógico | Sujeira injetada | Nota |
|---|---|---|---|
| `nota_expedicao_id` | string | — | |
| `pedido_id` | string (FK cross-sistema, CRM) | — | |
| `lote_id` | string (FK) | — | alocado por FEFO |
| `centro_distribuicao_id` | string | espaço/caixa inconsistente | |
| `quantidade_expedida` | int | número com vírgula | |
| `data_expedicao` | date | formato misto | |