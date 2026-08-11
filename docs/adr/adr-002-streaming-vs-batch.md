# ADR-002 — Streaming vs. Batch por camada

**Status:** Aceito

## Contexto

Esta decisão incorpora uma lição de um projeto anterior (`poc-lakehouse-food-latam`): usar Structured Streaming com checkpoint em todas as camadas (Bronze e Silver), mesmo sendo um pipeline batch diário de baixo volume, gerou uma cadeia de problemas reais — exclusões na origem quebrando o streaming (`ignoreDeletes`/`ignoreChanges`), duplicação por reprocessamento de checkpoint, e dificuldade de fazer correções manuais (backfill) sem contornar o mecanismo de checkpoint.

A causa raiz: streaming com checkpoint assume, por padrão, que a fonte só recebe inserções (append-only). Checkpoint e dados são mecanismos independentes — corrigir/apagar dados numa tabela não reverte o progresso do checkpoint.

## Decisão

Streaming (Structured Streaming com Autoloader, `Trigger.AvailableNow`) é usado **exclusivamente** entre Landing e Bronze — o único ponto do fluxo genuinamente append-only, já que um arquivo pousado num Volume não sofre DELETE/UPDATE depois (ver ADR-001).

De Bronze em diante (Bronze→Silver, Silver→Gold), o processamento é **batch + `MERGE INTO` por chave natural**, orquestrado por Databricks Workflows em schedule:

```
Landing (Volumes)
      │  Autoloader, Trigger.AvailableNow  ← streaming aqui: apropriado, append-only real
      ▼
    Bronze
      │  Job batch agendado (Workflows), MERGE INTO por chave natural
      │  ← idempotente: rodar 2x não duplica; correção manual não precisa contornar checkpoint
      ▼
Silver ──► Gold
```

Critério explícito para decidir streaming vs. batch em qualquer camada futura: **a fonte muda de forma diferente de um simples append, e há necessidade real de baixa latência?** Se a resposta for não para as duas perguntas, batch + MERGE é a escolha padrão.

## Alternativas consideradas

- **Streaming em todas as camadas**: descartada — é exatamente o erro documentado na lição do projeto anterior.
- **Batch em todas as camadas, incluindo Landing→Bronze**: descartada — perderia o benefício genuíno de streaming onde ele se aplica (Autoloader detectando novos arquivos automaticamente, sem job de varredura manual).

## Consequências

- Reprocessamento/backfill (ver ADR-008) é natural em Bronze→Silver→Gold: basta rodar o MERGE novamente para a `data_referencia` desejada, sem gerenciar ou resetar checkpoint.
- Streaming contínuo nunca é necessário em nenhuma camada — compatível com a limitação da Free Edition, que só suporta `Trigger.AvailableNow`/`Once` (ver `architecture.md`, seção de limitações).
- Chaves de negócio (`lote_id`, `pedido_id`) precisam estar bem definidas antes da implementação do MERGE em cada sistema — pré-requisito tratado no schema detalhado por pipeline, ainda pendente.

## Adendo — MERGE exige chave verdadeiramente única, não só "identificador nomeado"

Ao implementar a transformação Bronze→Silver de fato, 3 tabelas (`erp_posicoes_estoque`, `crm_itens_pedido`, `tms_leituras_temperatura`) não tinham nenhuma coluna que garantisse unicidade por linha — apenas combinações de FK + valor (`lote_id`+`centro_distribuicao_id`, `pedido_id`+`produto_id`, `remessa_id`+`timestamp_leitura`), sem garantia no código de que essas combinações não se repetiriam. `MERGE INTO` com uma condição que não identifica uma linha só falha com erro de "múltiplas linhas casando".

**Correção:** as 3 tabelas ganharam uma coluna de ID sintético próprio (`posicao_id`, `item_pedido_id`, `leitura_id`), gerada no mesmo padrão sequencial já usado no projeto — não chave composta, que continuaria com risco residual de colisão em pelo menos um caso (`crm_itens_pedido`, onde o mesmo produto pode aparecer mais de uma vez no mesmo pedido).

**Lição para desenho futuro:** ao definir o schema de uma tabela de evento (não dimensão), verificar explicitamente se existe uma coluna que garanta unicidade de linha — não assumir que a combinação de chaves estrangeiras é suficiente só porque "faz sentido" ser única.