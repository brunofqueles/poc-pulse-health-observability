"""
Notificadores — canal plugável para alertas da plataforma (ADR-007).

NotificadorBase define o contrato; cada subclasse implementa um canal
diferente. NotificadorTabela é o fallback garantido — nunca falha, é só
um INSERT em observability.alertas. NotificadorEmail envia via Gmail SMTP,
usando uma conta dedicada de portfólio (não a conta pessoal do autor) —
credencial guardada em Databricks Secret Scope, nunca em texto no código.

Referências: ADR-003 (OOP — contrato compartilhado com variação real de
implementação), ADR-007 (desenho original dos alertas, com o adendo de
implementação real do NotificadorEmail).
"""

from abc import ABC, abstractmethod
from datetime import datetime
import json
import uuid
import smtplib
from email.mime.text import MIMEText

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


class NotificadorEmail(NotificadorBase):
    """
    Envia o alerta por email, via Gmail SMTP. Usa uma conta dedicada de
    portfólio (bruno.queles.dataeng@gmail.com), não a conta pessoal do
    autor — credencial (senha de aplicativo) guardada em Databricks Secret
    Scope (pulse-secrets/gmail-app-password), nunca em texto no código.

    Nunca deixa exceção subir — captura qualquer falha de rede/autenticação
    e retorna False, para não derrubar o restante do fluxo de alerta (ex.:
    NotificadorTabela já ter registrado com sucesso).
    """

    def __init__(self, dbutils, remetente: str = "bruno.queles.dataeng@gmail.com", destinatarios: list = None):
        self.dbutils = dbutils
        self.remetente = remetente
        self.destinatarios = destinatarios or [remetente]

    def notificar(self, alerta: dict) -> bool:
        try:
            senha = self.dbutils.secrets.get(scope="pulse-secrets", key="gmail-app-password")

            corpo_texto = (
                f"{alerta['mensagem']}\n\n"
                f"Tipo de evento: {alerta['tipo_evento']}\n"
                f"Origem: {alerta['origem']}\n"
                f"Severidade: {alerta['severidade']}\n\n"
                f"Detalhes: {json.dumps(alerta.get('detalhes', {}), default=str, ensure_ascii=False, indent=2)}"
            )

            mensagem = MIMEText(corpo_texto)
            mensagem["Subject"] = f"[Pulse Health Platform] Alerta {alerta['severidade']}: {alerta['tipo_evento']}"
            mensagem["From"] = self.remetente
            mensagem["To"] = ", ".join(self.destinatarios)

            with smtplib.SMTP("smtp.gmail.com", 587) as servidor:
                servidor.starttls()
                servidor.login(self.remetente, senha)
                servidor.sendmail(self.remetente, self.destinatarios, mensagem.as_string())

            return True
        except Exception:
            return False