# ADR-003 — Programação Orientada a Objetos

**Status:** Aceito

## Contexto

Um dos objetivos de aprendizado explícitos do projeto é consolidar Programação Orientada a Objetos. Ao mesmo tempo, é preciso evitar o antipadrão oposto: aplicar OOP indiscriminadamente a toda linha de código, incluindo lógica de transformação simples que não se beneficia de abstração — o que aumentaria complexidade sem ganho real.

O critério adotado: **OOP se aplica onde existe um contrato de comportamento comum, implementado de formas diferentes** — não a transformações lineares de dado que não se repetem com variação.

## Decisão

Aplicar OOP em três pontos específicos do projeto, cada um com uma classe base (ou abstrata) e subclasses concretas:

### 1. Geração de dados sintéticos

```
SimuladorDeSistema (classe base)
  └─ gerar_dia(data_referencia) → grava JSON na Landing Zone (ADR-001)
       ├─ SimuladorERP
       ├─ SimuladorCRM
       ├─ SimuladorTMS
       └─ SimuladorFinanceiro
```
Cada subclasse define seu próprio schema `dbldatagen` e quais campos usam `Faker`, mas compartilha o mesmo contrato (`gerar_dia`). Escalar de 4 para 5/6/7 pipelines significa criar uma subclasse nova, não duplicar um script inteiro.

### 2. Verificação de qualidade

```
VerificadorDeQualidade (classe)
  └─ verificar(df, regras) → retorna violações encontradas
```
Reutilizada por qualquer pipeline que precise checar as regras definidas em `business-context.md` (ex.: estoque negativo, temperatura fora da faixa) — a regra muda, a mecânica de verificação não.

### 3. Notificação de alertas (ver ADR-007)

```
NotificadorBase (classe abstrata)
  ├─ NotificadorEmail
  ├─ NotificadorWebhook
  └─ NotificadorTabela
```
Canal plugável — trocar o meio de notificação é trocar a subclasse, não reescrever a lógica de disparo.

### Onde OOP **não** é aplicado

A lógica de transformação Bronze→Silver→Gold de cada pipeline permanece como funções PySpark simples, parametrizadas por Widgets (ADR-008) — não há variação de comportamento por sistema que justifique uma hierarquia de classes ali; é a mesma sequência de operações (limpar, tipar, aplicar MERGE), variando apenas os parâmetros de entrada.

## Alternativas consideradas

- **OOP em todo o código, incluindo transformações**: descartada — adicionaria abstração a lógica que já é simples e linear, dificultando leitura sem ganho de reuso real.
- **Nenhuma classe, tudo em funções e dicionários de configuração**: descartada — perde o benefício de contrato compartilhado explícito (`gerar_dia`, `verificar`) que facilita adicionar o 5º/6º/7º sistema sem duplicar estrutura.

## Consequências

- `src/` organiza-se por responsabilidade, não por pipeline: `src/simuladores/`, `src/qualidade/`, `src/notificadores/`, além de `src/transformacao/` (funções, não classes) e `src/spikes/` (já existente).
- Testes automatizados (pytest) podem testar cada classe isoladamente (ex.: `SimuladorERP` gera o schema esperado, `VerificadorDeQualidade` detecta a violação correta), sem precisar de um pipeline completo rodando.
- Adicionar o 5º pipeline (fase de escala) é, concretamente, criar uma nova subclasse de `SimuladorDeSistema` — teste direto de que o desenho é extensível, não só promessa.