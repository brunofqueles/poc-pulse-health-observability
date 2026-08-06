"""
Simulador Financeiro — SSC (Shared Services Center).

Implementa SimuladorDeSistema para o Financeiro. Opera Segunda a Sexta
(business-context.md).

Dependência de execução (estende o padrão do ADR-011): lê crm_pedidos e
tms_comprovantes_entrega -> tms_remessas, todos da mesma data_referencia.
A cadeia completa (CRM -> ERP -> TMS -> Financeiro) colapsa no mesmo dia
na simulação atual — cada sistema sempre lê o mesmo dia do anterior, sem
defasagem real de tempo entre pedido e entrega (mesma simplificação de
continuidade já registrada em ADR-010).

Regra de negócio: fatura só é gerada para pedido com entrega confirmada
(pod_confirmado). Valor faturado ocasionalmente diverge do valor do pedido
original, de propósito — gatilho do eixo de negócio da observabilidade
(reconciliação, docs/schemas/financeiro.md).

Schema de referência: docs/schemas/financeiro.md.
"""

import random
from datetime import date, timedelta

from src.simuladores.simulador_base import SimuladorDeSistema
from src.simuladores.sujeira_intencional import (
    formatar_data_suja,
    formatar_numero_sujo,
    formatar_texto_sujo,
    valor_nulo_variado,
    com_probabilidade,
)


