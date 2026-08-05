"""
Simulador de Sistema — Classe base.

Define o contrato comum que os 4 simuladores de sistema (ERP, CRM, TMS, Financeiro)
implementam, cada um com seu próprio schema de geração de dados.

O que esta classe resolve:
- Verifica o calendário de operação do sistema antes de gerar qualquer dado (business-context.md)
- Monta o caminho da Landing Zone na convenção <sistema>/data=AAAA-MM-DD/ (ADR-001)
- Grava os registros gerados como JSON, pronto para o Autoloader ler
- Separa dado de dimensão fixa (catálogo, via gerar_seed()/executar_seed()) do ciclo
  de evento diário (gerar_dia())

O que cada subclasse precisa implementar:
- nome_sistema — nome curto usado no path (ex.: "erp")
- dias_operacionais — quais dias da semana o sistema opera
- gerar_registros(data_referencia) — a lógica de geração propriamente dita (dbldatagen/Faker)
- gerar_seed() — opcional, só se o sistema tiver dimensão fixa (catálogo)

Nota técnica: `dbutils` não é injetado automaticamente em arquivos .py importados
(diferente de dentro de um notebook) — por isso é recebido explicitamente no
construtor, assim como `spark`. Quem instancia a classe a partir de um notebook
passa o `dbutils` já disponível ali.

Referências: ADR-001 (Landing Zone), ADR-003 (Programação Orientada a Objetos),
ADR-008 (Widgets e reprocessamento).
"""

from abc import ABC, abstractmethod
from datetime import date
import json


class SimuladorDeSistema(ABC):
    """
    Classe base para os simuladores de sistema do Pulse Health Platform.

    Cada sistema (ERP, CRM, TMS, Financeiro) implementa sua própria subclasse,
    definindo o schema de geração e o calendário de operação. Ver ADR-003.
    """

    def __init__(self, spark, dbutils, catalog: str = "poc_pulse_observability", volume_landing: str = "raw"):
        self.spark = spark
        self.dbutils = dbutils
        self.catalog = catalog
        self.volume_landing = volume_landing

    @property
    @abstractmethod
    def nome_sistema(self) -> str:
        """Nome curto do sistema, usado no path da Landing Zone (ex.: 'erp')."""
        ...

    @property
    @abstractmethod
    def dias_operacionais(self) -> set:
        """
        Dias da semana em que o sistema opera.
        Convenção Python: segunda=0 ... domingo=6.
        """
        ...

    def opera_em(self, data_referencia: date) -> bool:
        """Verifica se o sistema opera na data de referência, conforme seu calendário."""
        return data_referencia.weekday() in self.dias_operacionais

    @abstractmethod
    def gerar_registros(self, data_referencia: date) -> dict:
        """
        Gera os registros do dia para este sistema.

        Implementado por cada subclasse com seu próprio schema dbldatagen/Faker.
        Retorna um dicionário {nome_tabela: lista_de_registros}.
        """
        ...

    def caminho_landing(self, data_referencia: date) -> str:
        """Monta o path da Landing Zone para este sistema e data (ADR-001)."""
        data_str = data_referencia.strftime("%Y-%m-%d")
        return f"/Volumes/{self.catalog}/landing/{self.volume_landing}/{self.nome_sistema}/data={data_str}"

    def gerar_dia(self, data_referencia: date) -> dict:
        """
        Contrato principal (ADR-003).

        Verifica o calendário, gera os registros e grava como JSON na Landing Zone.
        Retorna um resumo da execução, incluindo o status "dia_nao_operacional"
        quando o sistema não opera naquela data — não é falha (ADR-007).
        """
        if not self.opera_em(data_referencia):
            return {
                "sistema": self.nome_sistema,
                "data_referencia": str(data_referencia),
                "status": "dia_nao_operacional",
                "tabelas_geradas": [],
            }

        registros_por_tabela = self.gerar_registros(data_referencia)
        caminho = self.caminho_landing(data_referencia)
        tabelas_geradas = []

        for nome_tabela, registros in registros_por_tabela.items():
            destino = f"{caminho}/{nome_tabela}.json"
            self._gravar_json(registros, destino)
            tabelas_geradas.append(nome_tabela)

        return {
            "sistema": self.nome_sistema,
            "data_referencia": str(data_referencia),
            "status": "sucesso",
            "tabelas_geradas": tabelas_geradas,
        }

    def gerar_seed(self) -> dict:
        """
        Gera dados de dimensão fixa (catálogo), executado uma única vez —
        não faz parte do ciclo diário. Sistemas sem dimensão fixa não
        precisam sobrescrever este método.
        """
        return {}

    def caminho_landing_seed(self) -> str:
        """Caminho da Landing Zone para dados de seed, sem partição de data."""
        return f"/Volumes/{self.catalog}/landing/{self.volume_landing}/{self.nome_sistema}/_seed"

    def executar_seed(self) -> dict:
        """Executa a geração de seed e grava na Landing Zone, se houver dado de dimensão fixa."""
        registros_por_tabela = self.gerar_seed()
        if not registros_por_tabela:
            return {"sistema": self.nome_sistema, "status": "sem_seed", "tabelas_geradas": []}

        caminho = self.caminho_landing_seed()
        tabelas_geradas = []
        for nome_tabela, registros in registros_por_tabela.items():
            destino = f"{caminho}/{nome_tabela}.json"
            self._gravar_json(registros, destino)
            tabelas_geradas.append(nome_tabela)

        return {"sistema": self.nome_sistema, "status": "sucesso", "tabelas_geradas": tabelas_geradas}

    def _gravar_json(self, registros: list, destino: str) -> None:
        """Grava a lista de registros como JSON linha-a-linha (formato esperado pelo Autoloader)."""
        conteudo = "\n".join(json.dumps(r, ensure_ascii=False) for r in registros)
        self.dbutils.fs.put(destino, conteudo, overwrite=True)