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

---

## Lição 8 — Dois bugs descobertos só ao calcular a métrica de verdade (Gold)

**O que aconteceu (bug 1):** `gold_otif` saiu como **100%** na primeira tentativa — número bom demais para ser verdade. Investigando, `data_entrega_real` no `SimuladorTMS` era gerada como **exatamente o mesmo valor** de `data_entrega_prevista`, sem nenhuma variação — ou seja, nenhuma entrega jamais poderia atrasar, mesmo por acaso. `status_entrega` também era sorteado de forma **independente** da data, sem relação real entre os dois campos (uma remessa podia estar marcada "atrasada" no texto com data idêntica à prevista).

**Por que isso não apareceu nos testes anteriores:** todos os testes até então validavam *estrutura* (a coluna existe? o tipo está certo? o JOIN funciona?) — nunca a *plausibilidade estatística* do resultado. Um KPI de negócio calculado corretamente sobre uma regra de geração incompleta ainda "funciona" tecnicamente — só o número não significa nada.

**Correção:** `data_entrega_real` passou a variar de propósito (80% no prazo, 15% atrasada 1-3 dias, 5% devolvida), com `status_entrega` derivado da mesma decisão, não sorteado à parte.

**O que aconteceu (bug 2, efeito colateral do bug 1):** ao regenerar os dados para aplicar a correção, `tms_remessas` e `tms_comprovantes_entrega` são geradas **juntas**, na mesma chamada — e como a alocação de rota/veículo é aleatória, a regeneração produziu valores novos também em `tms_remessas` (não só na tabela que pretendíamos corrigir). O Autoloader, com checkpoint intacto para `tms_remessas`, **ignorou** o arquivo novo — a Silver de `tms_remessas` ficou com dado antigo, enquanto `tms_comprovantes_entrega` já tinha o novo. Resultado: 50,4% de "divergência" entre as duas tabelas — número sem significado real, produzido por comparar dado de execuções diferentes como se fossem da mesma.

**Correção:** resetar Bronze/checkpoint de **ambas** as tabelas relacionadas, não só da que motivou a correção original.

**Lição para o futuro (duas, uma de cada bug):** (1) validar não só a estrutura de um KPI calculado, mas se o resultado é **estatisticamente plausível** — um número "bom demais" (100%, 0%, exatamente redondo) é sinal de regra de geração incompleta, não de sorte. (2) Quando uma tabela é regenerada, **todas as tabelas geradas na mesma chamada** (não só a que motivou a mudança) precisam ser tratadas como potencialmente alteradas — reset parcial, olhando só a tabela "culpada", é a fonte mais provável do próximo bug silencioso.

---

## Lição 9 — `JOIN` interno some com linha; em tabela de observabilidade, isso é o pior tipo de erro

**O que aconteceu:** `observability_cadeia_fria` combina 4 tabelas (`tms_remessas`, `erp_notas_expedicao`, `erp_lotes_producao`, `erp_produtos`) usando `JOIN` padrão (interno). Resultado: 115 de 789 remessas (14,6%) sumiram da tabela final, sem erro, sem aviso — porque `lote_id` não resolvia contra a Silver do ERP em parte dos casos (mesma limitação de continuidade já documentada no ADR-010/011).

**Por que isso é mais grave aqui do que em outra tabela qualquer:** o propósito da tabela é *detectar violação*. Uma remessa ausente da tabela final é indistinguível de "verificada, sem problema" — quem consultasse essa tabela concluiria, incorretamente, que não havia risco naquela remessa, quando na verdade ela nunca chegou a ser checada.

**Correção:** trocado para `LEFT JOIN` a partir da tabela âncora (a que deveria cobrir 100% dos casos), com uma categoria explícita (`nao_verificavel`) para linhas que não resolvem a cadeia completa — em vez de omitir, a lacuna de cobertura vira, ela mesma, um dado consultável.

**Lição para o futuro:** `JOIN` interno é a escolha padrão do dia a dia (mais rápido, resultado mais "limpo") — mas numa tabela cujo propósito é *auditar/detectar*, ausência silenciosa de linha é o erro mais perigoso possível, porque se disfarça de "sem problema encontrado". Regra prática: sempre que uma tabela existir para responder "algo deu errado aqui?", usar `LEFT JOIN` a partir da entidade que deveria ter cobertura completa, e tornar "não verificável" uma categoria de resultado tão válida quanto "conforme" ou "violação encontrada" — nunca uma linha que simplesmente não aparece.

---

