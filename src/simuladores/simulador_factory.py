"""
SimuladorFactory — mapeia nome de sistema para a classe de simulador correta.

Usado pelo notebook orquestrador (src/orquestracao/gerar_dados.py) para
instanciar o simulador certo a partir do Widget `sistema` (ADR-008), e para
saber a ordem de execução que respeita a cadeia de dependência (ADR-011).
"""

from src.simuladores.simulador_erp import SimuladorERP
from src.simuladores.simulador_crm import SimuladorCRM
from src.simuladores.simulador_tms import SimuladorTMS
from src.simuladores.simulador_financeiro import SimuladorFinanceiro


class SimuladorFactory:
    """Cria simuladores por nome e informa a ordem de execução correta."""

    _REGISTRO = {
        "crm": SimuladorCRM,
        "erp": SimuladorERP,
        "tms": SimuladorTMS,
        "financeiro": SimuladorFinanceiro,
    }

    @classmethod
    def criar(cls, nome_sistema: str, spark, dbutils):
        """Instancia o simulador correspondente a nome_sistema. Levanta ValueError se desconhecido."""
        classe = cls._REGISTRO.get(nome_sistema)
        if classe is None:
            sistemas_validos = ", ".join(cls._REGISTRO.keys())
            raise ValueError(f"Sistema desconhecido: '{nome_sistema}'. Válidos: {sistemas_validos}")
        return classe(spark=spark, dbutils=dbutils)

    @classmethod
    def ordem_execucao(cls) -> list:
        """
        Ordem de execução que respeita a cadeia de dependência de geração
        (ADR-011): CRM -> ERP -> TMS -> Financeiro. Cada sistema lê o(s)
        anterior(es) da Landing Zone para a mesma data_referencia.
        """
        return ["crm", "erp", "tms", "financeiro"]