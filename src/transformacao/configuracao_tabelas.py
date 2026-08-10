"""
Configuração declarativa de limpeza por tabela — usada por
transformar_bronze_para_silver.py.

Traduz em código o que docs/schemas/*.md já documenta na coluna "Tipo
lógico Silver". Colunas de chave estrangeira (FK) não entram em nenhuma
categoria de limpeza — nascem limpas, referenciam outra tabela.

Categorias disponíveis:
- chave_negocio: coluna usada no MERGE INTO (obrigatória, verdadeiramente única)
- colunas_data: parse_data_suja (dois formatos + nulo variado)
- colunas_numero_inteiro / colunas_numero_float: parse_numero_sujo
- colunas_texto: limpar_texto (normaliza caixa/espaço)
- colunas_fk_nulavel: parse_nulo_variado (só normaliza nulo)
- colunas_booleano: parse_booleano_sujo (True/nulo variado -> bool/None)
- colunas_timestamp: cast nativo (formato fixo, sem sujeira intencional)
"""

CONFIGURACAO_TABELAS = {
    # --- ERP ---
    "erp_lotes_producao": {
        "chave_negocio": "lote_id",
        "colunas_data": ["data_fabricacao", "data_validade", "data_liberacao"],
        "colunas_numero_inteiro": ["quantidade_produzida"],
        "colunas_texto": ["centro_producao_id", "status_qc"],
    },
    "erp_posicoes_estoque": {
        "chave_negocio": "posicao_id",
        "colunas_data": ["data_posicao"],
        "colunas_numero_inteiro": ["quantidade"],
        "colunas_texto": ["centro_distribuicao_id"],
    },
    "erp_notas_expedicao": {
        "chave_negocio": "nota_expedicao_id",
        "colunas_data": ["data_expedicao"],
        "colunas_numero_inteiro": ["quantidade_expedida"],
        "colunas_texto": ["centro_distribuicao_id"],
    },
    # --- CRM ---
    "crm_pedidos": {
        "chave_negocio": "pedido_id",
        "colunas_data": ["data_pedido"],
        "colunas_numero_float": ["valor_total"],
        "colunas_texto": ["status_pedido"],
    },
    "crm_itens_pedido": {
        "chave_negocio": "item_pedido_id",
        "colunas_numero_inteiro": ["quantidade"],
        "colunas_numero_float": ["preco_unitario"],
    },
    "crm_atendimento": {
        "chave_negocio": "interacao_id",
        "colunas_data": ["data_interacao"],
        "colunas_texto": ["tipo_interacao"],
        "colunas_fk_nulavel": ["lote_id"],
    },
    # --- TMS ---
    "tms_remessas": {
        "chave_negocio": "remessa_id",
        "colunas_data": ["data_expedicao", "data_entrega_prevista"],
        "colunas_numero_inteiro": ["sla_horas_contratado"],
    },
    "tms_leituras_temperatura": {
        "chave_negocio": "leitura_id",
        "colunas_numero_float": ["temperatura_celsius"],
        "colunas_timestamp": ["timestamp_leitura"],
    },
    "tms_comprovantes_entrega": {
        "chave_negocio": "comprovante_id",
        "colunas_data": ["data_entrega_real"],
        "colunas_texto": ["status_entrega"],
        "colunas_booleano": ["pod_confirmado"],
    },
    # --- Financeiro ---
    "financeiro_faturas": {
        "chave_negocio": "fatura_id",
        "colunas_data": ["data_faturamento"],
        "colunas_numero_float": ["valor_faturado"],
        "colunas_fk_nulavel": ["centro_custo_id"],
    },
    "financeiro_contas_receber": {
        "chave_negocio": "conta_receber_id",
        "colunas_data": ["data_vencimento", "data_recebimento"],
        "colunas_texto": ["status_conta"],
    },
}