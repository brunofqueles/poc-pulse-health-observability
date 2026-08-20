"""
Testes de src/simuladores/sujeira_intencional.py.

Funções com aleatoriedade (formatar_data_suja, formatar_numero_sujo,
formatar_texto_sujo, valor_nulo_variado, com_probabilidade) são testadas
por propriedade (o resultado pertence a um conjunto esperado, ou obedece
uma regra), não por valor exato — natureza intencionalmente não
determinística dessas funções.
"""

from datetime import date

from src.simuladores.sujeira_intencional import (
    formatar_data_suja,
    formatar_numero_sujo,
    formatar_texto_sujo,
    remover_acentos,
    valor_nulo_variado,
    com_probabilidade,
)


class TestFormatarDataSuja:
    def test_resultado_e_um_dos_dois_formatos_esperados(self):
        data = date(2026, 7, 29)
        for _ in range(20):
            resultado = formatar_data_suja(data)
            assert resultado in ("29/07/2026", "2026-07-29")


class TestFormatarNumeroSujo:
    def test_usa_virgula_como_separador_decimal(self):
        assert formatar_numero_sujo(1250.5) == "1.250,50"

    def test_numero_pequeno_sem_separador_de_milhar(self):
        assert formatar_numero_sujo(42.0) == "42,00"

    def test_casas_decimais_configuravel(self):
        assert formatar_numero_sujo(1250, casas_decimais=0) == "1.250"


class TestFormatarTextoSujo:
    def test_resultado_pertence_ao_conjunto_de_variacoes_esperadas(self):
        texto = "aprovado"
        variacoes_esperadas = {
            texto.upper(), texto.lower(), texto.title(),
            f" {texto} ", f"{texto} ",
        }
        for _ in range(30):
            resultado = formatar_texto_sujo(texto)
            assert resultado in variacoes_esperadas


class TestRemoverAcentos:
    def test_remove_acentuacao_de_palavra_com_cedilha_e_til(self):
        assert remover_acentos("Fabricação") == "Fabricacao"

    def test_texto_sem_acento_permanece_igual(self):
        assert remover_acentos("teste") == "teste"


class TestValorNuloVariado:
    def test_resultado_pertence_ao_conjunto_de_nulos_esperados(self):
        nulos_esperados = {None, "", "N/A", "NULL"}
        for _ in range(30):
            assert valor_nulo_variado() in nulos_esperados


class TestComProbabilidade:
    def test_probabilidade_zero_nunca_e_verdadeiro(self):
        assert all(not com_probabilidade(0.0) for _ in range(50))

    def test_probabilidade_um_sempre_e_verdadeiro(self):
        assert all(com_probabilidade(1.0) for _ in range(50))