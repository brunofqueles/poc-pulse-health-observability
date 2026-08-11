# ADR-013 — Transformação Bronze → Silver: função genérica config-driven

**Status:** Aceito

## Contexto

Com as 11 tabelas Bronze existindo (ADR-012), era preciso decidir como estruturar a limpeza e tipagem para a Silver — 11 tabelas, cada uma com um schema de colunas diferente precisando de limpeza diferente, mas nenhuma com lógica de negócio distinta o suficiente para justificar código próprio por tabela.

## Decisão

Uma função única (`transformar_bronze_para_silver`), guiada por **configuração declarativa** (`configuracao_tabelas.py`) — mesmo raciocínio do `IngestorAutoloader` (ADR-012): a variação entre tabelas é de *dados de configuração*, não de *comportamento*.

```python
CONFIGURACAO_TABELAS = {
    "erp_lotes_producao": {
        "chave_negocio": "lote_id",
        "colunas_data": ["data_fabricacao", "data_validade", "data_liberacao"],
        "colunas_numero_inteiro": ["quantidade_produzida"],
        "colunas_texto": ["centro_producao_id", "status_qc"],
    },
    # ... as outras 10
}
```

Seis categorias de limpeza suportadas, cada uma mapeada para uma função pura de `limpeza_utils.py` (espelho de `sujeira_intencional.py`, ADR-001):

| Categoria | Função | Uso |
|---|---|---|
| `colunas_data` | `parse_data_suja` | Dois formatos de data + nulo variado |
| `colunas_numero_inteiro` / `colunas_numero_float` | `parse_numero_sujo` | Padrão brasileiro, com cast final diferente |
| `colunas_texto` | `limpar_texto` | Caixa/espaço inconsistente |
| `colunas_fk_nulavel` | `parse_nulo_variado` | FK opcional, só normaliza nulo (ex.: `lote_id` em `crm_atendimento`) |
| `colunas_booleano` | `parse_booleano_sujo` | Campo que mistura booleano com nulo variado (ex.: `pod_confirmado`, Lição 5) |
| `colunas_timestamp` | Cast nativo do Spark | Formato fixo, sem sujeira intencional (`timestamp_leitura`) |

Limpeza aplicada via UDF (não expressão Spark SQL nativa) — garante que a lógica testada isoladamente (`limpeza_utils.py`) seja literalmente a que roda em produção, não uma reimplementação paralela em SQL com risco de divergência. Custo de performance do UDF aceito conscientemente, irrelevante no volume de uma POC.

Gravação: escrita simples na primeira execução (Silver ainda não existe); `MERGE INTO` por `chave_negocio` nas execuções seguintes (ADR-002).

## Alternativas consideradas

- **Uma função de transformação por tabela**: descartada — 11 funções quase-idênticas, divergindo só na lista de colunas, é exatamente o tipo de duplicação que a configuração declarativa evita.
- **Expressão SQL nativa em vez de UDF**: mais performática, mas duplicaria a lógica de limpeza em dois lugares (Python testado + SQL não testado), com risco real de os dois divergirem ao longo do tempo. Descartada para o volume desta POC.

## Consequências

- Adicionar limpeza a uma tabela nova é editar a configuração, não escrever código novo — mesmo ganho de manutenção já obtido com `IngestorAutoloader`.
- A configuração é, na prática, a tradução em código da coluna "Tipo lógico Silver" de `docs/schemas/*.md` — os dois precisam ser mantidos sincronizados manualmente (não há geração automática de um a partir do outro nesta fase).
- Validado em escala completa: as 11 tabelas passam por primeira carga e depois `MERGE`, com totais idênticos nas duas execuções — idempotência confirmada, não só suposta.