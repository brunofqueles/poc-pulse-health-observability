# TMS — Pulse Logistics

> Detalhamento de schema. Convenções gerais em [`README.md`](README.md).

### `bronze.tms_veiculos` (dimensão, seed pequeno)

| Campo | Gerador | Nota |
|---|---|---|
| `veiculo_id` | dbldatagen | — |
| `placa` | Faker/dbldatagen | — |
| `tipo_veiculo` | dbldatagen (categórico) | — |
| `refrigerado` | dbldatagen (boolean) | define capacidade real de cadeia fria |

### `bronze.tms_rotas` (dimensão, seed pequeno)

| Campo | Gerador |
|---|---|
| `rota_id` | dbldatagen |
| `regiao_destino` | dbldatagen (categórico, alinhado às regiões do CRM) |
| `tempo_transito_padrao_horas` | dbldatagen |

### `bronze.tms_remessas` (evento diário)

| Campo | Sujeira injetada | Nota |
|---|---|---|
| `remessa_id` | — | |
| `nota_expedicao_id` (FK cross-sistema, ERP) | — | |
| `pedido_id` (FK cross-sistema, CRM) | — | |
| `rota_id`, `veiculo_id` (FK) | — | **falha cruzada intencional**: ver seção dedicada abaixo |
| `sla_horas_contratado` | — | usado no cálculo de OTIF |
| `data_expedicao` | formato misto | |
| `data_entrega_prevista` | formato misto | derivada de expedição + SLA |

### `bronze.tms_leituras_temperatura` (evento de alta frequência, 3-6 leituras por remessa refrigerada, só para veículo refrigerado)

| Campo | Sujeira injetada | Nota |
|---|---|---|
| `leitura_id` | — | Chave de negócio (adicionada após MERGE INTO exigir chave verdadeiramente única — `remessa_id`+`timestamp_leitura` não era garantidamente único pelo código) |
| `remessa_id` (FK) | — | |
| `timestamp_leitura` | formato fixo, sem sujeira intencional (correção: a versão anterior deste documento indicava sujeira aqui, mas o simulador nunca implementou isso) | |
| `temperatura_celsius` | número com vírgula; ocasionalmente fora de 2–8°C mesmo em veículo refrigerado | segunda causa de violação: falha de equipamento |

### `bronze.tms_comprovantes_entrega` (evento diário)

| Campo | Sujeira injetada | Nota |
|---|---|---|
| `comprovante_id` | — | |
| `remessa_id` (FK) | — | |
| `data_entrega_real` | formato misto | comparado a `data_entrega_prevista` → base do OTIF |
| `status_entrega` | acentuação/caixa | |
| `pod_confirmado` | ocasionalmente ausente, de propósito | testa regra de entrega sem comprovante |

### ⚠️ Falha cruzada intencional — veículo sem refrigeração transportando produto de cadeia fria

Diferente de toda a sujeira listada acima (contida em uma única tabela/coluna), esta falha só é detectável **cruzando dois sistemas**: `tms_remessas.veiculo_id → tms_veiculos.refrigerado` contra `erp_lotes_producao.produto_id → erp_produtos.exige_cadeia_fria`. O simulador aloca, de propósito e ocasionalmente, uma remessa de Imunorax a um veículo com `refrigerado = false`. Esta verificação pertence à camada de regras de qualidade em Silver/Gold — não é redutível a uma checagem de coluna isolada, e deve ser tratada como caso de teste próprio quando a lógica de qualidade for implementada.