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