# ADR-016 — Fechamento mensal financeiro

**Status:** Aceito

## Contexto

`ADR-006` já previa um Job mensal, consultando `pipeline_runs` como pré-condição antes de considerar o fechamento válido — nunca implementado até esta fase. `ADR-014` (Gold) cobria KPIs diários; faltava a consolidação mensal com validação de completude.

## Decisão

`fechar_mes.ipynb` (6º orquestrador): lê `mes_referencia` (Widget, opcional — se vazio, calcula o mês anterior à data de execução), valida completude comparando dias úteis esperados (calendário Seg-Sex do Financeiro) contra `pipeline_runs` com `status = sucesso`, consolida `gold_fechamento_mensal` (`MERGE` por `mes_referencia`, idempotente), e dispara alerta via `NotificadorTabela` quando `fechamento_valido = false`.

**Job próprio** (`job_mensal_fechamento`, não Task dentro de outro Job) — frequência mensal é semanticamente distinta de diária/semanal, mesma separação de responsabilidade já usada para `job_manutencao`.

### Cálculo automático de "mês anterior" — limitação real do Databricks contornada

Confirmado (documentação oficial): dynamic value references do Databricks (`{{job.start_time.[year]}}`, `{{job.start_time.iso_date}}` etc.) fornecem componentes da data de execução, mas **não fazem aritmética de data** — não existe um `{{job.start_time.previous_month}}`. Solução: o Job passa `data_execucao` (`{{job.start_time.iso_date}}`) como parâmetro; o cálculo de "mês anterior" acontece em Python, dentro do notebook, não no YAML. `mes_referencia` continua aceitando sobrescrita manual (usada nos testes desta fase), com o cálculo automático como *fallback* apenas quando vazio.

## Descoberta durante a implementação: lacuna em `pipeline_runs`

Ao testar `fechar_mes` pela primeira vez contra julho (mês que sabíamos estar completo, coberto pelo backfill de 60 dias), a validação retornou `fechamento_valido = false`, com **todos** os 23 dias úteis "faltando" — mesmo o dado de Bronze/Silver/Gold de julho existindo e já validado matematicamente antes.

**Causa raiz:** `backfill_completo.ipynb` chamava `SimuladorFactory` diretamente, num loop manual — nunca passou por `gerar_dados.ipynb` (o único orquestrador que registra em `pipeline_runs`). O **dado** de julho existia; o **log de auditoria** de julho nunca foi criado. `fechar_mes` funcionou exatamente como desenhado: recusou validar um fechamento sem prova de execução registrada, mesmo o dado estando correto — expondo uma lacuna real de rastreabilidade, não um bug do fechamento em si.

**Correção — reconstrução retroativa, não regeneração de dado:** adicionada uma célula em `backfill_completo.ipynb` que reconstrói os 240 registros de `pipeline_runs` (60 dias × 4 sistemas) com base em evidência já conhecida (o próprio log de execução impresso do backfill original, mais a checagem de calendário `simulador.opera_em()` — sem chamar `gerar_registros()` de novo). Cada registro é marcado explicitamente com `"reconstrucao_retroativa": True` nos detalhes, para nunca ser confundido com execução em tempo real.

## Validado nos dois cenários

- **Julho** (mês completo, após a correção retroativa): `fechamento_valido: true`, 4.377 faturas, taxa de divergência 8,0% (consistente com o já validado em outras fases). Sem alerta.
- **Agosto** (mês incompleto, 11 de 21 dias úteis faltando): `fechamento_valido: false`, alerta disparado e confirmado em `observability.alertas`.
- **Cálculo automático**: testado com os dois Widgets vazios, calculou corretamente `2026-07` a partir da data real do dia do teste (20/08/2026).
- **Job real** (`databricks bundle run job_mensal_fechamento`): executado com sucesso via Databricks Workflows, `MERGE` idempotente confirmado (2 linhas em `gold_fechamento_mensal`, não 3, após reexecução).

## Alternativas consideradas

- **Task dentro de `job_diario`**: descartada — frequência mensal não deveria rodar diariamente só para verificar "ainda não é dia 1".
- **Ignorar a lacuna de `pipeline_runs` e ajustar a validação para aceitar dado sem log**: descartada — enfraqueceria o propósito real da validação (provar execução, não só existência de dado), e esconderia uma lacuna de rastreabilidade genuína em vez de corrigi-la.

## Consequências

- Qualquer geração de dado fora do orquestrador oficial (`gerar_dados.ipynb`) — incluindo scripts de backfill futuros — precisa registrar em `pipeline_runs` explicitamente, ou ficará invisível para validações de completude como esta.
- `gold_fechamento_mensal` é a primeira tabela Gold cuja gravação depende de uma consulta a `observability.pipeline_runs`, não só às camadas Silver — reforça `pipeline_runs` como peça operacional ativa, não apenas um log passivo.