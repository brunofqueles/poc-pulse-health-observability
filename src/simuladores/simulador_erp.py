"""
Simulador ERP — Manufacturing + Distribution.

Implementa SimuladorDeSistema para o ERP, cobrindo os dois módulos definidos
na Opção A (Manufacturing + Distribution numa única fonte no Dia 1).

dias_operacionais é a união dos dois calendários (Segunda a Sábado):
Manufacturing opera só Segunda a Sexta (checagem interna em gerar_registros);
Distribution opera Segunda a Sábado — o mesmo que a união externa, então
não precisa de checagem adicional.

Nesta entrega: erp_lotes_producao (Manufacturing) e erp_posicoes_estoque
(Distribution). erp_notas_expedicao fica pendente — depende de pedido_id do
CRM, que ainda não existe (SimuladorCRM é a próxima peça do projeto).

Limitação conhecida: o simulador não mantém memória entre execuções de
gerar_dia() — erp_posicoes_estoque referencia lote_id de forma sintética
(não garantido existir fisicamente na Bronze ainda). Resolver quando a
Silver tiver histórico real consultável — fora do escopo desta entrega.

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
    """Simulador do ERP (Manufacturing + Distribution)."""

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
        Gera as tabelas de evento diário do ERP, respeitando o calendário
        de cada módulo internamente (dias_operacionais externo é só a união).
        """
        registros_por_tabela = {}

        # Manufacturing opera Segunda a Sexta (business-context.md)
        if data_referencia.weekday() in {0, 1, 2, 3, 4}:
            registros_por_tabela["erp_lotes_producao"] = self._gerar_lotes_producao(data_referencia)

        # Distribution opera Segunda a Sábado — coincide com dias_operacionais
        # da classe (a união), então roda sempre que gerar_registros é chamado
        registros_por_tabela["erp_posicoes_estoque"] = self._gerar_posicoes_estoque(data_referencia)

        # erp_notas_expedicao: depende de pedido_id do CRM — adiado até
        # o SimuladorCRM existir (pedido_id precisa referenciar pedido real)

        return registros_por_tabela

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

    def _gerar_posicoes_estoque(self, data_referencia: date) -> list:
        """
        Gera as posições de estoque do dia (Distribution).

        lote_id é referenciado de forma sintética — o simulador não mantém
        memória entre dias, então não há garantia de que o lote citado
        exista fisicamente na Bronze ainda (limitação conhecida, documentada
        no cabeçalho do arquivo).
        """
        num_posicoes = random.randint(30, 60)

        df_base = (
            dg.DataGenerator(self.spark, name="erp_posicoes_estoque", rows=num_posicoes, seedColumnName="_seed_id")
            .withColumn("centro_distribuicao_id", "string", values=["CD01", "CD02"], random=True)
            .withColumn("quantidade", "int", minValue=10, maxValue=500, random=True)
            .build()
        )

        registros = []
        for row in df_base.collect():
            dia_lote = data_referencia - timedelta(days=random.randint(0, 5))
            lote_id_referenciado = f"LOTE-{dia_lote.strftime('%Y%m%d')}-{random.randint(0, 79):04d}"

            quantidade = row["quantidade"]
            if com_probabilidade(0.05):  # 5% de estoque negativo, de propósito (docs/schemas/erp.md)
                quantidade = -quantidade

            registros.append({
                "lote_id": lote_id_referenciado,
                "centro_distribuicao_id": formatar_texto_sujo(row["centro_distribuicao_id"]),
                "quantidade": formatar_numero_sujo(quantidade, casas_decimais=0),
                "data_posicao": formatar_data_suja(data_referencia),
            })

        return registros