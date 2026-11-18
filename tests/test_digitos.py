"""Testes dos dígitos verificadores de CPF e CNPJ."""

import random

import pytest

from lgpd_scan.detectors.digitos import dv_cnpj, dv_cpf

_PESOS_CPF_1 = [10, 9, 8, 7, 6, 5, 4, 3, 2]
_PESOS_CPF_2 = [11, 10, 9, 8, 7, 6, 5, 4, 3, 2]
_PESOS_CNPJ_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_PESOS_CNPJ_2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]


def _dv(valores: list[int], pesos: list[int]) -> int:
    soma = sum(v * p for v, p in zip(valores, pesos, strict=True))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def _dv_cpf_referencia(base: str) -> str:
    valores = [int(c) for c in base]
    d1 = _dv(valores, _PESOS_CPF_1)
    d2 = _dv([*valores, d1], _PESOS_CPF_2)
    return f"{d1}{d2}"


def _dv_cnpj_referencia(base: str) -> str:
    valores = [ord(c) - 48 for c in base]
    d1 = _dv(valores, _PESOS_CNPJ_1)
    d2 = _dv([*valores, d1], _PESOS_CNPJ_2)
    return f"{d1}{d2}"


def test_dv_cnpj_exemplo_oficial_da_receita() -> None:
    assert dv_cnpj("12ABC34501DE") == "35"


def test_dv_cpf_bate_com_implementacao_de_referencia() -> None:
    rng = random.Random(0)
    for _ in range(1000):
        base = "".join(rng.choice("0123456789") for _ in range(9))
        assert dv_cpf(base) == _dv_cpf_referencia(base)


def test_dv_cnpj_numerico_bate_com_referencia() -> None:
    rng = random.Random(1)
    for _ in range(1000):
        base = "".join(rng.choice("0123456789") for _ in range(12))
        assert dv_cnpj(base) == _dv_cnpj_referencia(base)


def test_dv_cnpj_alfanumerico_bate_com_referencia() -> None:
    rng = random.Random(4)
    alfabeto = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for _ in range(1000):
        base = "".join(rng.choice(alfabeto) for _ in range(12))
        assert dv_cnpj(base) == _dv_cnpj_referencia(base)


def _bases_cpf(semente: int, quantidade: int) -> list[str]:
    rng = random.Random(semente)
    return ["".join(rng.choice("0123456789") for _ in range(9)) for _ in range(quantidade)]


def _trocas(base: str, posicoes: list[int]) -> list[str]:
    """Todas as bases obtidas trocando um dígito, nas posições dadas, por outro dígito."""
    saida: list[str] = []
    for posicao in posicoes:
        for novo in "0123456789":
            if novo != base[posicao]:
                saida.append(base[:posicao] + novo + base[posicao + 1 :])
    return saida


def test_troca_de_um_digito_fora_das_posicoes_0_e_5_sempre_muda_o_dv_do_cpf() -> None:
    for base in _bases_cpf(2, 300):
        dv = dv_cpf(base)
        for alterada in _trocas(base, [1, 2, 3, 4, 6, 7, 8]):
            assert dv_cpf(alterada) != dv


def test_limitacao_do_cpf_troca_de_um_digito_pode_manter_o_dv() -> None:
    """Limitação conhecida do esquema módulo 11 do CPF: um erro de digitação passa.

    Restos 0 e 1 mapeiam ambos para o dígito 0, e o peso 11 equivale a 0 módulo 11 no
    segundo dígito. Trocar um único dígito (aqui, na posição 0) pode, então, manter os
    dois DVs; um detector não consegue pegar todo erro de digitação.
    """
    for base in _bases_cpf(3, 1000):
        mantem = [a for a in _trocas(base, [0]) if dv_cpf(a) == dv_cpf(base)]
        if mantem:
            assert mantem[0] != base
            assert dv_cpf(mantem[0]) == dv_cpf(base)
            return
    pytest.fail("nenhuma troca na posição 0 manteve o DV em 1000 bases")


@pytest.mark.parametrize("base", ["12345678", "1234567890", "12abc34501de", "12ABC3450-DE"])
def test_bases_invalidas_lancam_value_error(base: str) -> None:
    with pytest.raises(ValueError, match="base"):
        dv_cnpj(base)


@pytest.mark.parametrize("base", ["12345678", "1234567890", "12345678A", "123.456.78"])
def test_bases_de_cpf_invalidas_lancam_value_error(base: str) -> None:
    with pytest.raises(ValueError, match="base"):
        dv_cpf(base)
