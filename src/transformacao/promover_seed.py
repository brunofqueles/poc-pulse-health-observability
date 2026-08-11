"""
Promoção genérica de seeds — Landing Zone -> Bronze -> Silver.

Uma função só, guiada por configuração declarativa (configuracao_seeds.py),
mesmo raciocínio do ADR-013 (transformação das 11 tabelas de evento) e do
ADR-012 (IngestorAutoloader). Diferente delas, seed não usa Autoloader
(não é incremental, é recarregado por completo) nem UDFs de limpeza (sem
sujeira intencional) — só cast de tipo direto.
"""

from pyspark.sql.functions import col
from pyspark.sql.types import BooleanType, IntegerType, FloatType


def promover_seed(
    spark,
    tabela: str,
    config: dict,
    catalog: str = "poc_pulse_observability",
    volume_landing: str = "raw",
) -> dict:
    """Lê o seed da Landing Zone, grava Bronze (string) e Silver (tipado), ambos por overwrite."""
    sistema = config["sistema"]
    caminho = f"/Volumes/{catalog}/landing/{volume_landing}/{sistema}/_seed/{tabela}.json"

    df_bronze = spark.read.json(caminho)
    df_bronze = df_bronze.select([col(c).cast("string").alias(c) for c in df_bronze.columns])
    df_bronze.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.bronze.{tabela}")

    df_silver = df_bronze
    for coluna in config.get("colunas_boolean", []):
        df_silver = df_silver.withColumn(coluna, col(coluna).cast(BooleanType()))
    for coluna in config.get("colunas_integer", []):
        df_silver = df_silver.withColumn(coluna, col(coluna).cast(IntegerType()))
    for coluna in config.get("colunas_float", []):
        df_silver = df_silver.withColumn(coluna, col(coluna).cast(FloatType()))

    df_silver.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.silver.{tabela}")

    return {"tabela": tabela, "status": "sucesso", "total_linhas": df_silver.count()}