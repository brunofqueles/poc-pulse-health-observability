"""
Simulador Distribution — separado do ERP (5º pipeline, demonstração de escala).

Antes desta separação, Distribution vivia dentro de SimuladorERP (Opção A,
escolhida no início do projeto por simplicidade). Esta é a evolução para
Opção B: Distribution como pipeline próprio, com seu próprio calendário e
responsabilidade — prova de que o desenho config-driven do projeto escala
sem precisar reescrever a arquitetura.

Tabelas: erp_posicoes_estoque, erp_notas_expedicao — nomes mantidos
propositalmente (não viraram distribution_*), para não exigir mudança em
Gold, observability ou schemas que já referenciam essas tabelas pelo nome.
Só a origem (pasta na Landing Zone) muda: distribution/, não mais erp/.

Dependência de execução (estende ADR-011): lê crm_pedidos e
erp_lotes_producao, ambos da mesma data_referencia, via Landing Zone —
cross-read entre arquivos, não mais compartilhamento em memória como
quando Distribution vivia dentro da mesma classe do ERP.

dias_operacionais: Segunda a Sábado.

Schema de referência: docs/schemas/erp.md (seção Distribution).
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


class SimuladorDistribution(SimuladorDeSistema):
    """Simulador da Distribution (separado do ERP no 5º pipeline)."""

    @property
    def nome_sistema(self) -> str:
        return "distribution"

    @property
    def dias_operacionais(self) -> set:
        # segunda=0 ... sábado=5
        return {0, 1, 2, 3, 4, 5}

    def gerar_registros(self, data_referencia: date) -> dict:
        """Distribution opera Segunda a Sábado — sem checagem interna adicional de calendário."""
        registros_por_tabela = {
            "erp_posicoes_estoque": self._gerar_posicoes_estoque(data_referencia),
        }

        notas = self._gerar_notas_expedicao(data_referencia)
        if notas:
            registros_por_tabela["erp_notas_expedicao"] = notas

        return registros_por_tabela

    def _gerar_posicoes_estoque(self, data_referencia: date) -> list:
        """
        Gera as posições de estoque do dia.

        lote_id é referenciado de forma sintética — mesma limitação
        conhecida já documentada quando esta lógica vivia no ERP (sem
        memória entre dias, ADR-010).
        """
        num_posicoes = random.randint(30, 60)

        registros = []
        for indice in range(num_posicoes):
            centro = random.choice(["CD01", "CD02"])
            dia_lote = data_referencia - timedelta(days=random.randint(0, 5))
            lote_id_referenciado = f"LOTE-{dia_lote.strftime('%Y%m%d')}-{random.randint(0, 79):04d}"

            quantidade = random.randint(10, 500)
            if com_probabilidade(0.05):  # 5% de estoque negativo, de propósito
                quantidade = -quantidade

            registros.append({
                "posicao_id": f"POS-{data_referencia.strftime('%Y%m%d')}-{indice:04d}",
                "lote_id": lote_id_referenciado,
                "centro_distribuicao_id": formatar_texto_sujo(centro),
                "quantidade": formatar_numero_sujo(quantidade, casas_decimais=0),
                "data_posicao": formatar_data_suja(data_referencia),
            })

        return registros

    def _ler_lotes_aprovados_do_dia(self, data_referencia: date) -> list:
        """
        Lê erp_lotes_producao (Manufacturing) da mesma data na Landing Zone,
        retornando os lotes aprovados — cross-read entre pipelines (ADR-011,
        estendido). Se Manufacturing não operou nesse dia (ex.: sábado),
        retorna lista vazia — mesma limitação já documentada.
        """
        data_str = data_referencia.strftime("%Y-%m-%d")
        caminho = f"/Volumes/{self.catalog}/landing/{self.volume_landing}/erp/data={data_str}/erp_lotes_producao.json"

        try:
            df = self.spark.read.json(caminho)
            linhas = df.select("lote_id", "produto_id", "status_qc").collect()
        except Exception:
            return []

        # status_qc chega sujo (caixa/espaço variando) — "aprovado" nunca é
        # substring de "reprovado", então o teste funciona mesmo sem limpar
        return [
            {"lote_id": r.lote_id, "produto_id": r.produto_id}
            for r in linhas
            if "aprovado" in str(r.status_qc).strip().lower()
        ]

    def _gerar_notas_expedicao(self, data_referencia: date) -> list:
        """
        Gera notas de expedição, referenciando pedido_id real (lido da
        Landing Zone do CRM) e lote_id real quando Manufacturing produziu
        no mesmo dia. Em dias sem produção nova, cai para referência
        sintética — mesma limitação conhecida já documentada.
        """
        data_str = data_referencia.strftime("%Y-%m-%d")
        caminho_pedidos_crm = (
            f"/Volumes/{self.catalog}/landing/{self.volume_landing}/crm/data={data_str}/crm_pedidos.json"
        )

        try:
            df_pedidos = self.spark.read.json(caminho_pedidos_crm)
            pedidos_disponiveis = [row.pedido_id for row in df_pedidos.select("pedido_id").collect()]
        except Exception:
            pedidos_disponiveis = []

        if not pedidos_disponiveis:
            return []

        lotes_aprovados_hoje = self._ler_lotes_aprovados_do_dia(data_referencia)

        num_notas = min(len(pedidos_disponiveis), random.randint(150, 300))
        pedidos_selecionados = random.sample(pedidos_disponiveis, num_notas)

        registros = []
        for indice, pedido_id in enumerate(pedidos_selecionados):
            if lotes_aprovados_hoje:
                lote_id = random.choice(lotes_aprovados_hoje)["lote_id"]
            else:
                dia_lote = data_referencia - timedelta(days=random.randint(0, 5))
                lote_id = f"LOTE-{dia_lote.strftime('%Y%m%d')}-{random.randint(0, 79):04d}"

            registros.append({
                "nota_expedicao_id": f"NOTAEXP-{data_referencia.strftime('%Y%m%d')}-{indice:04d}",
                "pedido_id": pedido_id,
                "lote_id": lote_id,
                "centro_distribuicao_id": formatar_texto_sujo(random.choice(["CD01", "CD02"])),
                "quantidade_expedida": formatar_numero_sujo(random.randint(1, 50), casas_decimais=0),
                "data_expedicao": formatar_data_suja(data_referencia),
            })

        return registros