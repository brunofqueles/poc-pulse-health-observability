"""
Transformação genérica Bronze -> Silver.

Uma função só, guiada pela configuração declarativa
(configuracao_tabelas.py) — não há variação de comportamento entre tabelas
que justifique uma classe por tabela, mesmo raciocínio do
IngestorAutoloader (ADR-012).

Validado via spike (src/spikes/teste_merge_erp_lotes_producao): limpeza
via UDF reaproveitando limpeza_utils.py (já testado isoladamente), e
gravação idempotente via MERGE INTO por chave de negócio (ADR-002).

Categorias de limpeza suportadas na config:
- colunas_data: parse_data_suja (aceita os dois formatos + nulo variado)
- colunas_numero_inteiro / colunas_numero_float: parse_numero_sujo
- colunas_texto: limpar_texto (normaliza caixa/espaço)
- colunas_fk_nulavel: parse_nulo_variado (só normaliza nulo, sem outra limpeza)
- colunas_booleano: parse_booleano_sujo (True/nulo variado -> bool/None)
- colunas_timestamp: cast nativo do Spark (formato fixo, sem sujeira intencional)
"""

from pyspark.sql.functions import udf, col
from pyspark.sql.types import DateType, FloatType, StringType, IntegerType, BooleanType, TimestampType
from delta.tables import DeltaTable

from src.transformacao.limpeza_utils import (
    parse_data_suja,
    parse_numero_sujo,
    limpar_texto,
    parse_nulo_variado,
    parse_booleano_sujo,
)

_udf_data = udf(parse_data_suja, DateType())
_udf_numero = udf(parse_numero_sujo, FloatType())
_udf_texto = udf(limpar_texto, StringType())
_udf_fk_nulavel = udf(parse_nulo_variado, StringType())
_udf_booleano = udf(parse_booleano_sujo, BooleanType())


def transformar_bronze_para_silver(spark, catalog: str, tabela: str, config: dict) -> dict:
    """
    Lê a Bronze, aplica limpeza conforme config, grava na Silver.

    Primeira execução (Silver ainda não existe): escrita simples, cria a
    tabela. Execuções seguintes: MERGE INTO por chave de negócio,
    idempotente (ADR-002).
    """
    df_bronze = spark.table(f"{catalog}.bronze.{tabela}")

    df_silver = df_bronze
    for coluna in config.get("colunas_data", []):
        df_silver = df_silver.withColumn(coluna, _udf_data(col(coluna)))
    for coluna in config.get("colunas_numero_inteiro", []):
        df_silver = df_silver.withColumn(coluna, _udf_numero(col(coluna)).cast(IntegerType()))
    for coluna in config.get("colunas_numero_float", []):
        df_silver = df_silver.withColumn(coluna, _udf_numero(col(coluna)))
    for coluna in config.get("colunas_texto", []):
        df_silver = df_silver.withColumn(coluna, _udf_texto(col(coluna)))
    for coluna in config.get("colunas_fk_nulavel", []):
        df_silver = df_silver.withColumn(coluna, _udf_fk_nulavel(col(coluna)))
    for coluna in config.get("colunas_booleano", []):
        df_silver = df_silver.withColumn(coluna, _udf_booleano(col(coluna)))
    for coluna in config.get("colunas_timestamp", []):
        df_silver = df_silver.withColumn(coluna, col(coluna).cast(TimestampType()))

    if "data" in df_silver.columns:
        df_silver = df_silver.withColumnRenamed("data", "data_particao_ingestao")

    tabela_destino = f"{catalog}.silver.{tabela}"
    chave = config["chave_negocio"]

    if not spark.catalog.tableExists(tabela_destino):
        df_silver.write.format("delta").saveAsTable(tabela_destino)
        return {
            "tabela": tabela,
            "status": "sucesso_primeira_carga",
            "total_linhas": spark.table(tabela_destino).count(),
        }

    tabela_delta = DeltaTable.forName(spark, tabela_destino)
    (
        tabela_delta.alias("silver")
        .merge(df_silver.alias("bronze_limpo"), f"silver.{chave} = bronze_limpo.{chave}")
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )
    return {
        "tabela": tabela,
        "status": "sucesso_merge",
        "total_linhas": spark.table(tabela_destino).count(),
    }