"""
Configuração declarativa dos seeds — usada por promover_seed.py.

Seeds são catálogo fixo, sem sujeira intencional (diferente das 11 tabelas
de evento diário) — só precisam de cast de tipo, sem UDFs de limpeza.
Colunas não listadas em nenhuma categoria permanecem string (a maioria
dos campos de texto de seed já nasce "limpa").
"""

CONFIGURACAO_SEEDS = {
    "erp_produtos": {
        "sistema": "erp",
        "colunas_boolean": ["exige_cadeia_fria"],
        "colunas_integer": ["validade_padrao_dias"],
    },
    "crm_representantes": {
        "sistema": "crm",
    },
    "crm_clientes": {
        "sistema": "crm",
    },
    "tms_veiculos": {
        "sistema": "tms",
        "colunas_boolean": ["refrigerado"],
    },
    "tms_rotas": {
        "sistema": "tms",
        "colunas_integer": ["tempo_transito_padrao_horas"],
    },
    "financeiro_centros_custo": {
        "sistema": "financeiro",
    },
}