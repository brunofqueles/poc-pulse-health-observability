# Lições aprendidas

> Registro de problemas reais encontrados durante a construção do projeto — diagnóstico, causa raiz e correção. Diferente de um ADR (que documenta uma escolha entre alternativas), este documento registra descobertas de troubleshooting: coisas que só se aprende errando.

---

## Lição 1 — Caractere invisível no nome do catalog quebrou tudo silenciosamente

**O que aconteceu:** ao tentar gravar dados de verdade na Landing Zone (`executar_seed()` do `SimuladorERP`), toda tentativa de acessar o catalog `poc_pulse_observability` falhava com `[NO_SUCH_CATALOG_EXCEPTION]` — mesmo o catalog existindo, visível no Catalog Explorer, com o nome aparentemente correto.

**Diagnóstico:** comandos isolados (`dbutils.fs.ls`, `SHOW CATALOGS`) confirmaram que o problema não estava no código da classe — o catalog realmente não era encontrado por esse nome. A pista decisiva veio ao inspecionar os nomes com `repr()` em vez de `print()` direto:
```python
catalogs = [row.catalog for row in spark.sql("SHOW CATALOGS").collect()]
for c in catalogs:
    print(repr(c))
```
Resultado: `'poc_pulse_observability\xa0'` — um caractere de espaço não separável (`\xa0`, non-breaking space) grudado no final do nome, invisível em qualquer exibição normal da UI.

**Causa raiz:** o nome do catalog provavelmente foi digitado ou colado com esse caractere incluído no momento da criação — um espaço comum e um `\xa0` são visualmente idênticos, mas tecnicamente strings diferentes.

**Correção:** a documentação oficial da Databricks afirma que catalog não pode ser renomeado via SQL ("para renomear, crie um catalog novo e mova os objetos"). Na prática, a opção **Rename** do Catalog Explorer (UI) funcionou — renomeando com o nome digitado manualmente (sem colar), o problema foi resolvido sem precisar recriar catalog, schemas ou o Volume.

**Lição para o futuro:** ao criar qualquer objeto nomeado no Databricks (catalog, schema, tabela), **digitar o nome diretamente no campo**, nunca colar de outra origem (chat, documento, outra aba) — cópia e cola é o vetor mais provável de caractere invisível. Se um objeto "existe visualmente" mas não é encontrado por nome, `repr()` do nome real é o diagnóstico mais rápido, antes de suspeitar do código.

---

## Lição 2 — `%run` polui a saída; `import` de arquivo puro exige `dbutils` explícito

**O que aconteceu:** os simuladores foram inicialmente criados como Notebooks (`simulador_base`, `simulador_erp`) compartilhando código via `%run ./simulador_base`. Funcionava, mas cada notebook que desse `%run` no outro exibia a saída completa das células de markdown do notebook de origem — ruído crescente conforme mais simuladores fossem adicionados (4 sistemas, cada um repetindo a mesma explicação).

**Diagnóstico:** `%run` executa o notebook inteiro no contexto do notebook atual, incluindo a exibição de saída de todas as células — diferente de um `import` Python normal, que só expõe o que é explicitamente referenciado, sem exibir nada.

**Correção:** os simuladores foram convertidos de Notebook para arquivo `.py` puro (sem células de markdown), documentados via docstring nos próprios métodos/classes em vez de texto solto. Databricks Repos adiciona automaticamente a raiz do repositório ao `sys.path`, permitindo `import` normal entre arquivos.

**Efeito colateral descoberto em seguida:** `dbutils`, disponível automaticamente dentro de um notebook, **não** é injetado automaticamente em um arquivo `.py` importado — gerando `NameError: name 'dbutils' is not defined` na primeira tentativa de gravação real. Corrigido recebendo `dbutils` explicitamente no construtor da classe, no mesmo padrão já usado para `spark`.

**Lição para o futuro:** notebooks com célula de markdown são adequados para código **narrativo** (lido diretamente por uma pessoa, ex.: o notebook que vai orquestrar a geração diária). Código feito para ser **reutilizado por outros arquivos** (classes, funções compartilhadas) deve nascer como `.py` puro desde o início, evitando essa migração no meio do caminho. Qualquer classe/função nesse formato que precise de `spark` ou `dbutils` deve recebê-los explicitamente — nunca assumir que estarão disponíveis implicitamente.

---

## Lição 3 — Duas particularidades do `dbldatagen` que geram bug silencioso, não erro

