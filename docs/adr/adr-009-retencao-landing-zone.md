# ADR-009 — Retenção da Landing Zone

**Status:** Aceito

## Contexto

A Landing Zone (ADR-001) acumula um arquivo JSON por sistema por dia operacional, indefinidamente, caso nada seja feito. Como a Bronze já é a cópia fiel e versionada desses dados (Delta, com histórico via time travel), manter a Landing Zone para sempre depois que o Autoloader já processou o arquivo é custo de armazenamento sem benefício real — exceto no cenário específico de precisar reconstruir a Bronze do zero por corrupção grave.

## Decisão

Reter arquivos na Landing Zone por **30 dias** a partir da data de geração (`data=AAAA-MM-DD` no path). Após esse período, um **Job de limpeza agendado** (notebook PySpark, não recurso nativo de storage) remove os arquivos expirados.

```
Job de limpeza (Databricks Workflow, agendado)
  ├─ Lista partições data=AAAA-MM-DD em cada sistema da Landing Zone
  ├─ Calcula: data_atual - data_particao > 30 dias?
  │     sim → remove os arquivos da partição
  │     não → mantém
```

**Mecanismo escolhido conscientemente, não por padrão:** em ambiente corporativo real, isso costuma ser resolvido por uma lifecycle policy configurada diretamente no storage account (regra automática do cloud provider, sem necessidade de job). A Free Edition usa "Default Storage", totalmente gerenciado pela própria Databricks, sem opção de configurar storage account externo (confirmado na criação do catalog — ver `architecture.md`) — portanto essa opção não está disponível aqui. O Job de limpeza é o caminho que sabemos, com certeza, ser executável neste ambiente.

## Quando implementar

Documentar a decisão agora; **implementar o código apenas quando já existir histórico real acumulado** na Landing Zone (ou seja, depois que `SimuladorDeSistema` e o Job diário já estiverem rodando). Construir e "testar" um job de limpeza antes de existir dado antigo pra limpar só provaria que ele roda sem erro — não que ele de fato limpa o que deveria e preserva o que não deveria.

Teste proposto quando chegar a hora: em vez de esperar 30 dias de calendário real, usar o Widget de reprocessamento (ADR-008) para gerar um backfill de 40-60 dias de `data_referencia` simulada de uma vez, e então validar a limpeza contra esse histórico artificial.

## Alternativas consideradas

- **Manter a Landing Zone indefinidamente**: descartada — custo de armazenamento crescendo sem benefício, já que a Bronze cobre o caso de uso de histórico/auditoria.
- **Reter por um período mais curto (ex.: 7 dias)**: descartada — reduz a margem de recuperação em caso de falha grave detectada tardiamente, sem ganho de custo relevante dado o volume pequeno de uma POC.

## Consequências

- A Bronze passa a ser, na prática, a única fonte de recuperação de histórico com mais de 30 dias — reforça a importância de o Autoloader nunca falhar silenciosamente entre Landing e Bronze.
- O Job de limpeza é mais um artefato a versionar via Databricks Asset Bundles (ADR-004), junto com os Jobs diário e mensal.