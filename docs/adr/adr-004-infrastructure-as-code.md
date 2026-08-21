# ADR-004 — Infrastructure as Code (Databricks Asset Bundles)

**Status:** Aceito

## Contexto

Um dos objetivos de aprendizado do projeto é Infrastructure as Code — definir a infraestrutura de execução (Jobs, Workflows, parâmetros) como código versionado no repositório, em vez de configuração feita manualmente na UI e não rastreável.

O escopo do que precisa ser "IaC" já está definido por decisões anteriores: o Job diário com Tasks dependentes e o Job mensal (ADR-006), e os Widgets de parametrização (ADR-008).

## Decisão

Usar **Databricks Asset Bundles (DAB)** para definir declarativamente:

- O Job diário (Ingestão → Transformação → Financeiro, com as dependências de Task definidas no ADR-006)
- O Job mensal (fechamento, consultando `observability.pipeline_runs`)
- Os valores padrão dos Widgets (`data_referencia`, `sistema`, `modo_execucao` — ADR-008) para a execução agendada

Estrutura no repositório:

```
databricks.yml          ← definição raiz do bundle
resources/
  job_diario.yml
  job_mensal.yml
```

Deploy via Databricks CLI (`databricks bundle deploy`), autenticado por **Personal Access Token** — não por service principal, porque o Free Edition não disponibiliza essa identidade (ver ADR-005). Essa é uma limitação de ambiente já registrada, não uma escolha de design.

Um único target de deployment (`dev`) é definido — não existem ambientes `staging`/`prod` a versionar separadamente, porque a Free Edition opera com um único workspace. Essa ausência é documentada explicitamente no bundle, para não parecer omissão.

## Alternativas consideradas

- **Configuração manual via UI (criar Jobs clicando na tela)**: descartada — é o que o projeto já fez até aqui para infraestrutura exploratória (catalog, schemas), mas não escala como prática para Jobs que mudam com frequência durante o desenvolvimento, e não é versionável.
- **Terraform (provider oficial da Databricks)**: mais comum em ambientes corporativos com múltiplos serviços cloud além de Databricks. Descartado aqui por adicionar uma ferramenta e linguagem extra (HCL) sem necessidade — o escopo do projeto é single-workspace, e o DAB é nativo, YAML, e suficiente para esse tamanho.

## Consequências

- Qualquer mudança nos Jobs (novo pipeline na fase de escala, ajuste de schedule) passa a ser uma mudança de código revisável via Pull Request — não um clique na UI sem histórico.
- A ausência de múltiplos ambientes fica documentada como limitação de plataforma, não como lacuna de maturidade de IaC.
- Autenticação via Personal Access Token (não service principal) é uma limitação a mencionar com transparência caso o projeto seja avaliado por alguém familiarizado com ambientes corporativos reais, onde essa distinção importa.

## Adendo — implementação real e decisões confirmadas

**Estrutura real**, ligeiramente diferente da planejada (2 Jobs, não 3 — o mensal não foi implementado, já que `financeiro_fechamento_mensal` nunca foi codado):

```
databricks.yml
resources/
  job_diario.yml       (4 Tasks: gerar_dados → ingerir_dados → promover_seeds → construir_gold)
  job_manutencao.yml   (1 Task: limpar_landing_zone, agendado semanal)
```

**Web Terminal**: confirmado disponível na Free Edition, mas exige compute serverless "acordado" primeiro — a primeira tentativa retornou "Web terminal is only available on running compute"; rodar qualquer célula no notebook antes resolveu.

**Databricks CLI**: já vem pré-instalado no Web Terminal (v1.12.1 confirmado) — nenhuma instalação manual necessária.

**Personal Access Token — escopo granular, não `all-apis`**: a Free Edition oferece seleção de escopos específicos na criação do token (recurso mais novo que o esperado). Escolhidos `bundle`, `bundle-deployments`, `jobs`, `workspace` — suficientes para `validate`/`deploy`/`run`, sem precisar do escopo total "not recommended". Um token foi exposto acidentalmente durante os testes (apareceu em texto puro num `cat ~/.databrickscfg` capturado em print) — revogado e substituído; lição registrada abaixo. Comando de verificação recomendado dali em diante: `databricks current-user me` (confirma autenticação sem nunca exibir o token), não `cat` no arquivo de config.

