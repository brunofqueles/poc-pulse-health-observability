"""
Testes de src/simuladores/simulador_factory.py.

Testa só o mapeamento e a ordem — não instancia os simuladores de verdade
(exigiria sessão Spark ativa, fora do escopo de teste unitário puro).
"""

import pytest

from src.simuladores.simulador_factory import SimuladorFactory
from src.simuladores.simulador_erp import SimuladorERP
from src.simuladores.simulador_crm import SimuladorCRM
from src.simuladores.simulador_tms import SimuladorTMS
from src.simuladores.simulador_financeiro import SimuladorFinanceiro


class TestOrdemExecucao:
    def test_ordem_respeita_a_dependencia_do_adr011(self):
        assert SimuladorFactory.ordem_execucao() == ["crm", "erp", "tms", "financeiro"]

    def test_ordem_tem_os_4_sistemas_sem_repeticao(self):
        ordem = SimuladorFactory.ordem_execucao()
        assert len(ordem) == 4
        assert len(set(ordem)) == 4


class TestCriar:
    @pytest.mark.parametrize(
        "nome_sistema, classe_esperada",
        [
            ("erp", SimuladorERP),
            ("crm", SimuladorCRM),
            ("tms", SimuladorTMS),
            ("financeiro", SimuladorFinanceiro),
        ],
    )
    def test_cada_sistema_instancia_a_classe_certa(self, nome_sistema, classe_esperada):
        simulador = SimuladorFactory.criar(nome_sistema, spark=None, dbutils=None)
        assert isinstance(simulador, classe_esperada)

    def test_sistema_desconhecido_levanta_erro_claro(self):
        with pytest.raises(ValueError, match="Sistema desconhecido"):
            SimuladorFactory.criar("sistema_inexistente", spark=None, dbutils=None)