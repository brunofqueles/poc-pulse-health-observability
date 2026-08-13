"""
Registro de execução — grava o resultado de cada rodada de pipeline em
observability.pipeline_runs, transformando o que hoje só aparece impresso
na tela em histórico consultável.

Append-only (não MERGE) — cada execução é um evento novo, não algo que se
atualiza. Usado pelos 4 orquestradores (gerar_dados, ingerir_dados,
promover_seeds, construir_gold).
"""

import json
import uuid
from datetime import datetime

from pyspark.sql import Row
from pyspark.sql.types import StructType, StructField, StringType

_SCHEMA = StructType([
    StructField("execucao_id", StringType(), False),
    StructField("pipeline", StringType(), False),
    StructField("item", StringType(), False),
    StructField("status", StringType(), False),
    StructField("detalhes", StringType(), True),
    StructField("data_referencia", StringType(), True),
    StructField("timestamp_execucao", StringType(), False),
])


def registrar_execucao_pipeline(
    spark,
    pipeline: str,
    item: str,
    status: str,
    detalhes: dict,
    data_referencia=None,
    catalog: str = "poc_pulse_observability",
) -> None:
    """
    Grava uma linha de log de execução em observability.pipeline_runs.

    pipeline: nome do orquestrador (gerar_dados, ingerir_dados, promover_seeds, construir_gold)
    item: sistema ou tabela específica
    status: status retornado pela função/método que executou
    detalhes: dicionário de resultado inteiro, serializado como JSON
    data_referencia: aplica-se só a gerar_dados; None para os demais

    Schema definido explicitamente (não inferido) — com data_referencia
    frequentemente None, uma linha única sem schema explícito falha com
    CANNOT_DETERMINE_TYPE (Spark não consegue inferir tipo de coluna só-nula).
    """
    linha = Row(
        execucao_id=str(uuid.uuid4()),
        pipeline=pipeline,
        item=item,
        status=status,
        detalhes=json.dumps(detalhes, default=str, ensure_ascii=False),
        data_referencia=str(data_referencia) if data_referencia else None,
        timestamp_execucao=datetime.now().isoformat(),
    )

    df_linha = spark.createDataFrame([linha], schema=_SCHEMA)
    df_linha.write.format("delta").mode("append").saveAsTable(f"{catalog}.observability.pipeline_runs")