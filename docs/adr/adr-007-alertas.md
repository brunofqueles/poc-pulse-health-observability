# ADR-007 — Alertas (detecção → notificação)

**Status:** Aceito

## Contexto

A plataforma detecta eventos nos três eixos de observabilidade (execução, qualidade, negócio), mas detecção sem notificação é apenas metade de uma plataforma de observabilidade. Foi necessário decidir: quais eventos merecem alerta, e por qual mecanismo.

## Decisão

### Eventos que disparam alerta — um por eixo, não um por regra

| Eixo | Evento | Fonte |
|---|---|---|
| Execução | SLA de pipeline estourado ou falha de Task | `poc_pulse_observability.observability.pipeline_runs` |
| Qualidade | Violação de cadeia fria (temperatura fora de 2–8°C) | tabela de qualidade em `observability` |
| Negócio | Reconciliação financeira divergente (faturado ≠ pedido) | `observability` |

Restrito a três eventos deliberadamente — alertar em excesso é tão prejudicial quanto não alertar, pois transforma o alerta em ruído ignorável.

### Mecanismos — dois, para propósitos diferentes

**1. Job Notifications (nativo, eixo Execução)**
Configurado no próprio Workflow: notificação por email em `Failure` e `Duration warning` (não apenas Failure — SLA estourado é "terminou devagar", não necessariamente "falhou").

**Evidência:** teste real executado — Task `bronze_vendas` falhou propositalmente, notificação chegou por email ao endereço real cadastrado; o endereço fictício de teste (`data-eng-alerts@empresa-fake.com`) não recebeu, como esperado (endereço não existe).

**2. Notificador customizado em PySpark (eixos Qualidade e Negócio)**

Decisão consciente de não usar o recurso nativo **Alerts** (SQL Alerts) para esses dois eixos, para reforçar o objetivo de aprendizado de OOP/PySpark do projeto — mesmo havendo alternativa nativa mais simples.

Desenho com canal plugável:

```
VerificadorDeQualidade (classe)
  └─ verificar(df, regra) → retorna violações encontradas

NotificadorBase (classe abstrata)
  ├─ NotificadorEmail (smtplib)
  ├─ NotificadorWebhook (Slack/Teams) — alternativa, não implementada na Fase 1
  └─ NotificadorTabela (grava em observability.alertas) — fallback garantido, sempre funciona
```

`NotificadorTabela` nunca falha (é apenas um MERGE em tabela Delta) e serve como registro durável do alerta, consultável pelo AI/BI Dashboard independentemente da entrega por email ter funcionado.

**Evidência de viabilidade de rede:** spike documentado em `src/spikes/teste_conexao_smtp.py` — conexão de teste a `smtp.gmail.com:587` (sem autenticação, sem envio real) retornou sucesso, confirmando que outbound SMTP não está bloqueado no Free Edition.

**Pendência registrada:** o host de produção do `NotificadorEmail` deve ser o do Outlook (`smtp.office365.com` ou `smtp-mail.outlook.com`, porta 587), já que o email real do projeto é `bruno.quelestech@outlook.com`, não Gmail. O spike validou conectividade SMTP em geral, não esse host específico — a confirmar antes da implementação final.

## Consequências

- Dois mecanismos de alerta coexistem no projeto (nativo para execução, customizado para qualidade/negócio) — decisão documentada para não parecer inconsistência de stack.
- `NotificadorTabela` garante que nenhum alerta se perde mesmo se o canal de email falhar, às custas de exigir consulta ao dashboard para ver alertas não urgentes.
- Autenticação SMTP (usuário + senha de aplicativo) fica pendente de implementação — não é limitação de rede, é configuração de credencial a resolver na fase de código.