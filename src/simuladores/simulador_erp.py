"""
Simulador ERP — Manufacturing.

A partir do 5º pipeline (demonstração de escala), o ERP cobre só
Manufacturing — Distribution foi separada para SimuladorDistribution
(distribution/erp_posicoes_estoque, distribution/erp_notas_expedicao,
embora os nomes de tabela permaneçam erp_posicoes_estoque/
erp_notas_expedicao, sem alteração, para não exigir mudança em Gold/
observability/schemas que já as referenciam).

dias_operacionais volta a ser Segunda a Sexta (calendário próprio de
Manufacturing) — deixa de ser a união com Distribution, já que essa
distinção agora vive em classes separadas, não numa checagem interna.

Ver ADR-011 (adendo) para a nova cadeia de dependência de geração:
CRM → ERP → Distribution → TMS → Financeiro.

Schema de referência: docs/schemas/erp.md.
"""

import random
from datetime import date, timedelta

import dbldatagen as dg

from src.simuladores.simulador_base import SimuladorDeSistema
from src.simuladores.sujeira_intencional import (
    formatar_data_suja,
    formatar_numero_sujo,
    formatar_texto_sujo,
    valor_nulo_variado,
    com_probabilidade,
)


class SimuladorERP(SimuladorDeSistema):
    """Simulador do ERP (Manufacturing)."""

    @property
    def nome_sistema(self) -> str:
        return "erp"

    @property
    def dias_operacionais(self) -> set:
        # segunda=0 ... sexta=4 — calendário de Manufacturing
        return {0, 1, 2, 3, 4}

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
        Gera erp_lotes_producao (Manufacturing). Distribution foi separada
        para SimuladorDistribution — sem checagem interna adicional de
        calendário, já que dias_operacionais agora é só Manufacturing.
        """
        return {"erp_lotes_producao": self._gerar_lotes_producao(data_referencia)}

    def _gerar_lotes_producao(self, data_referencia: date) -> list:
        """
        Gera os lotes de produção do dia (Manufacturing).

        dbldatagen cuida da parte aleatória "limpa" (produto, centro,
        quantidade); chave, datas e sujeira intencional são resolvidas em
        Python puro, por controle e clareza sobre a lógica de negócio.
        """
        catalogo_produtos = self.gerar_seed()["erp_produtos"]
        ids_produtos = [p["produto_id"] for p in catalogo_produtos]
        num_lotes = random.randint(40, 80)  # volumetria (business-context.md)

        df_base = (
            dg.DataGenerator(self.spark, name="erp_lotes_producao", rows=num_lotes, seedColumnName="_seed_id")
            .withColumn("produto_id", "string", values=ids_produtos, random=True)
            .withColumn("centro_producao_id", "string", values=["CP01", "CP02"], random=True)
            .withColumn("quantidade_produzida", "int", minValue=500, maxValue=5000, random=True)
            .build()
        )

        registros = []
        for indice, row in enumerate(df_base.collect()):
            produto = next(p for p in catalogo_produtos if p["produto_id"] == row["produto_id"])
            aprovado = com_probabilidade(0.9)  # 90% aprovado / 10% reprovado (docs/schemas/erp.md)

            lote_id = f"LOTE-{data_referencia.strftime('%Y%m%d')}-{indice:04d}"
            data_validade = data_referencia + timedelta(days=produto["validade_padrao_dias"])

            registros.append({
                "lote_id": lote_id,
                "produto_id": row["produto_id"],
                "centro_producao_id": formatar_texto_sujo(row["centro_producao_id"]),
                "data_fabricacao": formatar_data_suja(data_referencia),
                "data_validade": formatar_data_suja(data_validade),
                "quantidade_produzida": formatar_numero_sujo(row["quantidade_produzida"]),
                "status_qc": formatar_texto_sujo("aprovado" if aprovado else "reprovado"),
                "data_liberacao": formatar_data_suja(data_referencia) if aprovado else valor_nulo_variado(),
            })

        return registros