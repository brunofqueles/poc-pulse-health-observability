# ADR-010 — Estratégia de geração de dados: desenvolvimento, backfill e produção

**Status:** Aceito

## Contexto

`data_referencia` é um Widget (ADR-008), não a data real do relógio — o calendário simulado do projeto é inteiramente desacoplado do tempo real. Isso levanta uma pergunta que precisa de resposta explícita antes da implementação dos simuladores: como lidar com a lacuna entre "quando codamos/testamos" e "que história de dados o projeto deveria ter"?

Esta decisão incorpora uma lição de um projeto anterior: manter um job auxiliar temporário ativo simultaneamente a um Workflow definitivo causou **duplicação real de dados** por race condition — a proteção "check-then-write" usada não era atômica, e as duas execuções concorrentes, cada uma legítima isoladamente, resultaram em escrita duplicada.

## Por que ACID não resolve isso sozinho

Uma distinção importante, para não tratar ACID como proteção suficiente: ACID (Atomicidade, Consistência, Isolamento, Durabilidade) é uma propriedade nativa do Delta Lake, garantida automaticamente pelo motor em toda operação sobre tabela Delta — não é algo implementado por nós. Mas ACID protege contra **corrupção** (escrita pela metade, conflito de arquivo), não contra **duplicação lógica de negócio**. Duas execuções concorrentes, cada uma decidindo de forma independente e "correta" que precisa inserir um registro, resultam em duas escritas válidas do ponto de vista do Delta — e ainda assim duplicadas do ponto de vista do negócio.

A proteção real contra duplicação vem da combinação de três camadas, cada uma cobrindo um risco diferente:

| Camada | O que evita | Onde está decidido |
|---|---|---|
| ACID (nativo do Delta) | Corrupção, escrita pela metade | Automático em Bronze/Silver/Gold |
| `MERGE INTO` por chave natural | Duplicação por reprocessamento **sequencial** do mesmo dado | ADR-002 |
| Nunca rodar processos concorrentes sobre o mesmo destino | Duplicação por execuções **simultâneas** | Esta decisão |

**Ponto adicional:** a Landing Zone (Volumes, `dbutils.fs.put`) não é tabela Delta — é escrita de arquivo comum, **sem nenhuma garantia ACID**. A regra de "nunca concorrência" é ainda mais crítica ali, por não haver rede de segurança do motor nessa camada.

## Decisão

### Fase de desenvolvimento (atual)

Nenhum job agendado ativo. Simuladores são executados **manualmente**, um de cada vez, via notebook de teste — sem concorrência possível, porque existe apenas um processo rodando por vez. Dados gerados nesta fase são **descartáveis**, sem compromisso de continuidade histórica dia a dia.

### Backfill único (ao final da implementação)

Quando os 4 simuladores + ingestão + transformação estiverem prontos e validados: limpeza completa de Landing Zone/Bronze/Silver/Gold, seguida de **um único job sequencial** (não paralelo) que percorre uma janela de datas simuladas (ex.: últimos 60-90 dias), respeitando o calendário de cada sistema (`business-context.md`), usando o mesmo Widget de reprocessamento (ADR-008). Isso gera a história "oficial" do projeto de forma deliberada, não acumulada por acaso durante os testes.

### Produção (fase futura)

Um único Workflow agendado (ADR-006), sem nenhum job auxiliar ou temporário coexistindo. Qualquer necessidade de reprocessamento pontual usa o mesmo Widget (ADR-008), nunca um segundo job paralelo ao definitivo — é exatamente essa coexistência que causou o incidente do projeto anterior.

## Alternativas consideradas

- **Manter um job de geração contínua rodando desde já, em paralelo ao desenvolvimento**: descartada — reproduziria o cenário do incidente anterior (job temporário + processo principal, concorrentes), além de misturar falha de código em desenvolvimento com falha operacional real nos alertas (ADR-007).
- **Tentar preservar continuidade real dia a dia durante a implementação**: descartada — implementação ainda está sujeita a mudança de schema e código, tornando qualquer histórico acumulado nessa fase não confiável; mais simples e mais seguro tratar como descartável e gerar a história oficial de uma vez, no fim.

## Consequências

- Nenhum dado gerado durante a fase de desenvolvimento precisa ser preservado ou tratado como confiável — simplifica testes e depuração.
- O backfill único é o primeiro uso real do Widget de reprocessamento em escala (múltiplos dias de uma vez), servindo também como teste de carga leve do mecanismo antes da produção.
- A regra "nunca dois processos concorrentes sobre o mesmo destino" vale tanto para Jobs do Databricks Workflows quanto para qualquer execução manual paralela (ex.: duas pessoas, ou você em duas abas, rodando o mesmo notebook ao mesmo tempo) — vale como princípio geral do projeto, não só para jobs agendados.