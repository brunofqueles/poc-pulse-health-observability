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
from email.mime.multipart import MIMEMultipart

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

    Email enviado como multipart/alternative: versão HTML formatada
    (cabeçalho colorido por severidade, campos em tabela, listas como
    <ul> em vez de array JSON cru) + versão texto puro como fallback,
    para clientes de email que não renderizam HTML.

    Nunca deixa exceção subir — captura qualquer falha de rede/autenticação
    e retorna False, para não derrubar o restante do fluxo de alerta (ex.:
    NotificadorTabela já ter registrado com sucesso).
    """

    _CORES_SEVERIDADE = {"alta": "#c0392b", "media": "#e67e22", "baixa": "#2c3e50"}

    def __init__(self, dbutils, remetente: str = "bruno.queles.dataeng@gmail.com", destinatarios: list = None):
        self.dbutils = dbutils
        self.remetente = remetente
        self.destinatarios = destinatarios or [remetente]

    def _renderizar_detalhes_html(self, detalhes: dict) -> str:
        """Cada campo de detalhes vira uma linha de tabela; listas viram <ul>, não array JSON."""
        linhas = ""
        for chave, valor in detalhes.items():
            if isinstance(valor, list):
                valor_html = (
                    "<ul style='margin:0;padding-left:18px;'>"
                    + "".join(f"<li>{item}</li>" for item in valor)
                    + "</ul>"
                ) if valor else "<em>nenhum</em>"
            else:
                valor_html = str(valor)
            linhas += (
                f"<tr><td style='padding:6px 12px;border:1px solid #ddd;font-weight:bold;"
                f"background:#fafafa;'>{chave}</td>"
                f"<td style='padding:6px 12px;border:1px solid #ddd;'>{valor_html}</td></tr>"
            )
        return linhas

    def _construir_html(self, alerta: dict) -> str:
        cor = self._CORES_SEVERIDADE.get(alerta["severidade"], "#2c3e50")
        linhas_detalhes = self._renderizar_detalhes_html(alerta.get("detalhes", {}))

        return f"""
        <html>
        <body style="font-family:Arial,Helvetica,sans-serif;color:#2c3e50;background:#f4f4f4;padding:20px;">
          <div style="max-width:600px;margin:0 auto;background:#ffffff;border:1px solid #ddd;border-radius:8px;overflow:hidden;">
            <div style="background:{cor};color:#ffffff;padding:16px 20px;">
              <h2 style="margin:0;font-size:16px;">Pulse Health Platform — Alerta {alerta['severidade'].upper()}</h2>
            </div>
            <div style="padding:20px;">
              <p style="font-size:14px;line-height:1.5;margin-top:0;">{alerta['mensagem']}</p>
              <table style="border-collapse:collapse;width:100%;font-size:13px;">
                <tr><td style="padding:6px 12px;border:1px solid #ddd;font-weight:bold;background:#fafafa;">Tipo de evento</td><td style="padding:6px 12px;border:1px solid #ddd;">{alerta['tipo_evento']}</td></tr>
                <tr><td style="padding:6px 12px;border:1px solid #ddd;font-weight:bold;background:#fafafa;">Origem</td><td style="padding:6px 12px;border:1px solid #ddd;">{alerta['origem']}</td></tr>
                {linhas_detalhes}
              </table>
            </div>
            <div style="background:#f4f4f4;padding:10px 20px;font-size:11px;color:#888;">
              Enviado automaticamente pela plataforma Pulse Health Observability.
            </div>
          </div>
        </body>
        </html>
        """

    def _construir_texto(self, alerta: dict) -> str:
        return (
            f"{alerta['mensagem']}\n\n"
            f"Tipo de evento: {alerta['tipo_evento']}\n"
            f"Origem: {alerta['origem']}\n"
            f"Severidade: {alerta['severidade']}\n\n"
            f"Detalhes: {json.dumps(alerta.get('detalhes', {}), default=str, ensure_ascii=False, indent=2)}"
        )

    def notificar(self, alerta: dict) -> bool:
        try:
            senha = self.dbutils.secrets.get(scope="pulse-secrets", key="gmail-app-password")

            mensagem = MIMEMultipart("alternative")
            mensagem["Subject"] = f"[Pulse Health Platform] Alerta {alerta['severidade']}: {alerta['tipo_evento']}"
            mensagem["From"] = self.remetente
            mensagem["To"] = ", ".join(self.destinatarios)

            # texto puro primeiro (fallback), HTML por último — clientes de
            # email preferem a última parte do multipart/alternative quando
            # conseguem renderizar
            mensagem.attach(MIMEText(self._construir_texto(alerta), "plain"))
            mensagem.attach(MIMEText(self._construir_html(alerta), "html"))

            with smtplib.SMTP("smtp.gmail.com", 587) as servidor:
                servidor.starttls()
                servidor.login(self.remetente, senha)
                servidor.sendmail(self.remetente, self.destinatarios, mensagem.as_string())

            return True
        except Exception:
            return False