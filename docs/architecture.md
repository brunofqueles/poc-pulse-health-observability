# Arquitetura — Pulse Health Platform (POC)

> Este documento descreve as decisões técnicas de arquitetura da plataforma de observabilidade de pipelines. Contexto de negócio (missões, entidades, regras) vive em `docs/business-context.md`. Decisões pontuais e seus trade-offs detalhados vivem em `docs/adr/`.

## 1. Entendimento do problema

Construir uma POC de plataforma de observabilidade que monitora pipelines de dados simulando a área de dados de um conglomerado fictício de Life Sciences (Pulse Health Group), demonstrando competências de engenharia de dados, arquitetura, qualidade, observabilidade e boas práticas de desenvolvimento (OOP, Widgets, Infrastructure as Code) — 100% dentro do Databricks Free Edition.

## 2. Premissas adotadas

- Plataforma alvo: **Databricks Free Edition** — serverless-only, sem private networking, outbound restrito a domínios confiáveis, 1 SQL warehouse (2X-Small), máximo 5 tasks concorrentes por conta, 1 pipeline Lakeflow ativo por tipo.
- Sem Docker e sem Power BI — geração de dados e visualização acontecem inteiramente dentro do Databricks.
- Escopo Fase 1: **4 pipelines** (ERP unificado cobrindo Manufacturing + Distribution, CRM/Commercial, TMS/Logistics, Financeiro/SSC). 5º pipeline (separação de Distribution do ERP) é a demonstração de escala.
- Volumetria e regras de negócio conforme `docs/business-context.md` — números fictícios, mas fixados como premissa, não descobertos durante o código.
- Governança e time: projeto solo, portfólio público — sem requisitos de compliance regulatório real, sem SLA contratual (é POC, não produto).

## 3. Arquitetura proposta

```
[Geração diária]                [Landing Zone]              [Ingestão]         [Transformação]
Databricks Workflow      ──>    poc_pulse_observability.landing (Volumes)  ──> Autoloader   ──>  Bronze ──> Silver ──> Gold
(trigger diário)                <sistema>/data=AAAA-MM-DD/    (cloudFiles,      (Delta,     (MERGE      (KPIs de
dbldatagen + Faker              arquivos JSON brutos          Trigger           cópia       por         negócio)
(um gerador por sistema)                                      AvailableNow)     fiel)       chave)
                                                                                                  │
                                                                                                  ▼
                                                                                     [Observabilidade — o produto]
                                                                                     poc_pulse_observability.observability
                                                                                     (logs de execução, qualidade,
                                                                                      SLA, reconciliação de negócio)
                                                                                                  │
                                                                                                  ▼
                                                                                  [Analytics / IA]
                                                                              AI/BI Dashboards + Genie
```

### Unity Catalog — convenção de nomes

Catalog único `poc_pulse_observability` (nome ajustado para manter o prefixo `poc_` usado em todo o repositório, sinalizando ambiente não-produtivo já dentro do próprio Databricks), schema por camada:

| Schema | Conteúdo |
|---|---|
| `poc_pulse_observability.landing` | Volumes — arquivos JSON brutos, organizados por `sistema/data=AAAA-MM-DD/` |
| `poc_pulse_observability.bronze` | Tabelas Delta, cópia fiel por sistema (`erp`, `crm`, `tms`, `financeiro`) — **todas as colunas como `string`, sem nenhum tratamento de tipo ou conteúdo**. Sujeira de origem (formato de data inconsistente, número com vírgula decimal, acentuação, nulo representado de formas diferentes) é preservada de propósito; tratamento só começa na Silver. Detalhamento de campo por sistema em `docs/schemas/` |
| `poc_pulse_observability.silver` | Tabelas Delta limpas, tipadas, deduplicadas, com regras de negócio aplicadas |
| `poc_pulse_observability.gold` | Tabelas Delta com KPIs de negócio (OTIF, taxa de rejeição de lote, DSO etc.) |
| `poc_pulse_observability.observability` | Tabelas Delta com logs de execução, métricas de qualidade, SLA e reconciliação — alimentadas pelos três eixos de observabilidade |

**Nota sobre `pipeline_runs`:** o status de cada execução não é binário (sucesso/falha) — existe um terceiro estado, **"dia não operacional"**, para quando o simulador de um sistema não gera arquivo por não ser dia de operação (ver calendário por sistema em `business-context.md`). Esse terceiro estado não deve disparar alerta de falha (ADR-007) nem impedir o Job mensal de considerar o mês completo (ADR-006).

