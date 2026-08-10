"""
Simulador CRM — Pulse Commercial.

Implementa SimuladorDeSistema para o CRM. Opera todos os dias da semana
(business-context.md) — pedido pode chegar por canal online mesmo fora do
expediente.

Reaproveita o catálogo de produtos do ERP (SimuladorERP.gerar_seed()) para
crm_itens_pedido, evitando duplicar a lista de produtos em dois arquivos.

Simplificação consciente: clientes/representantes nascem como seed fixo
nesta entrega — crescimento esporádico real (business-context.md) fica para
uma evolução futura, não implementado agora.

A violação "cliente bloqueado não pode pedir" emerge naturalmente da
distribuição (pedidos escolhem cliente aleatoriamente entre todos, incluindo
os ~5% bloqueados do seed) — não é forçada com lógica extra.

Schema de referência: docs/schemas/crm.md.
"""

import random
from datetime import date, timedelta

import dbldatagen as dg
from faker import Faker

from src.simuladores.simulador_base import SimuladorDeSistema
from src.simuladores.simulador_erp import SimuladorERP
from src.simuladores.sujeira_intencional import (
    formatar_data_suja,
    formatar_numero_sujo,
    formatar_texto_sujo,
    valor_nulo_variado,
    com_probabilidade,
)

_fake = Faker("pt_BR")


class SimuladorCRM(SimuladorDeSistema):
    """Simulador do CRM (Pulse Commercial)."""

    @property
    def nome_sistema(self) -> str:
        return "crm"

    @property
    def dias_operacionais(self) -> set:
        # todos os dias da semana — pedido pode chegar por canal online fora do expediente
        return {0, 1, 2, 3, 4, 5, 6}

    def gerar_seed(self) -> dict:
        """
        Representantes e clientes fixos (simplificação consciente — crescimento
        esporádico real fica para evolução futura, não implementado agora).
        """
        representantes = [
            {
                "representante_id": f"REP-{i:03d}",
                "nome_representante": _fake.name(),
                "regiao": random.choice(["Sudeste", "Sul", "Nordeste", "Centro-Oeste", "Norte"]),
            }
            for i in range(1, 9)
        ]

        clientes = []
        for i in range(1, 26):
            bloqueado = com_probabilidade(0.05)  # 5% bloqueado (docs/schemas/crm.md)
            clientes.append({
                "cliente_id": f"CLI-{i:04d}",
                "nome_cliente": _fake.company(),
                "email_contato": _fake.company_email(),
                "regiao": random.choice(["Sudeste", "Sul", "Nordeste", "Centro-Oeste", "Norte"]),
                "status_cliente": "bloqueado" if bloqueado else "ativo",
            })

        return {"crm_representantes": representantes, "crm_clientes": clientes}

    def gerar_registros(self, data_referencia: date) -> dict:
        """CRM opera todos os dias — sem checagem interna adicional de calendário."""
        pedidos, itens = self._gerar_pedidos_e_itens(data_referencia)
        return {
            "crm_pedidos": pedidos,
            "crm_itens_pedido": itens,
            "crm_atendimento": self._gerar_atendimento(data_referencia),
        }

    def _gerar_pedidos_e_itens(self, data_referencia: date) -> tuple:
        """
        Gera pedidos e seus itens juntos, porque item depende do pedido pai.

        dbldatagen cuida só do valor_total "limpo"; o resto (chave, cliente,
        representante, itens) é resolvido em Python, por precisar de lógica
        de referência entre entidades (pedido -> item -> produto).
        """
        seed = self.gerar_seed()
        clientes = seed["crm_clientes"]
        representantes = seed["crm_representantes"]

        catalogo_produtos = SimuladorERP(spark=self.spark, dbutils=self.dbutils).gerar_seed()["erp_produtos"]
        ids_produtos_validos = [p["produto_id"] for p in catalogo_produtos]

        num_pedidos = random.randint(150, 300)  # volumetria (business-context.md)

        df_base = (
            dg.DataGenerator(self.spark, name="crm_pedidos", rows=num_pedidos, seedColumnName="_seed_id")
            .withColumn("valor_total", "float", minValue=50.0, maxValue=5000.0, random=True)
            .build()
        )

        pedidos = []
        itens = []
        for indice, row in enumerate(df_base.collect()):
            pedido_id = f"PEDIDO-{data_referencia.strftime('%Y%m%d')}-{indice:04d}"
            cliente = random.choice(clientes)
            representante = random.choice(representantes)
            status = random.choice(["aberto", "em separacao", "concluido", "cancelado"])

            pedidos.append({
                "pedido_id": pedido_id,
                "cliente_id": cliente["cliente_id"],
                "representante_id": representante["representante_id"],
                "data_pedido": formatar_data_suja(data_referencia),
                "valor_total": formatar_numero_sujo(row["valor_total"]),
                "status_pedido": formatar_texto_sujo(status),
            })

            num_itens = random.randint(1, 4)
            for indice_item in range(num_itens):
                produto_id = random.choice(ids_produtos_validos)
                if com_probabilidade(0.03):  # 3% SKU inexistente, de propósito (docs/schemas/crm.md)
                    produto_id = "PROD-999"

                itens.append({
                    "item_pedido_id": f"ITEM-{data_referencia.strftime('%Y%m%d')}-{indice:04d}-{indice_item:02d}",
                    "pedido_id": pedido_id,
                    "produto_id": produto_id,
                    "quantidade": formatar_numero_sujo(random.randint(1, 50), casas_decimais=0),
                    "preco_unitario": formatar_numero_sujo(random.uniform(10.0, 500.0)),
                })

        return pedidos, itens

    def _gerar_atendimento(self, data_referencia: date) -> list:
        """Gera interações de atendimento do dia (baixo volume)."""
        seed = self.gerar_seed()
        clientes = seed["crm_clientes"]
        num_interacoes = random.randint(20, 40)  # volumetria (business-context.md)

        tipos = ["reclamacao", "duvida", "elogio", "solicitacao"]

        registros = []
        for i in range(num_interacoes):
            cliente = random.choice(clientes)

            # lote_id preenchido só ocasionalmente — gatilho de correlação com recall
            if com_probabilidade(0.1):
                dia_lote = data_referencia - timedelta(days=random.randint(0, 5))
                lote_id = f"LOTE-{dia_lote.strftime('%Y%m%d')}-{random.randint(0, 79):04d}"
            else:
                lote_id = valor_nulo_variado()

            registros.append({
                "interacao_id": f"ATEND-{data_referencia.strftime('%Y%m%d')}-{i:04d}",
                "cliente_id": cliente["cliente_id"],
                "lote_id": lote_id,
                "tipo_interacao": formatar_texto_sujo(random.choice(tipos)),
                "descricao": _fake.sentence(),
                "data_interacao": formatar_data_suja(data_referencia),
            })

        return registros