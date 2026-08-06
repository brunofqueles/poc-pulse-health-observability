"""
Sujeira intencional — funções puras para gerar dado malformado repetível.

Usado pelos simuladores (ERP, CRM, TMS, Financeiro) para transformar um valor
"limpo" (gerado pelo dbldatagen) em uma representação suja de propósito, do
jeito que um sistema de origem real entregaria — sem tratamento nenhum.

Cada campo sujo testa um caso específico de tratamento na Silver (ver
docs/schemas/), não é ruído aleatório sem controle: os padrões de sujeira
são fixos e conhecidos, só a escolha entre eles por chamada é aleatória.

Todas as funções recebem um valor já gerado e retornam string — Bronze é
100% string, sem tratamento algum (ADR-001, architecture.md).
"""

import random
import unicodedata
from datetime import date


def formatar_data_suja(data: date) -> str:
    """
    Formata uma data em um dos dois formatos inconsistentes usados nos
    sistemas de origem simulados: DD/MM/AAAA ou AAAA-MM-DD.
    """
    formato = random.choice(["%d/%m/%Y", "%Y-%m-%d"])
    return data.strftime(formato)


def formatar_numero_sujo(valor: float, casas_decimais: int = 2) -> str:
    """
    Formata um número no padrão brasileiro (milhar com ponto, decimal com
    vírgula) — ex.: 1250.5 -> "1.250,50". Sujeira típica de exportação de
    sistema legado, que a Silver precisa saber converter de volta.
    """
    texto = f"{valor:,.{casas_decimais}f}"
    texto = texto.replace(",", "TEMP").replace(".", ",").replace("TEMP", ".")
    return texto


def formatar_texto_sujo(texto: str) -> str:
    """
    Aplica variação de caixa e espaçamento inconsistente a um texto — ex.:
    "aprovado" -> " Aprovado ", "REPROVADO", "reprovado". Simula entrada
    manual ou exportação sem padronização.
    """
    variacoes = [
        texto.upper(),
        texto.lower(),
        texto.title(),
        f" {texto} ",
        f"{texto} ",
    ]
    return random.choice(variacoes)


def remover_acentos(texto: str) -> str:
    """Remove acentuação de um texto, simulando exportação sem encoding correto."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def valor_nulo_variado():
    """
    Retorna uma representação de nulo escolhida entre as formas inconsistentes
    encontradas em sistemas de origem reais: None (ausência real), string
    vazia, "N/A" ou "NULL" como texto.
    """
    return random.choice([None, "", "N/A", "NULL"])


def com_probabilidade(probabilidade: float) -> bool:
    """
    Decide, com a probabilidade informada (0.0 a 1.0), se uma condição de
    negócio/sujeira deve ser aplicada a este registro. Usado para controlar
    taxas como "10% dos lotes reprovados" ou "5% dos emails malformados".
    """
    return random.random() < probabilidade