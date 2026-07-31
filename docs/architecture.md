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
| `poc_pulse_observability.bronze` | Tabelas Delta, cópia fiel por sistema (`erp`, `crm`, `tms`, `financeiro`) |
| `poc_pulse_observability.silver` | Tabelas Delta limpas, tipadas, deduplicadas, com regras de negócio aplicadas |
| `poc_pulse_observability.gold` | Tabelas Delta com KPIs de negócio (OTIF, taxa de rejeição de lote, DSO etc.) |
| `poc_pulse_observability.observability` | Tabelas Delta com logs de execução, métricas de qualidade, SLA e reconciliação — alimentadas pelos três eixos de observabilidade |

### Os 4 pipelines (Fase 1)

| Pipeline | Fonte | Camada Bronze |
|---|---|---|
| ERP (Manufacturing + Distribution) | dbldatagen — módulos Produção e Estoque na mesma fonte | `poc_pulse_observability.bronze.erp_producao`, `poc_pulse_observability.bronze.erp_estoque` |
| CRM (Commercial) | dbldatagen + Faker (nomes, endereços, emails) | `poc_pulse_observability.bronze.crm_pedidos`, `poc_pulse_observability.bronze.crm_atendimento` |
| TMS (Logistics) | dbldatagen — inclui leitura de temperatura por remessa | `poc_pulse_observability.bronze.tms_remessas`, `poc_pulse_observability.bronze.tms_temperatura` |
| Financeiro (SSC) | dbldatagen — depende de eventos de entrega e pedido | `poc_pulse_observability.bronze.financeiro_faturas` |

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
- `adr-005-governanca-acesso.md` — RBAC pretendido, Tags real, ABAC descartado (com evidências testadas)
- `adr-006-orquestracao-dependencias.md` — Job diário com Tasks dependentes + Job mensal consultando observabilidade
- `adr-007-alertas.md` — Job Notifications nativo + Notificador customizado em PySpark (evidência de spike SMTP)
- `adr-008-widgets-reprocessamento.md` — parametrização e gatilho de backfill

**ADRs ainda pendentes**, antes da implementação de código:
- `adr-001-landing-zone.md`
- `adr-002-streaming-vs-batch.md`
- `adr-003-programacao-orientada-a-objetos.md`
- `adr-004-infrastructure-as-code.md`

**Infraestrutura já criada:** catalog `poc_pulse_observability` e os 5 schemas (`landing`, `bronze`, `silver`, `gold`, `observability`) — confirmados via Catalog Explorer.

Depois dos ADRs pendentes: schema detalhado por sistema (Passo 4) e estrutura de `src/` (Passo 5).