## Lição 10 — `lastProgress` esconde processamento real quando há múltiplos micro-lotes

**O que aconteceu:** ao integrar `registrar_execucao_pipeline` no `ingerir_dados`, uma tabela (`erp_lotes_producao`) apareceu como `sem_dado_novo` em `pipeline_runs`, mesmo tendo processado 54 linhas de verdade minutos antes. A dúvida inicial foi "o dado se perdeu?" — não: confirmado via `count()` direto na Bronze, as 54 linhas estavam lá. O problema era só no **relato**.

**Diagnóstico, com evidência real (não suposição):** `DESCRIBE HISTORY` na tabela Bronze revelou duas operações consecutivas com o **mesmo `queryId`**, `epochId` 1 e depois 2, um segundo de diferença — prova de que eram dois micro-lotes da **mesma execução** do `Trigger.AvailableNow`, não duas chamadas separadas. `query.lastProgress` só retorna o último micro-lote — que, nesse caso, era um lote de confirmação vazio ("não tem mais nada"), escondendo que o lote anterior, da mesma chamada, já tinha processado o arquivo de verdade.

**Correção:** trocado `query.lastProgress` (um único progresso) por `query.recentProgress` (lista de todos os micro-lotes da execução), somando `numFilesProcessed`/`numInputRows` de todos, não só do último.

**Lição para o futuro:** `Trigger.AvailableNow` não garante processar tudo num único micro-lote — pode dividir internamente. Qualquer código que leia `lastProgress` para decidir "processou algo?" está sujeito a esse falso negativo. `DESCRIBE HISTORY` (ou o equivalente `queryId`/`epochId` em `recentProgress`) é a forma correta de investigar comportamento de streaming que parece inconsistente com o que a tabela realmente contém — mais confiável que reexecutar e torcer para reproduzir.

---

## Lição 11 — Checkpoint órfão após limpeza manual, e exposição acidental de token

**O que aconteceu (parte 1 — checkpoint):** o primeiro teste real de `job_diario` via Asset Bundles falhou com `CloudFileNotFoundException`, apontando para uma partição da Landing Zone (`erp/data=2026-08-12`) que **não existia mais** — havia sido removida por um teste anterior da função `limpar_landing_zone`. O checkpoint do Autoloader, que rastreia arquivos descobertos (não só processados), ainda "sabia" desse arquivo e tentou lê-lo.

**Por que isso é diferente da Lição 7 (schema desatualizado):** lá, o problema era código de simulador corrigido gerando schema novo sobre dado antigo. Aqui, o dado em si nunca mudou de schema — foi **removido de propósito**, por uma função de manutenção legítima, mas sem coordenar com o estado do checkpoint que ainda o referenciava.

**Correção:** em vez de remendar o checkpoint específico, executado o backfill completo já planejado (ADR-010) — resolve a causa raiz (acúmulo de dado de teste inconsistente) de uma vez, não sintoma por sintoma.

**Lição para o futuro:** testar uma função de limpeza/remoção (mesmo com `dry_run` e toda a validação que já fizemos) não é uma operação isolada quando existe Autoloader com checkpoint rodando sobre os mesmos dados — remover um arquivo que um checkpoint já "viu" mas ainda não processou deixa esse checkpoint em estado inconsistente. Testes de limpeza real, em ambiente com Autoloader ativo, deveriam ser seguidos de verificação (ou reset) de checkpoint, não tratados como isolados só porque a função de limpeza em si foi bem testada.

**O que aconteceu (parte 2 — token exposto):** durante a configuração do Databricks CLI, um comando de verificação (`cat ~/.databrickscfg`) foi rodado e capturado em print para compartilhar — expondo o token de autenticação em texto puro.

**Correção:** token revogado imediatamente e substituído por um novo, com escopo granular (`bundle`, `bundle-deployments`, `jobs`, `workspace`) em vez do escopo total inicialmente sugerido.

**Lição para o futuro:** ao verificar se uma credencial foi configurada corretamente, usar sempre um comando que **confirma sem exibir** o segredo (ex.: `databricks current-user me`, que retorna dados de usuário sem nunca mostrar o token) — nunca `cat`/`print` direto num arquivo de configuração que guarda segredo em texto puro, mesmo em ambiente de baixo risco. A prática correta diante de qualquer exposição acidental, por menor que pareça, é tratar a credencial como comprometida e substituí-la — não avaliar se "alguém provavelmente não vai usar".

---

## Lição 12 — Interface muda mais rápido que roteiro fixo; confirmar a tela real antes de seguir passo a passo

