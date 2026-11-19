"""Testes do detector de e-mail."""

import random
import time

import pytest

from lgpd_scan._sinteticos import gerar_email
from lgpd_scan.detectors.base import Tipo
from lgpd_scan.detectors.email import detectar_email


def _fatias(texto: str) -> list[str]:
    return [texto[o.inicio : o.fim] for o in detectar_email(texto)]


@pytest.mark.parametrize(
    "email",
    ["joana@exemplo.com", "joana.silva+lgpd@exemplo.com.br", "j_o-a%na@sub.example.org"],
)
def test_casa_emails_validos(email: str) -> None:
    [o] = detectar_email(email)
    assert o.tipo is Tipo.EMAIL
    assert o.formatado is True
    assert email[o.inicio : o.fim] == email


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("escreva para joana@exemplo.com.", "joana@exemplo.com"),
        ("joana@exemplo.com, depois", "joana@exemplo.com"),
        ("<joana@exemplo.com>", "joana@exemplo.com"),
        ("(joana@exemplo.com)", "joana@exemplo.com"),
        ('"joana@exemplo.com"', "joana@exemplo.com"),
    ],
)
def test_pontuacao_em_volta_fica_de_fora(texto: str, esperado: str) -> None:
    assert _fatias(texto) == [esperado]


@pytest.mark.parametrize("texto", ["a@b", "joana@exemplo", "joana@exemplo.c", "@exemplo.com", ""])
def test_rejeita_sem_tld_ou_sem_parte_local(texto: str) -> None:
    assert detectar_email(texto) == []


def test_dois_emails_separados_por_ponto_e_virgula() -> None:
    texto = "joana@exemplo.com;pedro@exemplo.org"
    assert _fatias(texto) == ["joana@exemplo.com", "pedro@exemplo.org"]


def test_letras_unicode_na_parte_local_casam_inteiras() -> None:
    texto = "joão@exemplo.com"
    [o] = detectar_email(texto)
    assert texto[o.inicio : o.fim] == texto


def test_letras_unicode_no_dominio_casam_inteiras() -> None:
    texto = "maria@exemplo.com.br e ana@açaí.com.br"
    assert _fatias(texto) == ["maria@exemplo.com.br", "ana@açaí.com.br"]


@pytest.mark.parametrize("prefixo", ["x", "ã", "9", "_", ".", "%", "+", "-"])
def test_colado_a_caractere_da_parte_local_nunca_da_ocorrencia_parcial(prefixo: str) -> None:
    # Um recorte parcial seria mascarado pela Tarefa 11 deixando o resto visível:
    # a única ocorrência possível é o token inteiro, prefixo incluído.
    texto = prefixo + "oana@exemplo.com"
    assert _fatias(texto) == [texto]
    assert _fatias("ã" + prefixo + "joana@exemplo.com") == ["ã" + prefixo + "joana@exemplo.com"]


def test_sufixo_colado_ao_tld_nao_gera_ocorrencia_parcial() -> None:
    assert detectar_email("joana@exemplo.com1") == []


def test_todo_email_sintetico_e_achado_com_a_fatia_exata() -> None:
    rng = random.Random(7)
    for _ in range(200):
        email = gerar_email(rng)
        texto = f"contato: {email}, obrigado"
        assert _fatias(texto) == [email]


@pytest.mark.parametrize(
    "texto",
    ["a" * 200_000, "a" * 200_000 + "@", "a@" + "b." * 50_000, "a@" + "b" * 200_000],
)
def test_tempo_linear_em_celulas_grandes(texto: str) -> None:
    inicio = time.perf_counter()
    assert detectar_email(texto) == []
    assert time.perf_counter() - inicio < 1.0