**O que aconteceu:** ao testar `dbldatagen.DataGenerator` isoladamente antes de usar nos simuladores, dois comportamentos saíram diferentes do esperado, nenhum dos dois com erro explícito — os dois exigiram inspecionar o resultado com atenção para perceber.

**Problema 1 — coluna de seed duplicada:** todo `DataGenerator` cria automaticamente uma coluna de controle interna chamada `id`. Se o schema definido também tiver uma coluna própria chamada `id`, o resultado final tem **duas colunas `id`** — sem erro, sem aviso forte (só um `WARNING` fácil de não notar), e qualquer gravação subsequente (ex.: JSON) perde uma das duas silenciosamente.
**Correção:** usar `seedColumnName="_seed_id"` (ou outro nome que não colida) na criação do `DataGenerator`.

**Problema 2 — coluna renomeada some do resultado:** ao renomear a coluna de seed via `seedColumnName`, ela deixa de aparecer no `.build()` final — diferente do esperado (que ela continuasse presente, só renomeada). Tentar acessar essa coluna depois (`row['_seed_id']`) gera `PySparkValueError`.
**Correção:** não depender da coluna de seed do `dbldatagen` para numeração/chave — gerar sequência via `enumerate()` em Python puro sobre o resultado de `.collect()`, com controle total.

**Problema 3 (relacionado) — valores sequenciais em vez de aleatórios:** colunas numéricas (`minValue`/`maxValue`) sem o parâmetro `random=True` explícito saem em sequência crescente (10, 11, 12, 13...), não aleatórias — fácil de não perceber em uma amostra pequena.
**Correção:** sempre incluir `random=True` em coluna numérica que deveria variar de forma realista.

**Lição para o futuro:** ao adotar uma biblioteca de terceiros para geração de dado, testar isoladamente com uma amostra pequena e **inspecionar o schema resultante junto com os valores** (não só rodar sem erro) — comportamento de biblioteca externa não documentado com clareza total deve ser tratado como incerto até verificado na prática, mesmo quando a chamada "funciona".

---

## Lição 4 — `date` não é `datetime`, e isso quebra de duas formas diferentes

**O que aconteceu:** ao implementar `SimuladorTMS`, duas linhas de código trataram um objeto `date` como se fosse `datetime`, causando um erro explícito e um bug silencioso.

**Problema 1 — `AttributeError`:** código chamou `.date()` sobre um valor que já era `date` (resultado de `date + timedelta`). `.date()` é método de `datetime` (extrai só a parte de data de um timestamp completo) — `date` não tem esse método, porque já *é* só a parte de data.
**Correção:** remover a chamada `.date()` quando o valor de origem já é `date`.

**Problema 2 — bug silencioso, sem erro nenhum:** `date + timedelta(hours=8)` não avança nenhum dia, porque a aritmética de `date` só considera o componente `.days` do `timedelta` — horas menores que 24 são descartadas silenciosamente. Uma rota de 8h, 16h ou 18h de trânsito resultaria em "entrega no mesmo dia da expedição", sem erro nenhum acusando isso.
**Correção:** converter horas em dias completos antes de somar, arredondando para cima (`-(-horas // 24)`), já que qualquer trânsito, mesmo curto, geralmente significa "próximo dia útil" em um cenário de granularidade diária.

**Lição para o futuro:** ao misturar `date` (granularidade de dia) com durações em horas/minutos, converter explicitamente para a granularidade certa **antes** da operação — nunca confiar que a aritmética "vai fazer o que parece óbvio". Isso é ainda mais perigoso quando não gera erro (Problema 2) do que quando gera (Problema 1): o primeiro se descobre rodando; o segundo só se descobre inspecionando o resultado com atenção.

---

## Lição 5 — campo com tipo misto (booleano + string) vira string ao voltar do JSON, e o booleano some

**O que aconteceu:** `pod_confirmado` (TMS) grava `True` (booleano Python) quando confirmado, ou uma das variações de `valor_nulo_variado()` (`None`, `""`, `"N/A"`, `"NULL"`) quando não. Ao ler esse campo de volta via `spark.read.json()`, o filtro `linha.pod_confirmado is True` nunca encontrava nenhuma linha — mesmo havendo, de fato, entregas confirmadas gravadas.

**Diagnóstico:** `groupBy("pod_confirmado").count()` revelou que o Spark inferiu a coluna inteira como **string** (porque o campo mistura tipos diferentes entre registros) — o booleano `True` virou o texto `"true"` (minúsculo), não o booleano Python `True`. `linha.pod_confirmado is True` comparava com o objeto errado.

