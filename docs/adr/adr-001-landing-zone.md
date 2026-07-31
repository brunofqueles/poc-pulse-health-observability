# ADR-001 — Landing Zone

**Status:** Aceito

## Contexto

O projeto precisa gerar dados sintéticos para 4 sistemas (ERP, CRM, TMS, Financeiro) de forma que simule fielmente como dados chegam de fontes reais — não como uma escrita direta e artificial em tabela Delta.

Esta decisão incorpora uma lição de um projeto anterior (`poc-lakehouse-food-latam`): gravar dados sintéticos diretamente em tabelas Delta acopla a etapa de "gerar/receber dado" à etapa de "ingerir dado", dificultando testar cada uma isoladamente e não reproduzindo o padrão real de chegada de dados corporativos (arquivo pousando em armazenamento intermediário).

## Decisão

Adotar uma Landing Zone baseada em Unity Catalog Volumes, com geração via `dbldatagen` (+ `FakerTextFactory` para campos de texto realista), organizada em estrutura Hive-style, **isolada por sistema na raiz do path** — não por uma dimensão de negócio compartilhada — porque os 4 sistemas têm schemas distintos entre si:

```
/Volumes/poc_pulse_observability/landing/erp/data=AAAA-MM-DD/*.json
/Volumes/poc_pulse_observability/landing/crm/data=AAAA-MM-DD/*.json
/Volumes/poc_pulse_observability/landing/tms/data=AAAA-MM-DD/*.json
/Volumes/poc_pulse_observability/landing/financeiro/data=AAAA-MM-DD/*.json
```

- **Sistema como raiz do path**: permite um Autoloader (`cloudFiles`) por sistema, cada um lendo apenas o schema que lhe corresponde.
- **`data=` como partição Hive-style dentro de cada sistema**: permite poda de partição por ferramentas de ingestão sem precisar ler o conteúdo dos arquivos — eficiente mesmo em volume maior.
- **Geração e ingestão desacopladas**: um job gera o arquivo (Landing), outro o lê (Autoloader → Bronze) — cada etapa testável isoladamente, com reprocessamento e auditoria facilitados.

## Alternativas consideradas

- **Escrita direta em tabela Delta pelo simulador**: descartada — reabre exatamente o problema identificado na lição do projeto anterior (acoplamento, sem simulação fiel de fonte externa).
- **Partição única por dimensão de negócio compartilhada (ex.: país, como no projeto anterior)**: descartada aqui — os 4 sistemas do Pulse não compartilham uma dimensão comum equivalente; schemas distintos exigem isolamento por sistema, não uma partição transversal.

## Consequências

- Cada sistema tem seu próprio Autoloader, schema e stream de ingestão — mais artefatos de código, mas isolamento genuíno entre pipelines.
- A separação Landing → Bronze é o único ponto do fluxo de dados que usa Structured Streaming (ver ADR-002), porque é o único genuinamente append-only.
- A estrutura `<sistema>/data=AAAA-MM-DD/` é o que viabiliza o parâmetro `data_referencia` do Widget de reprocessamento (ver ADR-008): reprocessar um dia específico significa apontar o Autoloader/gerador para essa mesma convenção de partição.