"""Testes do detector de CNPJ (numérico e alfanumérico)."""

import random

from lgpd_scan._sinteticos import gerar_cnpj, gerar_cpf
from lgpd_scan.detectors.base import Tipo
from lgpd_scan.detectors.cnpj import detectar_cnpj
from lgpd_scan.detectors.digitos import dv_cnpj

# Exemplo oficial da IN RFB nº 2.229/2024.
_OFICIAL = "12.ABC.345/01DE-35"
_OFICIAL_SEM_MASCARA = "12ABC34501DE35"


def _com_dv_errado(cnpj: str) -> str:
    """Troca o último dígito (verificador) por outro, mantendo o formato."""
    return cnpj[:-1] + str((int(cnpj[-1]) + 1) % 10)


def test_exemplo_oficial_formatado() -> None:
    [o] = detectar_cnpj(_OFICIAL)
    assert o.tipo is Tipo.CNPJ
    assert o.formatado is True
    assert _OFICIAL[o.inicio : o.fim] == _OFICIAL


def test_alfanumerico_sem_mascara() -> None:
    [o] = detectar_cnpj(_OFICIAL_SEM_MASCARA)
    assert o.formatado is False
    assert _OFICIAL_SEM_MASCARA[o.inicio : o.fim] == _OFICIAL_SEM_MASCARA


def test_minusculas_nao_casam() -> None:
    assert detectar_cnpj("12.abc.345/01de-35") == []
    assert detectar_cnpj("12abc34501de35") == []


def test_dv_errado() -> None:
    assert detectar_cnpj(_com_dv_errado(_OFICIAL)) == []
    assert detectar_cnpj(_com_dv_errado(_OFICIAL_SEM_MASCARA)) == []


def test_base_de_caracteres_iguais() -> None:
    assert detectar_cnpj("A" * 12 + dv_cnpj("A" * 12)) == []
    assert detectar_cnpj("0" * 14) == []


def test_numerico_gerado_formatado_e_nao() -> None:
    for semente, formatado in ((1, True), (2, False)):
        cnpj = gerar_cnpj(random.Random(semente), alfanumerico=False, formatado=formatado)
        [o] = detectar_cnpj(cnpj)
        assert o.formatado is formatado
        assert cnpj[o.inicio : o.fim] == cnpj


def test_alfanumerico_gerado_formatado_e_nao() -> None:
    for semente, formatado in ((3, True), (4, False)):
        cnpj = gerar_cnpj(random.Random(semente), alfanumerico=True, formatado=formatado)
        [o] = detectar_cnpj(cnpj)
        assert o.formatado is formatado
        assert cnpj[o.inicio : o.fim] == cnpj


def test_mascara_parcial_e_valida_nao_formatada() -> None:
    cnpj = gerar_cnpj(random.Random(5), alfanumerico=True, formatado=True)
    parcial = cnpj.replace("/", "")
    [o] = detectar_cnpj(parcial)
    assert o.formatado is False
    assert parcial[o.inicio : o.fim] == parcial


def test_colado_em_letras_ou_digitos() -> None:
    assert detectar_cnpj("X" + _OFICIAL_SEM_MASCARA) == []
    assert detectar_cnpj(_OFICIAL_SEM_MASCARA + "X") == []
    assert detectar_cnpj("9" + _OFICIAL_SEM_MASCARA) == []
    assert detectar_cnpj(_OFICIAL_SEM_MASCARA + "9") == []
    assert detectar_cnpj("x" + _OFICIAL_SEM_MASCARA) == []


def test_cpf_valido_nao_casa_como_cnpj() -> None:
    assert detectar_cnpj(gerar_cpf(random.Random(6), formatado=False)) == []
    assert detectar_cnpj(gerar_cpf(random.Random(6), formatado=True)) == []


def test_embutido_em_texto_e_dois_em_ordem() -> None:
    a = gerar_cnpj(random.Random(7), alfanumerico=True, formatado=True)
    b = gerar_cnpj(random.Random(8), alfanumerico=False, formatado=False)
    texto = f"empresa {a} e {b}."
    ocs = detectar_cnpj(texto)
    assert [texto[o.inicio : o.fim] for o in ocs] == [a, b]
    assert ocs[0].inicio == len("empresa ")
    assert [o.formatado for o in ocs] == [True, False]


def test_texto_vazio_ou_sem_cnpj() -> None:
    assert detectar_cnpj("") == []
    assert detectar_cnpj("sem documento aqui") == []


def test_digitos_nao_ascii_nao_levantam_excecao() -> None:
    arabes = "".join(chr(0x660 + i) for i in range(1, 10)) + "12345"
    assert detectar_cnpj(arabes) == []
    assert detectar_cnpj("12.ABC.345/01DE-" + chr(0x663) + chr(0x665)) == []
