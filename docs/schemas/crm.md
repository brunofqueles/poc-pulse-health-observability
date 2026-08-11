# CRM — Pulse Commercial

> Detalhamento de schema. Convenções gerais em [`README.md`](README.md).

### `bronze.crm_representantes` (dimensão, seed pequeno)

| Campo | Gerador | Sujeira injetada |
|---|---|---|
| `representante_id` | dbldatagen | — |
| `nome_representante` | Faker (`name`) | — |
| `regiao` | dbldatagen (categórico) | caixa inconsistente |

### `bronze.crm_clientes` (dimensão, seed + crescimento esporádico)

| Campo | Gerador | Sujeira injetada |
|---|---|---|
| `cliente_id` | dbldatagen | — |
| `nome_cliente` | Faker (`company`) | acentuação/caixa |
| `email_contato` | Faker (`email`) | formato malformado ocasional |
| `regiao` | dbldatagen (categórico) | — |
| `status_cliente` | dbldatagen (ativo 95% / bloqueado 5%) | acentuação/caixa |

### `bronze.crm_pedidos` (evento diário)

| Campo | Sujeira injetada | Nota |
|---|---|---|
| `pedido_id` | — | **Chave de negócio** — nasce aqui, propaga para Distribution, Logistics, Financeiro |
| `cliente_id` (FK) | — | ocasionalmente referencia cliente bloqueado, de propósito |
| `representante_id` (FK) | — | |
| `data_pedido` | formato misto | |
| `valor_total` | número com vírgula | usado na reconciliação com o Financeiro |
| `status_pedido` | acentuação/caixa | |

### `bronze.crm_itens_pedido` (evento diário, filho de pedido)

| Campo | Sujeira injetada | Nota |
|---|---|---|
| `item_pedido_id` | — | Chave de negócio (adicionada após MERGE INTO exigir chave verdadeiramente única — um pedido pode ter o mesmo `produto_id` repetido entre itens) |
| `pedido_id` (FK) | — | |
| `produto_id` (FK cross-sistema, ERP) | ocasionalmente inexistente, de propósito | testa regra de SKU inválido |
| `quantidade` | número com vírgula | |
| `preco_unitario` | número com vírgula | |

### `bronze.crm_atendimento` (evento diário, baixo volume — 20 a 40/dia)

| Campo | Sujeira injetada | Nota |
|---|---|---|
| `interacao_id` | — | |
| `cliente_id` (FK) | — | |
| `lote_id` (FK cross-sistema, ERP, opcional) | nulo representado de formas diferentes | gatilho de correlação com recall quando preenchido |
| `tipo_interacao` | acentuação/caixa | categórico |
| `descricao` | Faker (`sentence`) | — |
| `data_interacao` | formato misto | |