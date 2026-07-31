# ADR-005 — Governança de acesso (RBAC, Tags e ABAC)

**Status:** Aceito

## Contexto

O projeto precisa demonstrar um modelo de governança de acesso ao Unity Catalog condizente com um ambiente corporativo real, mesmo rodando em Databricks Free Edition — ambiente de usuário único, sem Account Console.

## Decisão

Adotar três mecanismos, cada um avaliado e testado separadamente:

### 1. RBAC por grupo — modelo pretendido, não executável

Papéis definidos para o catalog `poc_pulse_observability`:

| Time / Identidade | Papel | Permissões pretendidas |
|---|---|---|
| Arquitetura | Admin do catalog | `ALL PRIVILEGES` em `poc_pulse_observability` |
| Engenharia de Dados (humano, interativo) | Constrói e mantém o código do pipeline | `USE CATALOG`, `CREATE TABLE`, `MODIFY`, `SELECT` em `landing`, `bronze`, `silver` — **sem** escrita manual em `gold` |
| Job de transformação Silver→Gold (identidade de execução) | Roda o MERGE automatizado | `MODIFY` restrito, só a identidade de execução, não a humana |
| Qualidade & Compliance | Investiga recall, audita rastreabilidade de lote | `SELECT` em todas as camadas (`bronze` a `gold`) + `observability` |
| Diretoria / Financeiro | Consome consolidado | `SELECT` somente em `gold` |
| Analytics/BI (Genie, AI/BI Dashboards) | Dashboards e exploração | `SELECT` em `silver` e `gold` |

Princípio: **ninguém edita a Gold manualmente**, nem quem constrói o pipeline — só o job automatizado escreve lá, protegendo a camada de consumo final de alteração acidental.

**Evidência de que isso não é executável aqui:** comando testado no SQL Editor —
```sql
GRANT SELECT ON CATALOG poc_pulse_observability TO `pulse-analytics`;
```
retornou:
```
[PRINCIPAL_DOES_NOT_EXIST] Could not find principal with name pulse-analytics.
```
Confirma que não há como criar o principal `pulse-analytics`, pois a criação de grupos exige Account Console, indisponível no Free Edition.

**Evidência complementar:** tentativa de acessar o Account Console (`accounts.azuredatabricks.net`) resultou em acesso negado após autenticação — confirmado por tentativa direta do usuário (sem mensagem de erro específica capturada em print).

### 2. Tags — mecanismo real e funcional

Diferente do RBAC, tagueamento funciona plenamente no Free Edition e foi validado.

**Convenção adotada:**

| Nível | Tag | Valor |
|---|---|---|
| Catalog | `ambiente` | `poc` |
| Catalog | `dominio` | `life-sciences` |
| Catalog | `projeto` | `pulse-health-observability` |
| Schema (cada um) | `camada` | `landing` / `bronze` / `silver` / `gold` / `observability` |

Tags de catalog são herdadas automaticamente por todos os schemas filhos — confirmado visualmente (tags `ambiente`, `dominio`, `projeto` aparecem em `bronze` e `gold` sem configuração adicional, marcadas com indicador de herança).

**Evidência:** `ALTER SCHEMA bronze SET TAGS ('camada' = 'bronze');` executado com sucesso; tag confirmada na tela de detalhes do schema no Catalog Explorer.

### 3. ABAC (Policies) — avaliado e descartado

Testada a tela de criação de policy (`Grant access`) no schema `gold`. Descoberta: **"Grant policies currently support models only"** — esse tipo de policy não se aplica a tabelas/schemas de dado, apenas a modelos de ML servidos pela plataforma. Não é limitação do Free Edition, é limitação do produto (ainda em expansão para outros tipos de objeto).

`Row filter` e `Column mask` (os outros dois tipos) se aplicariam a tabelas, mas exigem uma função de mascaramento/filtro já registrada, e nenhuma das 5 áreas de negócio documentadas em `business-context.md` tem dado sensível que justifique mascaramento. Decisão: **não implementar**, por ausência de caso de uso — não por limitação técnica.

## Consequências

- O modelo de RBAC fica documentado como especificação, não como configuração ativa — deixado explícito no repositório para não passar a impressão de governança implementada que não existe.
- Tags são o único mecanismo de governança real e demonstrável neste ambiente, usado tanto para descoberta quanto como base para relatórios de governança.
- Nenhum código de mascaramento/row-filter é escrito, evitando construir uma feature de governança atrás de tecnologia disponível sem requisito de negócio real por trás.