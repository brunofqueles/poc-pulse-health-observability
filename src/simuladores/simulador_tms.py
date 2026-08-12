"""
Simulador TMS — Pulse Logistics.

Implementa SimuladorDeSistema para o TMS. Opera Segunda a Sábado
(business-context.md).

Dependência de execução (estende o padrão do ADR-011): lê erp_notas_expedicao
e erp_lotes_producao, ambos da Landing Zone do ERP, para a mesma
data_referencia. O ERP precisa já ter rodado antes do TMS, no mesmo dia.

Falha cruzada intencional (docs/schemas/tms.md): remessa de produto que
exige cadeia fria ocasionalmente alocada a veículo sem refrigeração — só
detectável cruzando tms_remessas.veiculo_id -> tms_veiculos.refrigerado
contra erp_lotes_producao.produto_id -> exige_cadeia_fria.

Limitação conhecida (estende a já documentada em ADR-010/erp_posicoes_estoque):
quando o lote referenciado numa nota de expedição não pertence à produção do
próprio dia (ex.: lote antigo, ou dia sem produção), o TMS não consegue
resolver o produto real — nesse caso, assume conservadoramente que o lote
não exige cadeia fria, em vez de arriscar uma suposição no sentido contrário.

Schema de referência: docs/schemas/tms.md.
"""

import random
from datetime import date, timedelta

from src.simuladores.simulador_base import SimuladorDeSistema
from src.simuladores.simulador_erp import SimuladorERP
from src.simuladores.sujeira_intencional import (
    formatar_data_suja,
    formatar_numero_sujo,
    formatar_texto_sujo,
    valor_nulo_variado,
    com_probabilidade,
)


