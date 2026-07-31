# ADR-006 — Orquestração e dependências entre pipelines

**Status:** Aceito

## Contexto

O domínio de negócio define duas dependências reais entre os 4 pipelines:
1. O Silver/Gold do Financeiro faz reconciliação (valor faturado vs. valor do pedido), o que exige que Commercial e Logistics já tenham processado o dia.
2. O fechamento mensal do SSC Financeiro só pode ocorrer depois que os 4 pipelines processaram com sucesso todos os dias do período.

Esses dois requisitos, apesar de relacionados, operam em escalas de tempo diferentes (diário vs. mensal) e não deveriam ser resolvidos pelo mesmo mecanismo.

## Decisão

### Job diário — 1 Workflow, Tasks com dependência nativa

```
Ingestão ERP ──┐
Ingestão CRM ──┼──► Transformação ERP  ──┐
Ingestão TMS ──┤    Transformação CRM  ──┼──► Transformação Financeiro   ──► Gold (todos)
Ingestão Fin ──┘    Transformação TMS  ──┘    (depende de CRM + TMS prontos)
                                                        │
                                                        ▼
                                         Task de log (sempre roda, mesmo se algo falhar)
                                         grava em poc_pulse_observability.observability.pipeline_runs
```

A Transformação Financeiro depende explicitamente (via configuração de dependência de Task no Workflow) da conclusão de Transformação CRM e Transformação TMS — não é uma regra de negócio implícita no código, é uma dependência estrutural do Job.

### Job mensal — separado, consultando a própria plataforma de observabilidade

```
Job Mensal (gatilho no fim do mês)
  ├─ Consulta poc_pulse_observability.observability.pipeline_runs
  ├─ Verifica: os 4 pipelines rodaram com sucesso todo dia do mês?
  │     sim → Task de Fechamento Mensal
  │     não → Falha com mensagem clara, não fecha mês incompleto
```

O Job Mensal usa `pipeline_runs` como pré-condição de execução — a plataforma de observabilidade é operacionalmente consultada, não apenas relatada.

## Alternativas consideradas

- **4 Jobs independentes encadeados via "Run Job" Task:** mais apropriado quando cada pipeline tem um time diferente responsável. Descartado aqui — com 1 pessoa e 4-5 pipelines, adicionaria complexidade de coordenação sem ganho real.

## Consequências

- Falha em uma Task (ex.: Ingestão TMS) impede a execução das Tasks dependentes downstream (Transformação Financeiro), evitando reconciliação com dado incompleto.
- O Job Mensal depende de dado de observabilidade estar correto e completo — reforça a necessidade de a Task de log rodar mesmo quando outras falham.
- Respeita o limite de 5 tasks concorrentes da Free Edition — o desenho já assume execução em cadeia parcial, não paralelismo pleno dos 4 pipelines.