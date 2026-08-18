# ADR-015 — AI/BI Dashboard: camada de consumo visual

**Status:** Aceito (Dashboard e Genie implementados)

## Contexto

A plataforma tinha, até esta fase, dado de observabilidade calculado e consultável apenas via SQL/notebook — sem uma superfície visual pensada para consumo por alguém que não vá escrever query. `architecture.md` já reservava esse passo desde o início do projeto ("AI/BI Dashboards + Genie", substituindo Power BI), mas nunca havia sido implementado.

## Decisão

Um AI/BI Dashboard (`Pulse - Observabilidade`), com 3 painéis, cada um com descrição textual explicando o que mostra — pensado para "falhas visíveis" sem exigir que quem consulta saiba SQL:

| Painel | Fonte | Tipo |
|---|---|---|
| Alertas Recentes | `observability.alertas` | Tabela |
| Violações de Cadeia Fria por Tipo | `observability_cadeia_fria`, agregado por `tipo_violacao` | Gráfico de barra |
| Status de Execução por Pipeline | `pipeline_runs`, agregado por `pipeline`/`status` | Tabela |

**Restrição de linguagem: SQL, não PySpark** — cada painel é definido por uma query SQL; a ferramenta não oferece opção de célula PySpark. Isso não contradiz a decisão de projeto de usar só PySpark (ADR-002/003): aquela decisão cobre a camada de processamento (simuladores, transformação); AI/BI Dashboards é camada de consumo, com sua própria linguagem de configuração nativa — mesmo padrão já visto em Asset Bundles (YAML, não Python) e Databricks Workflows.

**Datasets separados da visualização**: cada painel tem um dataset SQL próprio (aba "Data" do dashboard), reaproveitável por múltiplas visualizações — mais próximo do padrão real de ferramentas de BI (dataset → múltiplos gráficos) do que escrever a query direto dentro do painel.

### Decisões de publicação (governança) — aplicação direta do ADR-005

**Shared data permission** (não "Individual data permissions"): consultas do dashboard rodam com as credenciais do publicador (o autor). Escolha obrigatória, não preferência — "Individual" exigiria que cada visualizador tivesse acesso próprio às tabelas via `GRANT`, e o ADR-005 já provou (`PRINCIPAL_DOES_NOT_EXIST`) que conceder acesso a outros principals não é possível no Free Edition, sem Account Console.

**Gerenciamento restrito a Admins** (não "All Workspace Users"/"All Account Users"): princípio de menor privilégio, mesmo critério já usado nas decisões de RBAC do ADR-005 — sem efeito prático diferente no ambiente mono-usuário atual, mas é a opção defensável caso o workspace ganhe mais usuários no futuro.

## Alternativas consideradas

- **Consultar `observability.alertas` só via SQL Editor/notebook**: descartada como solução final — funciona, mas não oferece a superfície visual "olhar e entender" que o pedido original (deixar falhas visíveis) pedia.

## Consequências

- O dashboard depende do mesmo SQL Warehouse único (2X-Small) da Free Edition (`architecture.md`, seção de limitações) — não testado sob múltiplos usuários simultâneos, irrelevante no contexto mono-usuário atual.
- Refresh do dashboard é manual nesta fase (não configuramos agendamento automático) — item a revisitar se o projeto migrar para `mode: production`.
- **Genie implementado nesta fase** — ver adendo abaixo.

## Adendo — Genie Agent implementado e validado

Criado `Pulse - Observabilidade` (Genie Agent), com escopo de **8 tabelas**: as 3 Gold (`gold_reconciliacao_financeira`, `gold_otif`, `gold_qualidade_producao`) e as 5 de `observability` (`alertas`, `pipeline_runs`, `observability_cadeia_fria`, `observability_qualidade_sku`, `observability_estoque_negativo`) — todas conectadas juntas na configuração inicial, não em duas etapas separadas como inicialmente registrado neste documento (correção de um erro de contabilidade da própria documentação, não do Genie).

**Camadas excluídas por desenho, não esquecimento:** `bronze`/`silver`/`landing` nunca entraram no escopo — Bronze é 100% string sem tratamento (ADR-001), inadequado para interpretação de linguagem natural.

**Validado com 5 perguntas, incluindo teste deliberado dos limites do escopo:**
1. "Quantos alertas existem registrados?" → 2 (correto — teste fabricado + as 520 violações reais)
2. "Quantas remessas têm o tipo de violação veículo incorreto?" → 520 (correto, já validado manualmente várias vezes)
3. "Quantas execuções cada pipeline teve, agrupado por status?" → agregação correta em duas dimensões (`pipeline`, `status`), incluindo um caso não-óbvio: `ingerir_dados` com as 11 tabelas em "sem_dado_novo" — corretamente refletindo que o Autoloader rastreia arquivo por *caminho*, não por *conteúdo* (ADR-012). Não é bug — é o comportamento correto, e o Genie interpretou/relatou com precisão.
4. "Qual o valor faturado até hoje, com lista diária?" → respondido corretamente com `SUM(valor_faturado)` sobre `gold_reconciliacao_financeira` (dentro do escopo) — consulta real conferida via "Show code", não texto fabricado.
5. **Teste deliberado do limite do escopo** — "Quantos clientes ativos existem no sistema?" (`crm_clientes` está na Silver, fora do escopo configurado): o Genie **não inventou número nem acessou a tabela fora de escopo** — respondeu com transparência que a tabela de clientes não está disponível, e ofereceu uma métrica substituta razoável (contagem de `pedido_id` únicos), sinalizando explicitamente que era aproximação.

**Correção de uma hipótese levantada e descartada durante a investigação:** ao ver a primeira resposta de faturamento (antes de confirmar que `gold` já estava no escopo), foi levantada a hipótese, apoiada por uma fonte secundária (blog de terceiros), de que o Genie poderia alcançar tabelas fora do Space configurado via edição manual de query. O teste 5 (acima) mostrou o oposto para consulta em linguagem natural: o escopo configurado foi respeitado com honestidade, sem fabricação. A fonte secundária tratava de um cenário diferente (edição manual da query gerada, não a interpretação da pergunta em si) — reforça a prática já seguida no projeto de testar diretamente em vez de confiar em fonte não-oficial sem verificação própria.