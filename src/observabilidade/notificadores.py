"""
Notificadores — canal plugável para alertas da plataforma (ADR-007).

NotificadorBase define o contrato; cada subclasse implementa um canal
diferente. NotificadorTabela é o fallback garantido — nunca falha, é só
um INSERT em observability.alertas — usado como canal principal nesta
fase, junto com Job Notifications (nativo, configurado no job_diario.yml)
para o eixo de execução.

NotificadorEmail (terceiro canal, via SMTP) foi desenhado mas não
implementado — exigiria senha de aplicativo, que requer verificação em
duas etapas ativada na conta pessoal do autor, decisão que ele optou por
não tomar apenas para viabilizar este teste de portfólio. O contrato
(NotificadorBase) já está provado com 2 implementações reais, cobrindo
o propósito de "canal plugável" sem depender do terceiro.

Referências: ADR-003 (OOP — contrato compartilhado com variação real de
implementação, exemplo mais puro do critério até aqui), ADR-007 (desenho
original dos alertas, com o adendo de escopo final).
"""

from abc import ABC, abstractmethod
from datetime import datetime
import json
import uuid

from pyspark.sql import Row
from pyspark.sql.types import StructType, StructField, StringType


class NotificadorBase(ABC):
    """Contrato comum: notificar() recebe um alerta e devolve se foi bem-sucedido."""

    @abstractmethod
    def notificar(self, alerta: dict) -> bool:
        """
        Envia/registra o alerta.

        alerta espera as chaves: tipo_evento, origem, severidade, mensagem,
        detalhes (dict, será serializado).
        """
        ...


class NotificadorTabela(NotificadorBase):
    """
    Fallback garantido — grava o alerta em observability.alertas.
    Nunca falha por motivo de rede (é só escrita em tabela Delta), diferente
    de um canal externo como email.
    """

    _SCHEMA = StructType([
        StructField("alerta_id", StringType(), False),
        StructField("tipo_evento", StringType(), False),
        StructField("origem", StringType(), False),
        StructField("severidade", StringType(), False),
        StructField("mensagem", StringType(), False),
        StructField("detalhes", StringType(), True),
        StructField("timestamp_alerta", StringType(), False),
    ])

    def __init__(self, spark, catalog: str = "poc_pulse_observability"):
        self.spark = spark
        self.catalog = catalog

    def notificar(self, alerta: dict) -> bool:
        linha = Row(
            alerta_id=str(uuid.uuid4()),
            tipo_evento=alerta["tipo_evento"],
            origem=alerta["origem"],
            severidade=alerta["severidade"],
            mensagem=alerta["mensagem"],
            detalhes=json.dumps(alerta.get("detalhes", {}), default=str, ensure_ascii=False),
            timestamp_alerta=datetime.now().isoformat(),
        )

        df_linha = self.spark.createDataFrame([linha], schema=self._SCHEMA)
        df_linha.write.format("delta").mode("append").saveAsTable(f"{self.catalog}.observability.alertas")
        return True