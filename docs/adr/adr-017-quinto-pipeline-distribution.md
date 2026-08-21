# ADR-017 — 5º pipeline: separação de Distribution do ERP

**Status:** Aceito

## Contexto

`business-context.md` já previa, desde o início do projeto, uma "Fase de escala" separando Distribution do ERP (Opção A → Opção B) como demonstração de que o desenho config-driven do projeto realmente escala, sem precisar reescrever a arquitetura. Chegada a hora de implementar.

## Decisão

Novo `SimuladorDistribution` (classe própria, mesma hierarquia de `SimuladorDeSistema`), cobrindo `erp_posicoes_estoque` e `erp_notas_expedicao` — antes geradas dentro de `SimuladorERP`. `SimuladorERP` fica só com Manufacturing (`erp_lotes_producao`), calendário volta a ser Seg-Sex (deixa de ser a união Seg-Sáb).

**Nomes de tabela mantidos, sem alteração** (`erp_posicoes_estoque`, `erp_notas_expedicao`, não `distribution_*`) — decisão deliberada que isolou completamente o impacto da mudança: Gold, observability e os schemas que já referenciam essas tabelas pelo nome não precisaram de nenhuma alteração. Confirmado na prática: revisão de `construir_gold.ipynb` e `promover_seeds.ipynb` não encontrou nenhuma referência que precisasse mudar.

**Nova cadeia de dependência de geração** (ADR-011, estendida): `CRM → ERP → Distribution → TMS → Financeiro`. Antes de Distribution virar classe própria, ela tinha acesso em memória aos lotes que o ERP gerava na mesma chamada; agora precisa **ler** `erp_lotes_producao` da Landing Zone (cross-read), mesmo padrão já usado entre os outros sistemas.

**Filtro de lote aprovado sobre texto sujo:** como Distribution só tem acesso ao `status_qc` já formatado (string suja: `"aprovado"`, `"APROVADO"`, `" aprovado "` etc.), o filtro usa `"aprovado" in status_qc.strip().lower()` — funciona corretamente porque `"aprovado"` nunca é substring de `"reprovado"` (confirmado por análise caractere a caractere antes de implementar, para evitar o mesmo tipo de erro de parsing sobre texto sujo já visto antes no projeto).

**Impacto real, medido, não estimado:** o único código que mudou foi `simulador_erp.py` (simplificado), `simulador_distribution.py` (novo), `simulador_factory.py` (registro + ordem), `simulador_tms.py` (1 linha — caminho de leitura de `erp/` para `distribution/`), e os 3 orquestradores com lista de sistema hardcoded (`gerar_dados`, `ingerir_dados`, `limpar_landing_zone`) — Widgets precisaram ser removidos e recriados manualmente, já que o Databricks não atualiza opções de dropdown existente automaticamente ao reexecutar a célula de definição.

## Incidente durante a implementação: `LOCATION_OVERLAP`

Ao tentar reingerir `erp_posicoes_estoque`/`erp_notas_expedicao` da nova pasta `distribution/`, `IngestorAutoloader` falhou com `INVALID_PARAMETER_VALUE.LOCATION_OVERLAP` — o checkpoint dessas duas tabelas (nomeado só pela **tabela**, não pelo sistema de origem) ainda continha referência ao caminho antigo (`erp/data=.../`), de quando essas tabelas viviam sob o ERP. O Unity Catalog recusou a mudança de "endereço de origem" para uma fonte de streaming já conhecida sob outro caminho.

**Correção:** reset pontual de Bronze/checkpoint/schema dessas 2 tabelas (não da Silver — o `MERGE` por chave continuou íntegro). O histórico antigo (dado real dos 60 dias do backfill anterior) permaneceu fisicamente em `erp/data=.../`, órfão da nova arquitetura — resolvido definitivamente pelo backfill completo (ver Adendo, ADR-010).

## Incidente de infraestrutura: queda de conexão do compute

Durante um teste de ingestão, o notebook travou por >10 minutos e depois retornou `StatusRuntimeException: UNAVAILABLE` (perda de conexão gRPC entre notebook e compute serverless) — falha de infraestrutura, não do código. **Diagnóstico correto: `DESCRIBE HISTORY`** na tabela Bronze confirmou que a escrita já havia sido concluída com sucesso *antes* da queda de conexão — o dado nunca esteve em risco, só a confirmação visual na tela não chegou a aparecer. Mesmo método de investigação já validado na Lição 10 (confiar no histórico real da tabela, não no estado aparente da célula).

## Alternativas consideradas

- **Renomear as tabelas para `distribution_*`**: descartada — multiplicaria o esforço de migração (Gold, observability, schemas, todos precisariam de atualização) sem benefício real, já que o nome da tabela não precisa refletir de qual simulador ela se origina.
- **Manter Distribution como parte do ERP indefinidamente**: era a Opção A original, válida para a Fase 1 — mas não demonstra a extensibilidade que o projeto se propõe a provar.

## Consequências

- Confirma, na prática, os 3 caminhos de extensão já documentados no `architecture.md`: novo sistema = nova classe + registro no Factory + entradas nos dicionários de configuração, sem precisar tocar em Job/Task do Asset Bundles.
- O backfill de 60 dias precisou ser refeito (agora 67 dias, estendido até a data real do teste, sem lacuna) — reset e regeneração completos, desta vez com `registrar_execucao_pipeline` embutido na geração desde o início, não como correção retroativa (corrigindo a causa raiz da Lição 15).
- Checkpoints do Autoloader são amarrados ao caminho de origem na primeira execução — qualquer mudança estrutural futura na Landing Zone (mover uma tabela de pasta) deve prever reset de checkpoint como parte do plano, não como surpresa.