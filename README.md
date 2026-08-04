# poc-pulse-health-observability

Plataforma de observabilidade de pipelines de dados — POC simulando a área de dados de um conglomerado fictício de Life Sciences (**Pulse Health Group**), construída inteiramente em **Databricks Free Edition**.

## O que é este projeto

Em vez de construir só pipelines, este projeto constrói uma plataforma que **monitora** pipelines — respondendo perguntas como: quais falharam, quanto demoraram, qual SLA foi violado, qual regra de qualidade foi quebrada, e se o dado de negócio reconcilia entre sistemas.

A observabilidade cobre três eixos:

| Eixo | Pergunta que responde |
|---|---|
| Execução | O pipeline rodou? Falhou onde? Demorou além do esperado? |
| Qualidade | O volume é normal? Alguma regra foi violada? |
| Negócio | O indicador final bate com a origem? |

## Cenário simulado

**Pulse Health Group**: uma holding fictícia com 4 empresas e um serviço financeiro compartilhado, integrados por um fluxo de dados ponta a ponta — pedido → produção → estoque → entrega → faturamento, com rastreabilidade de lote atravessando toda a cadeia.

Detalhes completos das 5 áreas de negócio, entidades, regras e KPIs: [`docs/business-context.md`](docs/business-context.md).

## Arquitetura

Medallion (`landing` → `bronze` → `silver` → `gold` → `observability`) sobre Unity Catalog, com geração de dados sintéticos via `dbldatagen` + `Faker`, ingestão via Autoloader, transformação via batch + `MERGE INTO`, e orquestração via Databricks Workflows.

Arquitetura completa, limitações da Free Edition e como foram absorvidas no desenho: [`docs/architecture.md`](docs/architecture.md).

Schema detalhado por sistema (campos, tipos, chaves de negócio, sujeira intencional de origem): [`docs/schemas/`](docs/schemas/).

## Decisões técnicas (ADRs)

Cada decisão de arquitetura relevante está documentada com contexto, alternativas consideradas e consequências:

| ADR | Tema |
|---|---|
| [001](docs/adr/adr-001-landing-zone.md) | Landing Zone |
| [002](docs/adr/adr-002-streaming-vs-batch.md) | Streaming vs. batch por camada |
| [003](docs/adr/adr-003-programacao-orientada-a-objetos.md) | Programação Orientada a Objetos |
| [004](docs/adr/adr-004-infrastructure-as-code.md) | Infrastructure as Code |
| [005](docs/adr/adr-005-governanca-acesso.md) | Governança de acesso (RBAC, Tags, ABAC) |
| [006](docs/adr/adr-006-orquestracao-dependencias.md) | Orquestração e dependências entre pipelines |
| [007](docs/adr/adr-007-alertas.md) | Alertas (detecção → notificação) |
| [008](docs/adr/adr-008-widgets-reprocessamento.md) | Widgets e reprocessamento/backfill |
| [009](docs/adr/adr-009-retencao-landing-zone.md) | Retenção da Landing Zone |

## FinOps

Simulações de custo (Databricks Pricing Calculator e Azure Pricing Calculator) para um cenário hipotético de produção: [`docs/custos/`](docs/custos/).

## Stack

Databricks Free Edition · PySpark · Delta Lake · Unity Catalog · Databricks Asset Bundles · GitHub Actions (planejado) · AI/BI Dashboards + Genie

## Status

Em desenvolvimento — fase de documentação e arquitetura concluída (contexto de negócio, arquitetura técnica, 8 ADRs, FinOps); implementação de código (`src/`) em andamento.

## Licença

MIT — ver [`LICENSE`](LICENSE).