**O que aconteceu:** o primeiro passo a passo para criar um painel no AI/BI Dashboard (baseado em documentação/conhecimento geral da ferramenta) assumia um fluxo de "colar SQL direto no editor do painel". A tela real mostrava uma interface diferente e mais nova — assistida por IA ("Ask the assistant to edit this chart..."), com abas separadas de "Data" (onde datasets SQL são definidos) e a página do dashboard (onde visualizações são configuradas), sem o caminho direto assumido inicialmente.

**Por que isso não é um erro no sentido dos anteriores:** não houve dado incorreto nem bug de código — foi um roteiro de instrução desatualizado em relação à interface real, corrigido assim que a tela real foi mostrada.

**Correção:** abandonado o roteiro genérico assumido; seguido o caminho real da tela (aba Data → Add SQL dataset → voltar para a página → adicionar visualização referenciando o dataset).

**Lição para o futuro:** para qualquer ferramenta de interface visual (diferente de código, que é determinístico), pedir confirmação da tela real antes de continuar um roteiro pré-planejado — interfaces desse tipo mudam com frequência maior do que documentação/conhecimento geral consegue acompanhar. Um print da tela real vale mais que um roteiro assumido, mesmo quando o roteiro parece razoável.

---

## Lição 13 — Verificar o estado real de configuração antes de levantar hipótese de falha

**O que aconteceu:** ao ver o Genie responder corretamente uma pergunta de faturamento (dado de `gold_reconciliacao_financeira`), foi levantada a hipótese de que ele tinha acessado uma tabela fora do escopo configurado — baseada na lembrança de que só as 5 tabelas de `observability` teriam sido conectadas. A lembrança estava errada: as 3 tabelas Gold também haviam sido conectadas, na mesma etapa inicial de configuração, só não registrado corretamente na documentação no momento.

**Por que isso quase virou uma conclusão errada, documentada como fato:** a hipótese foi reforçada por uma busca que trouxe uma fonte real (blog de terceiros) descrevendo um comportamento plausível e tecnicamente coerente ("Genie pode alcançar tabelas fora do Space via edição manual de query") — fácil de aceitar como confirmação, porque parecia se encaixar perfeitamente no caso observado.

**Correção:** antes de documentar a hipótese como conclusão, foi pedida confirmação direta da lista real de tabelas conectadas (não memória da conversa) e um teste específico desenhado para diferenciar as duas hipóteses (pergunta sobre `crm_clientes`, tabela genuinamente fora do escopo) — o resultado confirmou que o escopo era respeitado, refutando a hipótese antes de ela virar documentação permanente e incorreta.

**Lição para o futuro:** quando uma observação parece confirmar uma hipótese plausível e apoiada por fonte externa, ainda vale desenhar um teste que **poderia refutar** a hipótese antes de aceitá-la — especialmente antes de registrar algo como fato em documentação. Memória de configuração feita em mensagens anteriores da conversa não substitui verificação do estado atual real, principalmente quando a config foi feita por cliques na interface (não código versionado, que ficaria explícito no diff de um commit).

---

## Lição 14 — Duas particularidades do Web Terminal para rodar pytest

**O que aconteceu (parte 1):** `pip install pytest` completou com sucesso (confirmado via `pip show pytest`), mas o comando `pytest` retornou "command not found" no terminal.

**Causa:** o executável instalado não está no `PATH` do Web Terminal, mesmo o pacote Python existindo corretamente.
**Correção:** chamar via `python -m pytest`, que sempre funciona quando o pacote está instalado, independente do `PATH` do executável.

**O que aconteceu (parte 2):** com `python -m pytest tests/ -v`, apareceu `OSError: [Errno 95] Operation not supported` ao tentar criar `tests/__pycache__`.

**Causa:** `/Workspace` é um sistema de arquivos virtual do Databricks, não um disco comum — não suporta todas as operações de sistema de arquivos que o pytest tenta usar por padrão (cache de bytecode compilado).
**Correção:** `PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/ -v` — desabilita a escrita de cache, sem afetar a execução dos testes em si.

**Lição para o futuro:** ferramentas de linha de comando padrão do ecossistema Python (pytest, mas potencialmente outras) podem ter comportamento diferente rodando dentro do Web Terminal do Databricks, por causa do sistema de arquivos `/Workspace` não ser um disco POSIX completo. Ao rodar qualquer ferramenta nova nesse terminal pela primeira vez, tratar erros de I/O (`OSError`, permissão, `command not found`) como possivelmente específicos do ambiente, não do código — a mesma cautela já aplicada a Autoloader, Asset Bundles e Secret Scopes.