**Nota sobre ordem de geração:** além da dependência de Task na transformação (ADR-006), existe uma dependência de ordem já na própria geração — a cadeia completa é CRM → ERP → TMS → Financeiro, cada sistema lendo o(s) sistema(s) anterior(es) da Landing Zone para a mesma `data_referencia` (ver ADR-011, incluindo o adendo). Como consequência, a cadeia inteira (pedido → produção → expedição → entrega → faturamento) colapsa no mesmo dia na simulação atual — sem defasagem real de tempo entre as etapas.

### Os 5 pipelines

| Pipeline | Fonte | Tabelas Bronze |
|---|---|---|
| ERP (Manufacturing) | dbldatagen | `erp_lotes_producao` |
| Distribution | dbldatagen — separado do ERP no 5º pipeline (ADR-017, demonstração de escala) | `erp_posicoes_estoque`, `erp_notas_expedicao` (nomes mantidos, origem mudou) |
| CRM (Commercial) | dbldatagen + Faker (nomes, empresas, emails) | `crm_pedidos`, `crm_itens_pedido`, `crm_atendimento` |
| TMS (Logistics) | dbldatagen — inclui leitura de temperatura por remessa | `tms_remessas`, `tms_leituras_temperatura`, `tms_comprovantes_entrega` |
| Financeiro (SSC) | dbldatagen — depende de eventos de entrega e pedido | `financeiro_faturas`, `financeiro_contas_receber` |

Schema detalhado de cada tabela, por sistema: `docs/schemas/`.

## 4. Componentes e justificativa

| Componente | Por que esse e não outro |
|---|---|
| **dbldatagen** (+ Faker plugado via `FakerTextFactory`) | Nativo do Databricks, escala em Spark, gera chaves consistentes entre tabelas (essencial pra `lote_id`/`pedido_id` propagados). Faker cobre só os campos de texto realista (nome, endereço, email) — os dois compõem, não competem. |
| **Landing Zone (Volumes) antes de Bronze** | Desacopla geração de ingestão (Lição 1 do projeto anterior); simula fielmente como dados chegam de um sistema real (arquivo pousando), não escrita direta em tabela. |
| **Autoloader com `Trigger.AvailableNow`, só entre Landing e Bronze** | É o único ponto do fluxo genuinamente append-only (arquivo pousado não sofre DELETE/UPDATE depois) — exatamente o caso de uso pra que streaming com checkpoint foi desenhado. |
| **Batch + `MERGE INTO` por chave natural, de Bronze em diante** | Lição 2 do projeto anterior: streaming com checkpoint em camadas que sofrem correção/backfill gera duplicação e problemas de `ignoreDeletes`/`ignoreChanges`. MERGE por chave é idempotente por construção. |
| **Databricks Workflows para orquestração** | Nativo, sem custo extra — desenhado em ondas por causa do limite de 5 tasks concorrentes da Free Edition, não paralelismo total. |
| **AI/BI Dashboards + Genie (nativos)** | Substituem Power BI sem custo adicional; Genie cobre o caso de uso de "pergunta em linguagem natural sobre os dados" sem depender de API externa nem do allowlist de domínios de saída da Free Edition. |
| **Databricks Asset Bundles (IaC)** | Define jobs, pipelines e permissões como código versionado — é a peça de Infrastructure as Code que o projeto pretende demonstrar. |
| **Programação Orientada a Objetos** | Classe base de simulação (`SimuladorDeSistema`) com uma subclasse por sistema; mesma lógica se estende às camadas de transformação (classe base de regras de qualidade reutilizável entre pipelines). Detalhado em ADR próprio antes da implementação. |
| **Widgets (`dbutils.widgets`)** | Parametrização de notebooks/jobs — data de referência, nome do sistema, ambiente — permitindo que o mesmo notebook genérico sirva os 4 (e depois 5+) pipelines sem duplicar código. |

## 5. Limitações conhecidas da Free Edition e como o desenho já as absorve

| Limite | Como o desenho contorna |
|---|---|
| Sem private networking / outbound restrito | Resolvido por design: não há sistema externo — tudo nasce e vive dentro do Databricks (dbldatagen gera, Volumes armazenam) |
| Máximo 5 tasks concorrentes | Orquestração em ondas no Workflows, não paralelismo pleno dos pipelines |
| 1 pipeline Lakeflow ativo por tipo | Optamos por PySpark + Workflows em vez de Lakeflow Declarative Pipelines — também reforça o objetivo de aprendizado de PySpark |
| Streaming contínuo não suportado (só `AvailableNow`/`Once`) | Adotado por design desde o início — nenhuma camada do projeto depende de streaming contínuo |
| 1 SQL warehouse, 2X-Small | Atenção a não sobrecarregar com múltiplos dashboards AI/BI concorrentes durante testes |