class SimuladorTMS(SimuladorDeSistema):
    """Simulador do TMS (Pulse Logistics)."""

    @property
    def nome_sistema(self) -> str:
        return "tms"

    @property
    def dias_operacionais(self) -> set:
        # segunda=0 ... sábado=5 (business-context.md)
        return {0, 1, 2, 3, 4, 5}

    def gerar_seed(self) -> dict:
        """Veículos e rotas fixos — 6 veículos (2 refrigerados), 4 rotas."""
        veiculos = [
            {"veiculo_id": "VEI-001", "placa": "ABC1D23", "tipo_veiculo": "van", "refrigerado": False},
            {"veiculo_id": "VEI-002", "placa": "ABC2D34", "tipo_veiculo": "caminhao", "refrigerado": False},
            {"veiculo_id": "VEI-003", "placa": "ABC3D45", "tipo_veiculo": "caminhao", "refrigerado": True},
            {"veiculo_id": "VEI-004", "placa": "ABC4D56", "tipo_veiculo": "van", "refrigerado": False},
            {"veiculo_id": "VEI-005", "placa": "ABC5D67", "tipo_veiculo": "caminhao", "refrigerado": True},
            {"veiculo_id": "VEI-006", "placa": "ABC6D78", "tipo_veiculo": "van", "refrigerado": False},
        ]
        rotas = [
            {"rota_id": "ROTA-001", "regiao_destino": "Sudeste", "tempo_transito_padrao_horas": 8},
            {"rota_id": "ROTA-002", "regiao_destino": "Sul", "tempo_transito_padrao_horas": 18},
            {"rota_id": "ROTA-003", "regiao_destino": "Nordeste", "tempo_transito_padrao_horas": 30},
            {"rota_id": "ROTA-004", "regiao_destino": "Centro-Oeste", "tempo_transito_padrao_horas": 16},
        ]
        return {"tms_veiculos": veiculos, "tms_rotas": rotas}

    def gerar_registros(self, data_referencia: date) -> dict:
        """TMS opera Segunda a Sábado — sem checagem interna adicional de calendário."""
        notas_expedicao = self._ler_notas_expedicao(data_referencia)
        if not notas_expedicao:
            return {}  # ERP ainda não expediu nada nesta data

        mapa_lote_para_cadeia_fria = self._mapear_cadeia_fria_por_lote(data_referencia)

        remessas = self._gerar_remessas(data_referencia, notas_expedicao, mapa_lote_para_cadeia_fria)
        leituras = self._gerar_leituras_temperatura(data_referencia, remessas)
        comprovantes = self._gerar_comprovantes(data_referencia, remessas)

        registros_por_tabela = {"tms_remessas": [r["registro"] for r in remessas]}
        if leituras:
            registros_por_tabela["tms_leituras_temperatura"] = leituras
        registros_por_tabela["tms_comprovantes_entrega"] = comprovantes

        return registros_por_tabela

    def _ler_notas_expedicao(self, data_referencia: date) -> list:
        """Lê erp_notas_expedicao da Landing Zone do ERP, para a mesma data."""
        data_str = data_referencia.strftime("%Y-%m-%d")
        caminho = f"/Volumes/{self.catalog}/landing/{self.volume_landing}/erp/data={data_str}/erp_notas_expedicao.json"
        try:
            df = self.spark.read.json(caminho)
            return [row.asDict() for row in df.select("nota_expedicao_id", "pedido_id", "lote_id").collect()]
        except Exception:
            return []

    def _mapear_cadeia_fria_por_lote(self, data_referencia: date) -> dict:
        """
        Constrói {lote_id: exige_cadeia_fria} a partir de erp_lotes_producao
        do mesmo dia. Lotes não encontrados (limitação conhecida, ver
        cabeçalho do arquivo) não entram no mapa — tratados como False
        por padrão em quem consome o mapa.
        """
        data_str = data_referencia.strftime("%Y-%m-%d")
        caminho = f"/Volumes/{self.catalog}/landing/{self.volume_landing}/erp/data={data_str}/erp_lotes_producao.json"
        try:
            df = self.spark.read.json(caminho)
            linhas = df.select("lote_id", "produto_id").collect()
        except Exception:
            return {}

        catalogo_produtos = SimuladorERP(spark=self.spark, dbutils=self.dbutils).gerar_seed()["erp_produtos"]
        exige_cadeia_fria_por_produto = {p["produto_id"]: p["exige_cadeia_fria"] for p in catalogo_produtos}

        return {
            row.lote_id: exige_cadeia_fria_por_produto.get(row.produto_id, False)
            for row in linhas
        }

    def _gerar_remessas(self, data_referencia: date, notas_expedicao: list, mapa_cadeia_fria: dict) -> list:
        """
        Gera uma remessa por nota de expedição. Aplica a falha cruzada
        intencional: remessa de produto que exige cadeia fria tem 5% de
        chance de ser alocada a veículo sem refrigeração, de propósito.
        """
        veiculos = self.gerar_seed()["tms_veiculos"]
        rotas = self.gerar_seed()["tms_rotas"]
        veiculos_refrigerados = [v for v in veiculos if v["refrigerado"]]
        veiculos_normais = [v for v in veiculos if not v["refrigerado"]]

        remessas = []
        for indice, nota in enumerate(notas_expedicao):
            exige_cadeia_fria = mapa_cadeia_fria.get(nota["lote_id"], False)

            if exige_cadeia_fria:
                if com_probabilidade(0.05) or not veiculos_refrigerados:
                    # falha cruzada intencional: veículo errado para o produto
                    veiculo = random.choice(veiculos_normais)
                else:
                    veiculo = random.choice(veiculos_refrigerados)
            else:
                veiculo = random.choice(veiculos)

            rota = random.choice(rotas)
            remessa_id = f"REM-{data_referencia.strftime('%Y%m%d')}-{indice:04d}"
            # date não soma horas menores que 24 — converte para dias completos,
            # arredondando pra cima (8h de trânsito ainda é entrega no dia seguinte)
            dias_transito = -(-rota["tempo_transito_padrao_horas"] // 24)
            data_entrega_prevista = data_referencia + timedelta(days=dias_transito)

            registro = {
                "remessa_id": remessa_id,
                "nota_expedicao_id": nota["nota_expedicao_id"],
                "pedido_id": nota["pedido_id"],
                "rota_id": rota["rota_id"],
                "veiculo_id": veiculo["veiculo_id"],
                "sla_horas_contratado": formatar_numero_sujo(rota["tempo_transito_padrao_horas"], casas_decimais=0),
                "data_expedicao": formatar_data_suja(data_referencia),
                "data_entrega_prevista": formatar_data_suja(data_entrega_prevista),
            }

            remessas.append({
                "registro": registro,
                "remessa_id": remessa_id,
                "veiculo_refrigerado": veiculo["refrigerado"],
                "data_entrega_prevista": data_entrega_prevista,
            })

        return remessas

    def _gerar_leituras_temperatura(self, data_referencia: date, remessas: list) -> list:
        """
        Gera leituras de temperatura só para remessas em veículo refrigerado
        (independente de o produto exigir ou não — o caminhão refrigerado
        registra temperatura sempre que está em operação).

        5% das leituras saem fora da faixa 2-8°C mesmo em veículo
        refrigerado — segunda causa de violação de cadeia fria (falha de
        equipamento, distinta da falha de alocação de veículo).
        """
        leituras = []
        for r in remessas:
            if not r["veiculo_refrigerado"]:
                continue

            num_leituras = random.randint(3, 6)
            for i in range(num_leituras):
                timestamp = data_referencia.strftime("%Y-%m-%dT") + f"{(6 + i * 3) % 24:02d}:00:00"

                if com_probabilidade(0.05):  # falha de equipamento, de propósito
                    temperatura = random.uniform(9.0, 15.0)
                else:
                    temperatura = random.uniform(2.0, 8.0)

                leituras.append({
                    "leitura_id": f"LEITURA-{r['remessa_id']}-{i:02d}",
                    "remessa_id": r["remessa_id"],
                    "timestamp_leitura": timestamp,
                    "temperatura_celsius": formatar_numero_sujo(temperatura),
                })

        return leituras

    def _gerar_comprovantes(self, data_referencia: date, remessas: list) -> list:
        """
        Gera um comprovante de entrega por remessa. data_entrega_real varia
        em relação à prevista (80% no prazo, 15% atrasada 1-3 dias, 5%
        devolvida) — status_entrega é derivado dessa comparação, não
        sorteado de forma independente (correção: a versão anterior gerava
        data_entrega_real sempre igual à prevista, tornando o cálculo de
        OTIF sempre 100%, e status_entrega sem relação real com a data).
        POD ausente em ~7% dos casos, de propósito.
        """
        registros = []
        for r in remessas:
            pod_confirmado = not com_probabilidade(0.07)

            sorteio = random.random()
            if sorteio < 0.05:
                status = "devolvida"
                data_entrega_real = r["data_entrega_prevista"] + timedelta(days=random.randint(1, 5))
            elif sorteio < 0.20:
                status = "atrasada"
                data_entrega_real = r["data_entrega_prevista"] + timedelta(days=random.randint(1, 3))
            else:
                status = "entregue"
                data_entrega_real = r["data_entrega_prevista"]

            registros.append({
                "comprovante_id": f"COMP-{r['remessa_id']}",
                "remessa_id": r["remessa_id"],
                "data_entrega_real": formatar_data_suja(data_entrega_real),
                "status_entrega": formatar_texto_sujo(status),
                "pod_confirmado": pod_confirmado if pod_confirmado else valor_nulo_variado(),
            })

        return registros