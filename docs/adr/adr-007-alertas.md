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

## Adendo — implementação real e fechamento de escopo (NotificadorEmail descartado)

**Job Notifications, implementado via YAML, não UI:** confirmado que Jobs gerenciados por Asset Bundles não expõem configuração de notificação pela tela — é obrigatório usar `email_notifications`/`health` no YAML (`resources/job_diario.yml`), coerente com o próprio Databricks orientando "modify bundle sources and redeploy" para qualquer edição. `on_failure` e `on_duration_warning_threshold_exceeded` configurados para 2 endereços (real + fictício de simulação de "grupo de trabalho"); `health.rules` com limiar de 900s (15min), acima do tempo real medido (~3min). Testado e confirmado: email real recebido, aviso de duração visível na tela de Runs.

**`NotificadorBase`/`NotificadorTabela` implementados como desenhado**, com uma correção de robustez: gravação usa schema explícito (`StructType`), não inferência automática — mesma correção já aplicada em `registrar_execucao_pipeline` (`CANNOT_DETERMINE_TYPE` quando uma coluna pode vir nula numa única linha). Testado com dado genuíno do projeto: 520 violações reais de `veiculo_incorreto` (de `observability_cadeia_fria`, backfill de 60 dias) geraram e registraram um alerta com sucesso — não só exemplo fabricado.

**`NotificadorEmail` — implementado como interface, não como código funcional (Opção C).** Antes de descartar, testada a viabilidade de guardar credencial com segurança: Databricks Secret Scopes (`databricks secrets create-scope`) confirmados funcionais no Free Edition — criado, verificado (`list-scopes`) e removido com sucesso (`delete-scope`), validando que o mecanismo existe caso o projeto retome esse canal no futuro. O bloqueio real foi outro: gerar a senha de aplicativo necessária para SMTP no Outlook exige verificação em duas etapas ativada na conta, e o autor optou conscientemente por não ativar 2FA na conta pessoal apenas para viabilizar este teste de portfólio — decisão de limite pessoal, não técnica. `NotificadorWebhook`, cogitado no desenho original, também não foi implementado (mesma decisão de escopo, nunca chegou a ser necessário testar).

**Escopo final de canais ativos:** Job Notifications (execução) + `NotificadorTabela` (qualidade/negócio) — 2 canais reais, cobrindo os 3 eixos de observabilidade já definidos. O contrato `NotificadorBase` está provado com uma implementação real (`NotificadorTabela`); a ausência de uma segunda implementação de canal externo não compromete a demonstração de "canal plugável" via OOP (ADR-003), que é sobre o contrato, não sobre quantidade de implementações.

**Consumo dos alertas:** `docs/adr/adr-015-aibi-dashboard.md` — o primeiro AI/BI Dashboard do projeto, com um painel dedicado a `observability.alertas`.