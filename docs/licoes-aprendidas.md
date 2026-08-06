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