**Correção:** comparar como string (`str(valor).lower() == "true"`), reforçando a própria regra que o projeto já havia estabelecido — Bronze é 100% string, sem exceção — mesmo quando o código-fonte usa um tipo nativo do Python antes de serializar.

**Lição para o futuro:** um campo que mistura booleano com representações de nulo no mesmo registro é convertido para string pelo motor ao ser lido de volta de um formato semi-estruturado (JSON) — nunca assumir que um `True` do Python sobrevive como booleano depois de ir e voltar por um arquivo. Ler o schema inferido (`df.printSchema()` ou `df.dtypes`) antes de escrever qualquer filtro sobre um campo assim evita esse erro por completo.

---

## Lição 6 — `lastProgress` nunca é `None` com `Trigger.AvailableNow`, e isso já era conhecido

**O que aconteceu:** `IngestorAutoloader.executar()` classificava o status como `"sucesso"` mesmo quando zero arquivos novos foram processados — porque a lógica original checava `if progresso is None` para decidir se não havia dado novo, mas `query.lastProgress` **sempre** retorna um objeto preenchido com `Trigger.AvailableNow`, mesmo sem nenhum arquivo para processar. A checagem certa precisa olhar `numFilesProcessed`, não a presença de `lastProgress`.

**O que torna esta lição diferente das anteriores:** esse comportamento específico do Autoloader já estava registrado como conhecimento do projeto anterior (`poc-lakehouse-food-latam`), **antes** deste projeto sequer começar. Reencontramos o mesmo bug do zero, gastando um ciclo de debug evitável, porque não consultamos as lições já documentadas antes de escrever o código pela primeira vez.

**Lição para o futuro (a mais importante desta lista):** antes de implementar algo que já foi construído em um projeto anterior — mesmo que o código em si não seja reaproveitado — **consultar as lições aprendidas documentadas primeiro**. Elas existem exatamente para evitar redescobrir o mesmo problema da forma mais cara (debugando em produção de código novo) em vez da mais barata (lendo um parágrafo antes de escrever a primeira linha).

---

## Lição 7 — Corrigir o simulador não corrige o dado que ele já gerou

**O que aconteceu:** ao adicionar uma coluna de chave nova em 3 simuladores (`posicao_id`, `item_pedido_id`, `leitura_id`), testamos gerando **dado novo** e confirmando que a coluna aparecia — mas as tabelas Bronze e Silver dessas 3 tabelas já existiam, criadas antes da correção, a partir de arquivos antigos sem a coluna nova. Ao rodar a transformação em escala (11 tabelas), o `MERGE INTO` falhou com erro de coluna inexistente — a Silver tinha herdado o schema antigo da Bronze, que nunca foi atualizado.

**Por que isso não apareceu antes:** os testes anteriores sempre validavam a peça nova isoladamente (gerar 1 dia, conferir o conteúdo) — nunca testamos o ciclo completo (gerar → ingerir → transformar) **depois** de uma correção de schema num simulador. O problema só existe na interseção entre "código corrigido" e "dado antigo, gerado pelo código anterior à correção".

**Correção:** como o projeto ainda está em fase de desenvolvimento (dado descartável, ADR-010), o caminho foi reset completo — não só das 3 tabelas afetadas, mas de **todas as 11**, porque os simuladores geram os 4 sistemas juntos numa cadeia com dependência real (ADR-011): regenerar só as 3 quebraria a integridade referencial com as outras 8 que dependiam do mesmo lote de geração. Reset de Bronze + Silver + checkpoint + schema do Autoloader, seguido de backfill das datas já testadas via `SimuladorFactory`.

**Lição para o futuro:** corrigir um simulador que já gerou dado em produção (ou em qualquer tabela persistida) não é uma operação isolada — o dado já existente fica **silenciosamente desatualizado** em relação ao código novo, sem erro nenhum até algo tentar usar a coluna que não existe. Duas opções reais para lidar com isso quando acontecer: (1) em fase de desenvolvimento, aceitar o dado como descartável e resetar, como fizemos aqui; (2) em produção real, seria necessário schema evolution explícito (`ALTER TABLE ADD COLUMN`, com a coluna nova vindo `NULL` para o histórico) — opção mais cara de implementar corretamente, mas necessária quando o dado não pode ser descartado. Antes de corrigir um simulador que já gerou dado, perguntar explicitamente: "essa mudança de schema precisa de uma estratégia de migração, ou dá para descartar o que já existe?"