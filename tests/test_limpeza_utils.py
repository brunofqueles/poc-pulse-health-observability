"""
Testes de src/transformacao/limpeza_utils.py.

Cada função de limpeza é o espelho de uma função de sujeira
(sujeira_intencional.py) — os testes cobrem os dois formatos gerados por
cada função suja, mais as 4 variações de nulo, garantindo que a reversão
funciona nos casos que o próprio projeto gera de propósito.
"""

import pytest
from datetime import date

from src.transformacao.limpeza_utils import (
    parse_data_suja,
    parse_numero_sujo,
    limpar_texto,
    parse_nulo_variado,
    parse_booleano_sujo,
)


class TestParseDataSuja:
    def test_formato_dd_mm_aaaa(self):
        assert parse_data_suja("29/07/2026") == date(2026, 7, 29)

    def test_formato_aaaa_mm_dd(self):
        assert parse_data_suja("2026-07-29") == date(2026, 7, 29)

    def test_os_dois_formatos_convergem(self):
        assert parse_data_suja("29/07/2026") == parse_data_suja("2026-07-29")

    @pytest.mark.parametrize("valor_nulo", [None, "", "N/A", "NULL", "null"])
    def test_variacoes_de_nulo_viram_none(self, valor_nulo):
        assert parse_data_suja(valor_nulo) is None

    def test_formato_invalido_levanta_erro(self):
        with pytest.raises(ValueError):
            parse_data_suja("29-07-2026-invalido")


class TestParseNumeroSujo:
    def test_padrao_brasileiro_com_milhar(self):
        assert parse_numero_sujo("1.250,50") == 1250.5

    def test_padrao_brasileiro_sem_milhar(self):
        assert parse_numero_sujo("42,00") == 42.0

    @pytest.mark.parametrize("valor_nulo", [None, "", "N/A", "NULL"])
    def test_variacoes_de_nulo_viram_none(self, valor_nulo):
        assert parse_numero_sujo(valor_nulo) is None

    def test_valor_invalido_levanta_erro(self):
        with pytest.raises(ValueError):
            parse_numero_sujo("abc")


class TestLimparTexto:
    @pytest.mark.parametrize(
        "texto_sujo",
        ["APROVADO", "aprovado", "Aprovado", " aprovado ", "aprovado "],
    )
    def test_variacoes_convergem_para_minusculo_sem_espaco(self, texto_sujo):
        assert limpar_texto(texto_sujo) == "aprovado"

    @pytest.mark.parametrize("valor_nulo", [None, "", "N/A", "NULL"])
    def test_variacoes_de_nulo_viram_none(self, valor_nulo):
        assert limpar_texto(valor_nulo) is None


class TestParseNuloVariado:
    @pytest.mark.parametrize("valor_nulo", [None, "", "N/A", "NULL", "null"])
    def test_variacoes_de_nulo_viram_none(self, valor_nulo):
        assert parse_nulo_variado(valor_nulo) is None

    def test_valor_real_passa_intacto(self):
        assert parse_nulo_variado("CLI-0001") == "CLI-0001"


class TestParseBooleanoSujo:
    @pytest.mark.parametrize("valor_true", ["true", "True", "TRUE"])
    def test_variacoes_de_true_viram_booleano(self, valor_true):
        assert parse_booleano_sujo(valor_true) is True

    @pytest.mark.parametrize("valor_nulo", [None, "", "N/A", "NULL"])
    def test_variacoes_de_nulo_viram_none(self, valor_nulo):
        assert parse_booleano_sujo(valor_nulo) is None