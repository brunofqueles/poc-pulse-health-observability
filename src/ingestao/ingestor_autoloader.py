"""
IngestorAutoloader — ingestão genérica Landing Zone -> Bronze via Autoloader.

Classe única, parametrizada por sistema e tabela — diferente dos simuladores
(que têm uma subclasse por sistema), a lógica de ingestão é idêntica para
qualquer tabela; só os parâmetros mudam.

Streaming (Structured Streaming + Autoloader, Trigger.AvailableNow) só se
aplica aqui, entre Landing e Bronze — o único ponto do fluxo genuinamente
append-only (ADR-002).

Validado via spike (src/spikes/teste_autoloader_erp_lotes_producao):
cloudFiles funciona no compute serverless da Free Edition, pathGlobFilter
isola corretamente uma tabela dentro da pasta do sistema (que tem várias
tabelas na mesma partição data=), e inferColumnTypes=false preserva Bronze
100% string (ADR-001). Idempotência confirmada: reexecutar não reprocessa
arquivos já ingeridos (checkpoint).
"""


class IngestorAutoloader:
    """Ingestão genérica de uma tabela, da Landing Zone para a Bronze, via Autoloader."""

    def __init__(
        self,
        spark,
        sistema: str,
        tabela: str,
        catalog: str = "poc_pulse_observability",
        volume_landing: str = "raw",
    ):
        self.spark = spark
        self.sistema = sistema
        self.tabela = tabela
        self.catalog = catalog
        self.volume_landing = volume_landing

    def _caminho_landing(self) -> str:
        return f"/Volumes/{self.catalog}/landing/{self.volume_landing}/{self.sistema}"

    def _caminho_schema(self) -> str:
        return f"/Volumes/{self.catalog}/landing/{self.volume_landing}/_autoloader_schema/{self.tabela}"

    def _caminho_checkpoint(self) -> str:
        return f"/Volumes/{self.catalog}/landing/{self.volume_landing}/_autoloader_checkpoint/{self.tabela}"

    def executar(self) -> dict:
        """
        Lê os arquivos novos da tabela na Landing Zone e grava na Bronze,
        via Autoloader com Trigger.AvailableNow (ADR-002).
        """
        df_stream = (
            self.spark.readStream
            .format("cloudFiles")
            .option("cloudFiles.format", "json")
            .option("cloudFiles.inferColumnTypes", "false")
            .option("cloudFiles.schemaLocation", self._caminho_schema())
            .option("pathGlobFilter", f"{self.tabela}.json")
            .load(self._caminho_landing())
        )

        query = (
            df_stream.writeStream
            .format("delta")
            .option("checkpointLocation", self._caminho_checkpoint())
            .trigger(availableNow=True)
            .toTable(f"{self.catalog}.bronze.{self.tabela}")
        )
        query.awaitTermination()

        # Trigger.AvailableNow pode processar em mais de um micro-lote numa
        # única execução — query.lastProgress só traz o ÚLTIMO, que pode ser
        # um lote de confirmação vazio, escondendo que um lote anterior da
        # MESMA execução já processou dado de verdade. Somar todos os
        # micro-lotes de query.recentProgress evita esse falso negativo.
        arquivos_processados = 0
        linhas_processadas = 0
        for progresso in query.recentProgress:
            try:
                metricas = progresso["sources"][0]["metrics"]
                arquivos_processados += int(metricas.get("numFilesProcessed", 0))
                linhas_processadas += progresso["sources"][0].get("numInputRows", 0)
            except (KeyError, IndexError):
                continue

        status = "sucesso" if arquivos_processados > 0 else "sem_dado_novo"

        return {
            "tabela": self.tabela,
            "status": status,
            "arquivos_processados": arquivos_processados,
            "linhas_processadas": linhas_processadas,
        }