---

## Lição 15 — Dado existir não é o mesmo que dado ter prova de execução

**O que aconteceu:** ao testar `fechar_mes.ipynb` (que valida completude consultando `pipeline_runs` antes de aceitar um fechamento) contra julho — mês que sabíamos, com certeza, estar completo — a validação retornou `fechamento_valido = false`, com todos os 23 dias úteis "faltando".

**Causa raiz:** `backfill_completo.ipynb` gerou o dado real de julho chamando `SimuladorFactory` diretamente, num loop manual, sem nunca passar pelo orquestrador oficial (`gerar_dados.ipynb`) — o único ponto do código que registra em `pipeline_runs`. O dado existia de verdade, validado matematicamente em fases anteriores; a prova de execução registrada, não.

**Por que isso não foi um bug de `fechar_mes`, e sim uma descoberta válida:** o comportamento era exatamente o desenhado — não confiar apenas na existência do dado, exigir prova de execução. A "falha" no teste era, na verdade, o mecanismo de validação funcionando corretamente e expondo uma lacuna real de rastreabilidade que já existia, silenciosa, desde o backfill.

**Correção:** reconstrução retroativa de `pipeline_runs` (240 registros), baseada em evidência já conhecida (log de execução do backfill original + checagem de calendário), marcada explicitamente como `reconstrucao_retroativa: True` — nunca disfarçada de execução em tempo real.

**Lição para o futuro:** qualquer atalho de desenvolvimento que gere dado "por fora" do caminho oficial (chamar a lógica de negócio diretamente, pulando o orquestrador que também registra auditoria) cria uma lacuna que só aparece quando algo depende dessa auditoria — nesse caso, meses depois, ao construir uma validação de completude. Ao criar um script de backfill/atalho, perguntar explicitamente: "o que esse atalho **não está fazendo** que o caminho oficial faz?" — não só "o dado final está certo?".

---

## Lição 16 — Checkpoint do Autoloader trava no caminho de origem original

**O que aconteceu:** ao separar Distribution do ERP (5º pipeline) e apontar a fonte de `erp_posicoes_estoque`/`erp_notas_expedicao` para a nova pasta `distribution/`, a ingestão falhou com `INVALID_PARAMETER_VALUE.LOCATION_OVERLAP`.

**Causa raiz:** o checkpoint dessas tabelas — nomeado só pela tabela, não pelo sistema de origem — ainda continha referência ao caminho antigo (`erp/data=.../`). O Unity Catalog recusou a troca de "endereço de origem" para uma fonte de streaming que ele já conhecia associada a outro caminho.

**Correção:** reset pontual de Bronze/checkpoint/schema só das 2 tabelas afetadas (não da Silver — `MERGE` por chave permaneceu íntegro).

**Lição para o futuro:** mover a origem física de uma tabela na Landing Zone (trocar de pasta/sistema) exige reset de checkpoint do Autoloader como parte do plano, não como surpresa descoberta ao testar — o checkpoint é amarrado ao caminho de origem desde a primeira execução, não só ao nome da tabela de destino.

---

## Lição 17 — Falha de infraestrutura não é falha de dado; `DESCRIBE HISTORY` confirma o que realmente aconteceu

**O que aconteceu:** durante um teste de ingestão, a célula travou por mais de 10 minutos e depois retornou `StatusRuntimeException: UNAVAILABLE` — perda de conexão gRPC entre o notebook e o compute serverless.

**Por que isso não gerou pânico nem retrabalho desnecessário:** em vez de assumir que o dado não foi escrito (e tentar reprocessar, arriscando duplicação), `DESCRIBE HISTORY` na tabela Bronze confirmou que a escrita já havia sido concluída com sucesso *antes* da queda de conexão — o dado nunca esteve em risco, só a confirmação visual na tela não chegou a aparecer.

**Lição para o futuro:** quando uma célula falha por erro de infraestrutura (timeout, perda de conexão, "internal error" recomendando reiniciar compute), o primeiro passo não é reprocessar — é **verificar o estado real** via `DESCRIBE HISTORY` ou consulta direta à tabela. Mesmo princípio já estabelecido na Lição 10 (confiar no histórico real da tabela, não no estado aparente da célula/tela) — reaplicado aqui com sucesso, evitando um reprocessamento desnecessário que poderia ter introduzido risco de duplicação sem necessidade real.