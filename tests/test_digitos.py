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
    valores = [int(c) for c in base]
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


def test_alterar_um_digito_invalida_o_cpf() -> None:
    rng = random.Random(2)
    for _ in range(200):
        base = "".join(rng.choice("0123456789") for _ in range(9))
        dv = dv_cpf(base)
        posicao = rng.randrange(9)
        novo = str((int(base[posicao]) + rng.randrange(1, 10)) % 10)
        alterada = base[:posicao] + novo + base[posicao + 1 :]
        assert alterada != base
        assert dv_cpf(alterada) != dv


@pytest.mark.parametrize("base", ["12345678", "1234567890", "12abc34501de", "12ABC3450-DE"])
def test_bases_invalidas_lancam_value_error(base: str) -> None:
    with pytest.raises(ValueError, match="base"):
        dv_cnpj(base)


@pytest.mark.parametrize("base", ["12345678", "1234567890", "12345678A", "123.456.78"])
def test_bases_de_cpf_invalidas_lancam_value_error(base: str) -> None:
    with pytest.raises(ValueError, match="base"):
        dv_cpf(base)