## 6. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Volume de código/escopo crescer além do sustentável por uma pessoa | Critério já fixado: regra de negócio só vira feature se gerar dado/evento monitorável pela plataforma; senão fica só como texto no `business-context.md` |
| Falha real (bug) confundida com falha simulada (proposital) | Falhas injetadas são documentadas e isoladas em uma etapa própria do gerador — nunca misturadas ao código de ingestão/transformação |
| Chave de negócio (`lote_id`/`pedido_id`) divergente entre sistemas | Geração via dbldatagen com chaves compartilhadas desde a origem, não geradas independentemente por sistema |

## 7. Evolução — fase de escala

Adicionar o 5º pipeline (separar Distribution do ERP) é o teste de que o desenho é config-driven: deve significar adicionar uma entrada de configuração (schema, regras, tabela destino) e um novo schema Bronze — não reescrever pipelines existentes. Sistemas adicionais futuros (RH, Marketing, Compras) seguem o mesmo critério.

## 8. Próximos passos

**ADRs escritos:**
- `adr-001-landing-zone.md` — geração via dbldatagen+Faker, Landing Zone isolada por sistema
- `adr-002-streaming-vs-batch.md` — streaming só em Landing→Bronze, batch+MERGE nas demais camadas
- `adr-003-programacao-orientada-a-objetos.md` — OOP em simuladores, verificador de qualidade e notificadores
- `adr-004-infrastructure-as-code.md` — Databricks Asset Bundles para os Jobs diário e mensal
- `adr-005-governanca-acesso.md` — RBAC pretendido, Tags real, ABAC descartado (com evidências testadas)
- `adr-006-orquestracao-dependencias.md` — Job diário com Tasks dependentes + Job mensal consultando observabilidade
- `adr-007-alertas.md` — Job Notifications nativo + Notificador customizado em PySpark (evidência de spike SMTP)
- `adr-008-widgets-reprocessamento.md` — parametrização e gatilho de backfill
- `adr-009-retencao-landing-zone.md` — retenção de 30 dias, Job de limpeza agendado
- `adr-010-estrategia-geracao-dados.md` — geração dev/backfill/produção, ACID vs. concorrência
- `adr-011-dependencia-geracao-cross-sistema.md` — ordem de execução CRM → ERP → TMS → Financeiro na geração
- `adr-012-ingestao-autoloader.md` — configuração e convenções da ingestão Landing→Bronze
- `adr-013-transformacao-bronze-silver.md` — função genérica config-driven, 6 categorias de limpeza
- `adr-014-gold-negocio-observabilidade.md` — desenho da camada Gold (overwrite, grão por pergunta de negócio)
- `adr-015-aibi-dashboard.md` — AI/BI Dashboard e Genie Agent, camada de consumo visual e linguagem natural
- `adr-016-fechamento-mensal.md` — consolidação mensal com validação de completude e alerta condicional
- `adr-017-quinto-pipeline-distribution.md` — separação de Distribution do ERP, demonstração de escala

**Infraestrutura já criada:** catalog `poc_pulse_observability`, os 5 schemas, tags aplicadas, Volume `raw` na Landing Zone.

**Código já implementado (`src/`):**
- `simuladores/simulador_base.py` — classe base (OOP, ADR-003)
- `simuladores/sujeira_intencional.py` — 6 funções puras de sujeira, testadas
- `simuladores/simulador_erp.py` — Manufacturing (a partir do ADR-017, só isso)
- `simuladores/simulador_distribution.py` — Distribution, 5º pipeline separado do ERP (ADR-017)
- `simuladores/simulador_crm.py`, `simulador_tms.py`, `simulador_financeiro.py` — os demais simuladores, cada um com chave de negócio própria em toda tabela de evento
- `simuladores/simulador_factory.py` — mapeamento sistema → classe e ordem de execução, 5 pipelines (ADR-011)
- `orquestracao/gerar_dados.py` — notebook orquestrador de geração, com Widgets (ADR-008)
- `orquestracao/ingerir_dados.py` — notebook orquestrador de ingestão, as 11 tabelas
- `orquestracao/promover_seeds.py` — notebook orquestrador dos 6 seeds (Landing → Bronze → Silver)
- `orquestracao/construir_gold.py` — notebook orquestrador da Gold (KPIs de negócio)
- `ingestao/ingestor_autoloader.py` — ingestão genérica Landing→Bronze via Autoloader (ADR-012)
- `transformacao/limpeza_utils.py` — 6 funções puras de limpeza, espelho de `sujeira_intencional.py`
- `transformacao/configuracao_tabelas.py` — configuração declarativa das 11 tabelas de evento
- `transformacao/transformar_bronze_para_silver.py` — função genérica de transformação (ADR-013)
- `transformacao/configuracao_seeds.py`, `promover_seed.py` — configuração e função genérica dos 6 seeds
- `observabilidade/registrar_execucao.py` — registro de execução em `pipeline_runs`, usado pelos orquestradores (ADR-014, Fase C)
- `observabilidade/notificadores.py` — `NotificadorBase`, `NotificadorTabela` (ADR-007)
- `orquestracao/fechar_mes.ipynb` — 6º orquestrador, fechamento mensal financeiro (ADR-016)
- `manutencao/limpar_landing_zone.py` — remoção de partições vencidas, com modo `dry_run` e `data_referencia` parametrizável para teste (ADR-009)
- `orquestracao/limpar_landing_zone.py` — 5º notebook orquestrador, com Widget `dry_run` (status dinâmico em `pipeline_runs`: `dry_run` ou `sucesso`, conforme o modo)

