# ADR-014 — Gold: KPIs de negócio e observabilidade

**Status:** Aceito (Fase A concluída; Fases B e C pendentes)

## Contexto

Com Bronze e Silver completas (11 tabelas de evento + 6 seeds), faltava a camada que realmente entrega o objetivo do projeto: KPIs de negócio calculados de verdade, e a base para a plataforma de observabilidade. `business-context.md` já documentava quais KPIs eram esperados em cada área — a Gold é a implementação real deles.

## Decisão

### Gold é recriada por completo (`overwrite`), não incremental

Diferente da Silver (`MERGE` por chave, incremental — ADR-002/013), toda tabela Gold é reescrita inteira a cada execução. Justificativa: Gold é **dado derivado**, não fonte de verdade própria — recalcular do zero a partir da Silver (que já é confiável e idempotente) é mais simples e menos propenso a erro do que tentar fazer `MERGE` incremental sobre uma agregação, que exigiria lógica de reversão complexa para linhas que mudam de grupo.

### Estrutura: linha-a-linha vs. agregada, conforme a pergunta de negócio

| Tabela | Grão | Tipo de pergunta |
|---|---|---|
| `gold_reconciliacao_financeira` | 1 linha por fatura | "Essa fatura específica diverge do pedido?" |
| `gold_otif` | 1 linha por remessa | "Essa entrega específica foi no prazo?" |
| `gold_qualidade_producao` | 1 linha por centro+produto (agregado) | "Qual a taxa de rejeição desse grupo?" |

Não existe padrão único — o grão da tabela Gold segue a granularidade da pergunta que ela responde, não uma convenção fixa de "sempre agregar" ou "sempre manter linha".

### Fase 0 necessária antes da Gold: promover os 6 seeds

Seeds (`erp_produtos`, `tms_veiculos` etc.) nunca tinham passado de Landing Zone — a Gold de observabilidade (Fase B, pendente) precisa deles para os `JOIN`s cruzados (ex.: `tms_veiculos.refrigerado`). Promovidos via função genérica própria (`promover_seed.py`), mais simples que a de evento diário: sem Autoloader (recarrega por completo, não incremental) e sem UDFs de limpeza (seed não tem sujeira intencional — só cast de tipo).

## Validação: um KPI "bom demais" é sinal de alerta, não de sucesso

`gold_otif` deu 100% na primeira tentativa — investigado e revertido para a causa raiz (Lição 8, `docs/licoes-aprendidas.md`): o simulador nunca dava chance real de atraso. A prática adotada daqui em diante: todo KPI novo é conferido quanto à **plausibilidade estatística** do resultado antes de ser aceito como correto, não só quanto à execução sem erro.

## Alternativas consideradas

- **Gold incremental via MERGE, como a Silver**: descartada para a Fase A — a maioria das tabelas Gold implementadas é recalculável por completo a baixo custo (volume de POC); a complexidade de MERGE incremental sobre agregação não se justifica neste volume. Pode ser revisitada se o volume real de produção tornasse o recálculo completo caro.

## Consequências

- Gold sempre reflete o estado mais recente da Silver no momento da execução — não existe risco de Gold "desatualizada" por MERGE mal feito, ao custo de recalcular tudo a cada execução.
- `gold_qualidade_producao`, sendo agregada, perde a granularidade de lote individual — quem precisar investigar um lote específico reprovado precisa voltar na Silver, não na Gold.
- Fases B (observabilidade de qualidade/dados) e C (observabilidade de execução, `pipeline_runs`) seguem pendentes — este ADR cobre a decisão de desenho geral da camada, válida para as três fases, não só a primeira.