**`mode: development`, mantido conscientemente**: gera o prefixo `[dev nome_usuario]` nos Jobs e ativa *source-linked deployment* — os Jobs implantados referenciam os notebooks do workspace diretamente, sem exigir `deploy` a cada edição. Migrar para `mode: production` removeria o prefixo, mas trocaria para paths fixos exigindo redeploy manual a cada mudança de notebook — voltaria a expor o mesmo risco de dessincronia já visto na Lição 7. Migração para `production` fica para quando o projeto estiver pronto para rodar sem supervisão constante, não agora.

**`pause_status: PAUSED` nos dois Jobs**: nenhum agendamento roda sozinho até ativação manual e consciente — mesmo princípio do `dry_run` do `job_manutencao`, camada dupla de segurança.

**Tags nos Jobs**: reaproveitada a mesma convenção já usada no Unity Catalog (`ambiente`, `dominio`, `projeto`) — consistência entre as duas camadas de governança do projeto.

**Testado com sucesso**: `databricks bundle validate` (sintaxe), `databricks bundle deploy` (criação real dos 2 Jobs), `databricks bundle run job_diario` (execução real das 4 Tasks, ~3 minutos, todas com sucesso — após o backfill completo descrito no ADR-010, adendo).

**Incidente encontrado e não escondido**: a primeira tentativa de `bundle run job_diario` falhou com `CloudFileNotFoundException` — detalhado no ADR-012 (adendo) e na Lição 11, `docs/licoes-aprendidas.md`.

## Segundo adendo — migração real para produção (mode: production, agendamento ativo)

Executada quando o projeto já tinha 5 pipelines completos, 3 Jobs testados individualmente via `bundle run`, e backfill de 67 dias validado — critério de "pronto para rodar sem supervisão constante" definido no adendo anterior.

**Exigência nova, não vista em `development`:** `mode: production` exige `workspace.root_path` explícito no `databricks.yml` — sem ele, `bundle validate` falha com `"target with 'mode: production' must set 'workspace.root_path' to make sure only one copy is deployed"`. Adicionado seguindo o padrão sugerido pela própria mensagem de erro: `/Workspace/Users/<usuario>/.bundle/${bundle.name}/${bundle.target}`. Confirmado, na prática, que essa exigência existe para evitar múltiplas cópias implantadas do mesmo Bundle — proteção ativa, não burocracia vazia.

**Migração não duplicou os Jobs**: a mudança de `mode` e `root_path`, seguida de `bundle deploy`, atualizou os 3 Jobs existentes (confirmado visualmente — 3 Jobs na lista, não 6) em vez de criar cópias novas ao lado das antigas. O Databricks tratou como atualização de implantação existente, não implantação nova.

**Sequência aplicada**: 1 mudança de `mode` (validada e implantada uma vez, afetando os 3 Jobs de uma vez) → depois os 3 `pause_status: PAUSED → UNPAUSED`, um Job por vez, cada um com seu próprio `validate`/`deploy` isolado — permitindo confirmar cada ativação individualmente antes de seguir para a próxima, em vez de ativar tudo de uma vez sem checkpoint intermediário.

**Decisão consciente sobre cota da Free Edition**: a documentação oficial confirma que a Free Edition opera sob política de "fair use" sem limite numérico publicado (nem DBU-horas, nem execuções por dia) — decidido prosseguir mesmo com essa incerteza, apoiado em estimativa baseada em medição real (job_diario ~3min/dia, os outros dois esporádicos) como carga leve, com acompanhamento manual dos primeiros dias em vez de uma garantia formal de que a cota não será excedida.

**Resultado confirmado**: os 3 Jobs em "Scheduled", prefixo `[dev...]` removido, agendamento ativo — `job_diario` diariamente às 06:00, `job_manutencao` semanalmente (segunda, 07:00), `job_mensal_fechamento` mensalmente (dia 1, 06:00), todos America/Sao_Paulo.