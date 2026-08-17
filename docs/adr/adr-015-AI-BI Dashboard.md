# ADR-015 — AI/BI Dashboard: camada de consumo visual

**Status:** Aceito (Dashboard implementado; Genie pendente)

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
- **Genie não foi configurado nesta fase** — decisão deliberada de sequenciamento: validar a base de dashboard fixo primeiro (queries já conhecidas e corretas), antes de configurar a camada de linguagem natural, que exige contexto adicional (Genie Space apontando para as tabelas, com descrição de colunas) para interpretar perguntas corretamente.