**Infraestrutura como código:** `databricks.yml` + `resources/` (3 Jobs: `job_diario` com 4 Tasks dependentes e Job Notifications configurado, `job_manutencao` com 1 Task, `job_mensal_fechamento` com 1 Task e cálculo automático de mês anterior — todos com `description`, pausados por segurança, `pause_status: PAUSED`). Testado via CLI: `validate`, `deploy`, `run` — todos os Jobs executando com sucesso via Databricks Workflows real, e email de notificação recebido de verdade em teste.

**Estado dos dados:** Bronze e Silver completas nas 17 tabelas, agora sob **5 pipelines** (ERP/Manufacturing separado de Distribution, ADR-017). Gold completa nas 3 fases. Histórico real: **backfill de 67 dias** (16/06 a 21/08/2026, estendido até a data real do teste — sem lacuna entre o fim do backfill e "hoje") executado e validado matematicamente contra o calendário de cada sistema — 49 dias úteis (Manufacturing/Financeiro), 58 dias (Distribution/TMS), 67 dias (Commercial). `pipeline_runs` registrado durante a própria geração desta vez, não como correção retroativa (corrige a causa raiz da Lição 15). `observability_cadeia_fria` usa `LEFT JOIN` com categoria explícita "não verificável", nunca `INNER JOIN` (ADR-014, adendo).

**Alertas e visualização:** `NotificadorBase`/`NotificadorTabela` (ADR-007) testados com dado real (520 violações de `veiculo_incorreto` do backfill). `NotificadorEmail` desenhado como interface, não implementado (decisão de limite pessoal, não técnica — ver ADR-007, adendo). Primeiro AI/BI Dashboard (`Pulse - Observabilidade`, ADR-015) publicado, com 3 painéis sobre `observability.alertas`, `observability_cadeia_fria` e `pipeline_runs` — as decisões de permissão de publicação são aplicação direta da governança já documentada no ADR-005. **Genie Agent** (`Pulse - Observabilidade`) configurado sobre 8 tabelas (3 Gold + 5 observability), validado com 5 perguntas em linguagem natural — incluindo teste deliberado do limite do escopo (pergunta sobre tabela fora dele, respondida com transparência, sem fabricação) (ADR-015, adendo).

**Testes automatizados:** `tests/` (raiz do projeto) — 3 arquivos, 55 testes, 100% de sucesso. Cobrem funções puras determinísticas (`limpeza_utils.py`, `SimuladorFactory`) e funções com aleatoriedade testadas por propriedade, não valor exato (`sujeira_intencional.py`). `chispa` avaliado mas não utilizado nesta fase — as funções testáveis sem sessão Spark ativa não envolvem comparação de DataFrame; permanece disponível para uma futura fase de teste de integração da camada de transformação.

**Job mensal de fechamento financeiro:** `fechar_mes.ipynb` (6º orquestrador) + `job_mensal_fechamento` (3º Job, Asset Bundles) — consolida `gold_fechamento_mensal`, validando completude via `pipeline_runs` antes de aceitar o fechamento. Descoberta e corrigida uma lacuna real (backfill nunca registrava em `pipeline_runs`, ADR-016/Lição 15). Testado nos dois cenários (mês completo/incompleto) e via Job real (`bundle run`).

**Próximo passo real:** migração para produção (`mode: development` → `production`, `pause_status: UNPAUSED` nos 3 Jobs, redeploy). Depois: revisão do AI/BI Dashboard (incluir `gold_fechamento_mensal` e alertas).