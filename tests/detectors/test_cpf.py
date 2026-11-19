"""Testes do detector de CPF."""

import random

from lgpd_scan._sinteticos import gerar_cpf
from lgpd_scan.detectors.base import Tipo
from lgpd_scan.detectors.cpf import detectar_cpf

# CPF gerado pelo algoritmo (não copiado de pessoa real).
_CPF = "674.172.244-07"
_CPF_SEM_MASCARA = "67417224407"


def _com_dv_errado(cpf: str) -> str:
    """Troca o último dígito (verificador) por outro, mantendo o formato."""
    ultimo = cpf[-1]
    return cpf[:-1] + str((int(ultimo) + 1) % 10)


def test_formatado_valido() -> None:
    cpf = gerar_cpf(random.Random(1), formatado=True)
    [o] = detectar_cpf(cpf)
    assert o.tipo is Tipo.CPF
    assert o.formatado is True
    assert cpf[o.inicio : o.fim] == cpf


def test_onze_digitos_sem_mascara() -> None:
    cpf = gerar_cpf(random.Random(2), formatado=False)
    [o] = detectar_cpf(cpf)
    assert o.formatado is False
    assert cpf[o.inicio : o.fim] == cpf


def test_mascara_parcial_e_valida_nao_formatada() -> None:
    texto = "674172244-07"
    [o] = detectar_cpf(texto)
    assert o.formatado is False
    assert texto[o.inicio : o.fim] == texto


def test_dv_errado() -> None:
    assert detectar_cpf(_com_dv_errado(_CPF)) == []
    assert detectar_cpf(_com_dv_errado(_CPF_SEM_MASCARA)) == []


def test_digitos_todos_iguais() -> None:
    assert detectar_cpf("111.111.111-11") == []
    assert detectar_cpf("00000000000") == []


def test_embutido_em_texto() -> None:
    texto = f"cliente {_CPF} ligou"
    [o] = detectar_cpf(texto)
    assert texto[o.inicio : o.fim] == _CPF
    assert o.inicio == len("cliente ")
    assert o.formatado is True


def test_colado_em_digitos() -> None:
    assert detectar_cpf("9" + _CPF_SEM_MASCARA + "9") == []
    assert detectar_cpf("9" + _CPF_SEM_MASCARA) == []
    assert detectar_cpf(_CPF_SEM_MASCARA + "9") == []


def test_dois_cpfs_em_ordem() -> None:
    a = gerar_cpf(random.Random(3), formatado=True)
    b = gerar_cpf(random.Random(4), formatado=False)
    texto = f"{a} e {b}"
    ocs = detectar_cpf(texto)
    assert [texto[o.inicio : o.fim] for o in ocs] == [a, b]
    assert [o.formatado for o in ocs] == [True, False]


def test_texto_vazio_ou_sem_cpf() -> None:
    assert detectar_cpf("") == []
    assert detectar_cpf("sem documento aqui") == []


def test_digitos_nao_ascii_sao_ignorados() -> None:
    arabes = "".join(chr(0x660 + i) for i in range(1, 10)) + "12"
    assert detectar_cpf(arabes) == []
