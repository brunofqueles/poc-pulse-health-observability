# ADR-011 — Dependência de ordem na geração de dados cross-sistema

**Status:** Aceito

## Contexto

`erp_notas_expedicao` precisa referenciar um `pedido_id` real do CRM (`docs/schemas/erp.md`) — sem isso, a chave ficaria "sujeira do tipo errado": fingindo uma integridade que não existe, diferente da sujeira intencional que o projeto controla de propósito (ADR incorporando as lições do projeto anterior). Isso expôs uma dependência que a arquitetura documentada até então não cobria: a própria **geração** de dados (não só a transformação, já coberta pelo ADR-006) tem uma ordem implícita entre sistemas.

## Decisão

`SimuladorERP._gerar_notas_expedicao()` lê diretamente o arquivo `crm_pedidos.json` já gravado na Landing Zone do CRM, para a mesma `data_referencia`, via `spark.read.json()`. Se o arquivo não existir (CRM ainda não gerou aquele dia), o método retorna lista vazia — sem erro, sem exceção, apenas ausência de dependência satisfeita.

Quando possível (dias com produção nova, Segunda a Sexta), `lote_id` referenciado na nota de expedição usa lotes **reais**, gerados na mesma execução de `SimuladorERP.gerar_dia()`, preservando o vínculo genuíno com o produto — necessário para a checagem de cadeia fria que o TMS vai implementar. Em dias sem produção (sábado), cai para referência sintética, mesma limitação já documentada para `erp_posicoes_estoque`.

**Regra de ordem resultante:** para uma `data_referencia` específica, o `SimuladorCRM` precisa rodar antes do `SimuladorERP`, se a intenção for ter `erp_notas_expedicao` populada com integridade real naquele dia. Rodar na ordem inversa não é erro — apenas produz uma Distribution sem notas de expedição para aquele dia, recuperável rodando o ERP novamente depois (idempotente, MERGE por chave garante isso — ADR-002).

## Alternativas consideradas

- **Compartilhar dado em memória entre simuladores, dentro de uma única chamada orquestradora** (em vez de ler de arquivo já gravado): mais rápido (sem I/O), mas exigiria que o orquestrador conhecesse as dependências internas de cada simulador — acoplamento maior entre a camada de orquestração e a lógica de negócio de cada sistema. Descartada em favor de manter cada simulador responsável só por si mesmo, lendo o que precisa da Landing Zone (mesmo padrão que a Bronze/Silver já usam para consumir dado de outra camada).
- **Chave estrangeira totalmente sintética, sem tentar vínculo real** (o que já fazemos em `erp_posicoes_estoque`): mais simples, mas sacrificaria a possibilidade de a checagem de cadeia fria do TMS (cruzando lote → produto → exige_cadeia_fria) ser genuína em pelo menos parte dos casos. Descartada como padrão geral, mas mantida como *fallback* documentado para o caso sem produção do dia.

## Consequências

- A ordem de execução dos simuladores por sistema deixa de ser arbitrária — precisa ser conhecida e respeitada por quem rodar o backfill (ADR-010) ou desenhar o Job diário real (ADR-006): CRM antes de ERP, para a mesma data.
- `SimuladorERP` passa a depender de leitura via Spark (`spark.read.json`), não só escrita — primeira vez que um simulador lê dado de outro sistema na Landing Zone.
- Se o TMS também precisar ler dado de outro sistema (provável, dado que referencia `nota_expedicao_id` do ERP), o mesmo padrão se aplica — tratar como precedente, não repensar do zero.