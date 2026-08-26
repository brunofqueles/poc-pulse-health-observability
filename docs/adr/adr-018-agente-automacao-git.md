# ADR-018 — Agente de Automação Git

**Status:** Aceito

## Contexto

Depois de mais de 75 PRs mergeados manualmente ao longo do projeto (branch → editar → commit → PR → merge → apagar branch, sempre pela interface do Databricks + GitHub), a disciplina de Git estava plenamente dominada — condição que o projeto já havia definido desde o início como pré-requisito para automatizar esse fluxo (item de backlog "Agente de automação de commits/PR — só após dominar o fluxo manual").

Motivação adicional: mais elementos de IA estão previstos para entrar no projeto — um agente que automatiza a mecânica de Git reduz atrito para incorporá-los.

## Decisão

**Nível A de automação** (entre 3 níveis considerados — ver Alternativas): o agente cria branch, commita e abre o PR sozinho; **merge continua sempre manual**, revisado por uma pessoa antes de qualquer código entrar em `main`. Nenhum método de merge é implementado na classe, por decisão deliberada — não é limitação técnica, é escolha de risco.

**Credencial:** GitHub Personal Access Token (classic, escopo `repo` apenas), guardado em Databricks Secret Scope (`pulse-secrets/github-pat`) — mesmo padrão já validado com a senha de aplicativo do Gmail (ADR-007, segundo adendo).

**Mecanismo de execução:** API REST do GitHub (`requests`), não `git` CLI local — decisão simples dado o ambiente (Web Terminal não tem o repositório clonado como working tree gerenciável da forma que o fluxo `git add/commit/push` tradicional exige).

**Escopo MVP: 1 arquivo por commit**, via `PUT /repos/{owner}/{repo}/contents/{path}` (Contents API) — confirmado contra a documentação oficial do GitHub antes de implementar. Múltiplos arquivos num único commit exigiriam a Git Database API (Blobs → Tree → Commit → Ref) ou GraphQL (`createCommitOnBranch`) — superfície de implementação bem maior, sem necessidade real comprovada ainda. Decisão de escopo, não limitação da API: o GitHub suporta múltiplos arquivos por commit, só não pelo caminho mais simples.

**Estrutura:** `AgenteAutomacaoGit` com 4 métodos — `criar_branch`, `commitar_arquivo`, `abrir_pr` (as 3 operações atômicas) e `publicar_mudanca` (ponto de entrada único, orquestra as 3 em sequência, interrompendo cedo se qualquer etapa falhar, sem tentar operações seguintes sobre estado inconsistente).

## Alternativas consideradas

- **Nível B (merge automático se testes passarem)** e **Nível C (tudo automático)**: descartados — nenhuma rede de segurança automatizada (mesmo testes) substitui revisão humana antes de código entrar em produção; o valor de portfólio do projeto também depende de demonstrar julgamento humano no controle final, não abrir mão dele.
- **`git` CLI local no Web Terminal**: descartada para este MVP — exigiria gerenciar clone, working tree e estado local, mais complexidade sem benefício claro sobre a API REST direta.

## Consequências

- O agente reduz passos manuais (criar branch na interface, colar conteúdo, escrever mensagem, abrir PR), mas o julgamento final (merge) permanece 100% humano — coerente com a disciplina de Git já demonstrada nos 75+ PRs anteriores do projeto.
- Limite real do MVP: uma mudança que abrange vários arquivos ainda precisa de várias chamadas de `publicar_mudanca` (uma branch/commit/PR por arquivo) ou do fluxo manual já dominado — não é um problema at bloqueante, apenas uma fronteira clara de escopo desta primeira versão.
- Validado em 3 camadas antes deste registro: `criar_branch` isolado, `commitar_arquivo` isolado (arquivo de teste, depois removido via PR fechado sem merge), `abrir_pr` isolado — e este próprio ADR é o primeiro uso real de `publicar_mudanca`, publicando sua própria documentação através do mecanismo que documenta.