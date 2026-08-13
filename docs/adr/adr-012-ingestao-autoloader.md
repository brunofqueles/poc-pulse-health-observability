# ADR-012 — Ingestão Landing Zone → Bronze via Autoloader

**Status:** Aceito

## Contexto

Com os 4 simuladores gerando dado real na Landing Zone (ADR-001), era preciso validar como a ingestão para Bronze funcionaria de fato no Free Edition — nenhuma parte do fluxo de Autoloader havia sido testada até este ponto do projeto.

## Decisão

Uma classe única e parametrizada, `IngestorAutoloader(spark, sistema, tabela)` — diferente dos simuladores (uma subclasse por sistema), a lógica de ingestão é idêntica para qualquer tabela; só os parâmetros mudam. Não há hierarquia de classes aqui.

```python
IngestorAutoloader(spark, sistema="erp", tabela="erp_lotes_producao").executar()
```

Configuração validada por spike (`src/spikes/teste_autoloader_erp_lotes_producao`):

| Opção | Valor | Por quê |
|---|---|---|
| `cloudFiles.format` | `"json"` | Formato gerado pelos simuladores |
| `cloudFiles.inferColumnTypes` | `false` | Preserva Bronze 100% string (ADR-001) |
| `cloudFiles.schemaLocation` | `.../_autoloader_schema/{tabela}` | Obrigatório mesmo com `inferColumnTypes=false` — Autoloader ainda rastreia nomes de coluna e evolução de schema |
| `pathGlobFilter` | `"{tabela}.json"` | Isola uma tabela específica dentro da pasta do sistema, que contém várias tabelas na mesma partição `data=` |
| `checkpointLocation` | `.../_autoloader_checkpoint/{tabela}` | Garante idempotência — reexecutar não reprocessa arquivo já ingerido |
| `trigger` | `availableNow=True` | Streaming só faz sentido aqui — o único ponto do fluxo genuinamente append-only (ADR-002) |

Convenção de pastas: `_autoloader_schema/` e `_autoloader_checkpoint/`, com `_` inicial, mesma convenção já usada para `_seed/` — sinaliza "infraestrutura técnica", não dado de negócio.

**Descoberta durante o spike:** o Autoloader detecta sozinho o padrão Hive-style do path (`data=AAAA-MM-DD/`) e cria automaticamente uma coluna `data` com o valor da partição — sem necessidade de extração manual.

## Alternativas consideradas

- **Uma classe por sistema (mesma hierarquia dos simuladores)**: descartada — não há nenhuma variação de comportamento por sistema na ingestão; herdar do padrão dos simuladores aqui seria abstração sem propósito, o mesmo raciocínio já usado no ADR-003 para não aplicar OOP às transformações.

## Consequências

- Adicionar ingestão de uma tabela nova (ex.: fase de escala, 5º pipeline) significa só instanciar a classe com novos parâmetros — nenhum código novo.
- O retorno de `executar()` distingue `"sucesso"` (processou arquivo novo) de `"sem_dado_novo"` (rodou limpo, nada para processar) — decidido pelo número de arquivos processados, não pela presença de `lastProgress`, que o `Trigger.AvailableNow` sempre retorna preenchido mesmo sem dado novo (ver Lição 6, `docs/licoes-aprendidas.md`).
- Generalizar para as 11 tabelas de evento diário é o próximo passo — o padrão já está provado, não precisa de nova investigação por tabela.

## Adendo — `recentProgress`, não `lastProgress`, para não perder relato de micro-lotes

`query.lastProgress` reflete só o último micro-lote de uma execução do `Trigger.AvailableNow`. Quando o Autoloader divide o processamento em mais de um micro-lote (mesmo dentro de uma única chamada de `.executar()`), o último pode ser um lote de confirmação vazio — fazendo `IngestorAutoloader` reportar `sem_dado_novo` mesmo tendo processado dado real num lote anterior da mesma execução. Diagnosticado via `DESCRIBE HISTORY` da tabela Bronze, confirmando dois registros com o mesmo `queryId` e `epochId` sequencial (ver Lição 10, `docs/licoes-aprendidas.md`).

**Correção:** `executar()` agora itera `query.recentProgress` (todos os micro-lotes da execução) e soma as métricas, em vez de olhar só `lastProgress`. O dado gravado na Bronze nunca esteve incorreto — só o relato de status.