"""
Limpeza — funções puras para reverter a sujeira intencional injetada pelos
simuladores (src/simuladores/sujeira_intencional.py), usadas na transformação
Bronze -> Silver.

Cada função é o espelho de uma função de sujeira: onde formatar_data_suja()
gera um dos dois formatos possíveis, parse_data_suja() aceita os dois e
devolve o tipo lógico real. Onde valor_nulo_variado() gera uma das quatro
representações de nulo, as funções aqui tratam todas como None.

Bronze é 100% string (ADR-001) — toda função aqui recebe string (ou None)
e devolve o tipo lógico esperado pela Silver.

Decisão de normalização: limpar_texto() sempre devolve minúsculo — não
tenta preservar a convenção de caixa original (que nem sempre é consistente
entre um código como "CP01" e uma palavra como "aprovado"). O importante
para a Silver é ser determinística, não replicar a forma original.
"""

from datetime import date, datetime


def _eh_nulo_variado(valor) -> bool:
    """Detecta as variações de nulo geradas por valor_nulo_variado(): None, "", "N/A", "NULL" (case-insensitive)."""
    if valor is None:
        return True
    texto = str(valor).strip().lower()
    return texto in ("", "n/a", "null", "none")


def parse_data_suja(valor):
    """
    Converte uma data suja (formatar_data_suja: DD/MM/AAAA ou AAAA-MM-DD)
    para date. Retorna None se o valor for uma variação de nulo.
    """
    if _eh_nulo_variado(valor):
        return None

    texto = str(valor).strip()
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue

    raise ValueError(f"Formato de data não reconhecido: {valor!r}")


def parse_numero_sujo(valor):
    """
    Converte um número no padrão brasileiro (formatar_numero_sujo: milhar
    com ponto, decimal com vírgula) para float. Retorna None se o valor
    for uma variação de nulo.
    """
    if _eh_nulo_variado(valor):
        return None

    texto = str(valor).strip().replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        raise ValueError(f"Número não reconhecido: {valor!r}")


def limpar_texto(valor):
    """
    Padroniza um texto sujo (formatar_texto_sujo: caixa/espaço
    inconsistentes) para minúsculo e sem espaço nas bordas. Retorna None
    se o valor for uma variação de nulo.
    """
    if _eh_nulo_variado(valor):
        return None
    return str(valor).strip().lower()


def parse_nulo_variado(valor):
    """
    Normaliza qualquer variação de nulo (None, "", "N/A", "NULL") para
    None de verdade. Para valores que não são nulo, devolve o próprio
    valor sem alteração — conveniência para campos que não passam por
    nenhuma outra limpeza (ex.: chaves estrangeiras opcionais).
    """
    return None if _eh_nulo_variado(valor) else valor


def parse_booleano_sujo(valor):
    """
    Converte um campo que mistura booleano real com nulo variado (ex.:
    pod_confirmado — True quando confirmado, ou uma das representações de
    valor_nulo_variado() quando não) para bool ou None. Ver Lição 5,
    docs/licoes-aprendidas.md: o Spark lê esse tipo de campo como string,
    e True vira o texto "true", não o booleano Python.
    """
    if _eh_nulo_variado(valor):
        return None
    return str(valor).strip().lower() == "true"