class SimuladorFinanceiro(SimuladorDeSistema):
    """Simulador do Financeiro (SSC)."""

    @property
    def nome_sistema(self) -> str:
        return "financeiro"

    @property
    def dias_operacionais(self) -> set:
        # segunda=0 ... sexta=4 (business-context.md)
        return {0, 1, 2, 3, 4}

    def gerar_seed(self) -> dict:
        """Centros de custo fixos, um por área operacional do conglomerado."""
        centros = [
            {"centro_custo_id": "CC-001", "nome_centro_custo": "Manufacturing"},
            {"centro_custo_id": "CC-002", "nome_centro_custo": "Distribution"},
            {"centro_custo_id": "CC-003", "nome_centro_custo": "Logistics"},
            {"centro_custo_id": "CC-004", "nome_centro_custo": "Commercial"},
        ]
        return {"financeiro_centros_custo": centros}

    def gerar_registros(self, data_referencia: date) -> dict:
        """Financeiro opera Segunda a Sexta — sem checagem interna adicional de calendário."""
        entregas_confirmadas = self._ler_entregas_confirmadas(data_referencia)
        if not entregas_confirmadas:
            return {}  # nenhuma entrega confirmada hoje — nada a faturar

        pedidos = self._ler_pedidos_crm(data_referencia)

        faturas = self._gerar_faturas(data_referencia, entregas_confirmadas, pedidos)
        if not faturas:
            return {}

        contas_receber = self._gerar_contas_receber(data_referencia, faturas)

        return {
            "financeiro_faturas": [f["registro"] for f in faturas],
            "financeiro_contas_receber": contas_receber,
        }

    def _ler_entregas_confirmadas(self, data_referencia: date) -> list:
        """
        Lê tms_comprovantes_entrega + tms_remessas do TMS (mesma data),
        retornando só as entregas com POD confirmado — regra de negócio:
        fatura só após entrega confirmada.
        """
        data_str = data_referencia.strftime("%Y-%m-%d")
        base = f"/Volumes/{self.catalog}/landing/{self.volume_landing}/tms/data={data_str}"

        try:
            df_comprovantes = self.spark.read.json(f"{base}/tms_comprovantes_entrega.json")
            df_remessas = self.spark.read.json(f"{base}/tms_remessas.json")
        except Exception:
            return []

        df_join = df_comprovantes.join(
            df_remessas.select("remessa_id", "pedido_id"), "remessa_id"
        )

        # pod_confirmado mistura booleano real (True) com nulo variado
        # (None/""/"N/A"/"NULL") no mesmo campo — o Spark infere a coluna
        # como string ao ler de volta (tipos mistos), e True vira o texto
        # "true", não o booleano Python. Comparar como string, coerente
        # com a regra de que Bronze é 100% string (architecture.md).
        linhas = df_join.select("remessa_id", "pedido_id", "pod_confirmado").collect()
        return [
            {"remessa_id": r.remessa_id, "pedido_id": r.pedido_id}
            for r in linhas
            if str(r.pod_confirmado).lower() == "true"
        ]

    def _ler_pedidos_crm(self, data_referencia: date) -> dict:
        """Lê crm_pedidos da mesma data, retornando {pedido_id: valor_total}."""
        data_str = data_referencia.strftime("%Y-%m-%d")
        caminho = f"/Volumes/{self.catalog}/landing/{self.volume_landing}/crm/data={data_str}/crm_pedidos.json"
        try:
            df = self.spark.read.json(caminho)
            linhas = df.select("pedido_id", "valor_total").collect()
        except Exception:
            return {}
        return {r.pedido_id: r.valor_total for r in linhas}

    def _gerar_faturas(self, data_referencia: date, entregas_confirmadas: list, pedidos: dict) -> list:
        """
        Gera uma fatura por entrega confirmada. Valor faturado diverge do
        valor original do pedido em ~8% dos casos, de propósito — gatilho
        de reconciliação (eixo de negócio da observabilidade).
        """
        centros = self.gerar_seed()["financeiro_centros_custo"]

        faturas = []
        for indice, entrega in enumerate(entregas_confirmadas):
            valor_pedido_str = pedidos.get(entrega["pedido_id"])
            if valor_pedido_str is None:
                continue  # pedido não encontrado no CRM do dia — pula, não inventa valor

            # valor_pedido_str já está sujo (formato BR) — reconstrói o número
            # limpo antes de decidir se diverge, para não acumular sujeira em cima de sujeira
            valor_limpo = float(valor_pedido_str.replace(".", "").replace(",", "."))

            if com_probabilidade(0.08):  # ~8% de divergência, de propósito
                valor_faturado = valor_limpo * random.uniform(0.85, 1.15)
            else:
                valor_faturado = valor_limpo

            fatura_id = f"FAT-{data_referencia.strftime('%Y%m%d')}-{indice:04d}"
            centro_custo = random.choice(centros)
            data_faturamento = data_referencia + timedelta(days=random.randint(0, 2))

            registro = {
                "fatura_id": fatura_id,
                "pedido_id": entrega["pedido_id"],
                "remessa_id": entrega["remessa_id"],
                "valor_faturado": formatar_numero_sujo(valor_faturado),
                "data_faturamento": formatar_data_suja(data_faturamento),
                "centro_custo_id": (
                    valor_nulo_variado() if com_probabilidade(0.03)  # 3% sem centro de custo, de propósito
                    else centro_custo["centro_custo_id"]
                ),
            }
            faturas.append({"registro": registro, "fatura_id": fatura_id, "data_faturamento": data_faturamento})

        return faturas

    def _gerar_contas_receber(self, data_referencia: date, faturas: list) -> list:
        """Gera uma conta a receber por fatura, com data de recebimento ocasionalmente nula (ainda não recebido)."""
        registros = []
        for f in faturas:
            data_vencimento = f["data_faturamento"] + timedelta(days=30)
            recebido = com_probabilidade(0.6)  # 60% já recebido, no momento da simulação

            registros.append({
                "conta_receber_id": f"CR-{f['fatura_id']}",
                "fatura_id": f["fatura_id"],
                "data_vencimento": formatar_data_suja(data_vencimento),
                "data_recebimento": formatar_data_suja(data_vencimento) if recebido else valor_nulo_variado(),
                "status_conta": formatar_texto_sujo("recebido" if recebido else "em aberto"),
            })

        return registros