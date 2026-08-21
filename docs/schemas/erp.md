# ERP — Manufacturing

> Detalhamento de schema. Convenções gerais (sujeira intencional, calendário, chaves cross-sistema) em [`README.md`](README.md).
>
> **Nota:** a partir do 5º pipeline (`ADR-017`), este arquivo cobre só Manufacturing — Distribution (`erp_posicoes_estoque`, `erp_notas_expedicao`) virou pipeline próprio, documentado em [`distribution.md`](distribution.md). Nomes de tabela mantidos sem alteração.

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