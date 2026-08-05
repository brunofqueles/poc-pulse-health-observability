"""
Simulador ERP — Manufacturing + Distribution.

Implementa SimuladorDeSistema para o ERP, cobrindo os dois módulos definidos
na Opção A (Manufacturing + Distribution numa única fonte no Dia 1).

Nesta primeira entrega: estrutura da classe, calendário (união dos dois
módulos) e gerar_seed() (catálogo dos 3 produtos fixos).
Próxima entrega: gerar_registros() com dbldatagen/Faker para as tabelas
de evento diário (erp_lotes_producao, erp_posicoes_estoque, erp_notas_expedicao).

Schema de referência: docs/schemas/erp.md.
"""

from datetime import date

from src.simuladores.simulador_base import SimuladorDeSistema


class SimuladorERP(SimuladorDeSistema):
    """
    Simulador do ERP (Manufacturing + Distribution).

    dias_operacionais é a união dos dois calendários (business-context.md):
    Manufacturing opera Segunda a Sexta, Distribution opera Segunda a Sábado.
    A distinção entre os dois é resolvida dentro de gerar_registros() — ver
    próxima entrega — não no calendário externo.
    """

    @property
    def nome_sistema(self) -> str:
        return "erp"

    @property
    def dias_operacionais(self) -> set:
        # segunda=0 ... sábado=5 — união de Manufacturing (Seg-Sex) e Distribution (Seg-Sáb)
        return {0, 1, 2, 3, 4, 5}

    def gerar_seed(self) -> dict:
        """
        Catálogo fixo de produtos (docs/schemas/erp.md).

        3 produtos, cada um cobrindo uma forma farmacêutica distinta, para
        manter os cenários de teste concretos e verificáveis. Imunorax é o
        único produto que deve acionar a regra de cadeia fria na Logistics.
        """
        produtos = [
            {
                "produto_id": "PROD-001",
                "nome_produto": "Vitalectra 500mg",
                "forma_farmaceutica": "comprimido",
                "exige_cadeia_fria": False,
                "validade_padrao_dias": 730,
            },
            {
                "produto_id": "PROD-002",
                "nome_produto": "Imunorax",
                "forma_farmaceutica": "injetável",
                "exige_cadeia_fria": True,
                "validade_padrao_dias": 365,
            },
            {
                "produto_id": "PROD-003",
                "nome_produto": "Pulmoxil",
                "forma_farmaceutica": "xarope",
                "exige_cadeia_fria": False,
                "validade_padrao_dias": 180,
            },
        ]
        return {"erp_produtos": produtos}

    def gerar_registros(self, data_referencia: date) -> dict:
        """
        Tabelas de evento diário (erp_lotes_producao, erp_posicoes_estoque,
        erp_notas_expedicao). Ainda não implementado — próxima entrega.
        """
        raise NotImplementedError(
            "gerar_registros() do SimuladorERP ainda não implementado — "
            "próxima entrega (dbldatagen/Faker + sujeira intencional)."
        )