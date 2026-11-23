"""Testes do mascaramento. Os valores são sintéticos ou de exemplo, nunca de pessoas reais."""

import random

import pytest

from lgpd_scan._sinteticos import gerar_cnpj, gerar_cpf, gerar_email, gerar_telefone
from lgpd_scan.detectors.base import Tipo
from lgpd_scan.mascara import mascarar


@pytest.mark.parametrize(
    ("trecho", "tipo", "esperado"),
    [
        ("674.172.244-07", Tipo.CPF, "***.172.244-**"),
        ("67417224407", Tipo.CPF, "***172244**"),
        ("12.ABC.345/01DE-35", Tipo.CNPJ, "12.***.***/01DE-**"),
        ("joana@exemplo.com", Tipo.EMAIL, "j****@exemplo.com"),
        ("(11) 98765-4321", Tipo.TELEFONE, "(11) 9****-4321"),
        ("11987654321", Tipo.TELEFONE, "119****4321"),
        ("+55 11 98765-4321", Tipo.TELEFONE, "+55 11 9****-4321"),
        ("(21) 3456-7890", Tipo.TELEFONE, "(21) 3***-7890"),
        ("a@exemplo.com", Tipo.EMAIL, "*@exemplo.com"),
    ],
)
def test_exemplos_fixos(trecho: str, tipo: Tipo, esperado: str) -> None:
    assert mascarar(trecho, tipo) == esperado


def test_email_com_um_so_alfanumerico_na_parte_local_nao_mostra_nada() -> None:
    assert mascarar("a.@exemplo.com", Tipo.EMAIL) == "*.@exemplo.com"


def _sinteticos(rng: random.Random) -> list[tuple[str, Tipo]]:
    return [
        (gerar_cpf(rng, formatado=True), Tipo.CPF),
        (gerar_cpf(rng, formatado=False), Tipo.CPF),
        (gerar_cnpj(rng, alfanumerico=False, formatado=True), Tipo.CNPJ),
        (gerar_cnpj(rng, alfanumerico=True, formatado=True), Tipo.CNPJ),
        (gerar_cnpj(rng, alfanumerico=True, formatado=False), Tipo.CNPJ),
        (gerar_telefone(rng, celular=True, formatado=True), Tipo.TELEFONE),
        (gerar_telefone(rng, celular=True, formatado=False), Tipo.TELEFONE),
        (gerar_telefone(rng, celular=False, formatado=True), Tipo.TELEFONE),
        (gerar_telefone(rng, celular=False, formatado=False), Tipo.TELEFONE),
        (gerar_email(rng), Tipo.EMAIL),
    ]


def test_propriedades_com_dados_sinteticos() -> None:
    rng = random.Random(9)
    conferidos = 0
    for _ in range(300):
        for trecho, tipo in _sinteticos(rng):
            mascarado = mascarar(trecho, tipo)
            assert len(mascarado) == len(trecho)
            assert mascarado != trecho
            for original, novo in zip(trecho, mascarado, strict=True):
                if original.isalnum():
                    assert novo in (original, "*")
                else:
                    assert novo == original
            conferidos += 1
    assert conferidos == 3000
