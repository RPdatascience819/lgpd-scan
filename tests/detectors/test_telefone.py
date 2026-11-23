"""Testes do detector de telefone e do registro DETECTORES."""

import random

import pytest

from lgpd_scan._sinteticos import gerar_telefone
from lgpd_scan.detectors import DETECTORES
from lgpd_scan.detectors.base import Tipo
from lgpd_scan.detectors.cnpj import detectar_cnpj
from lgpd_scan.detectors.cpf import detectar_cpf
from lgpd_scan.detectors.email import detectar_email
from lgpd_scan.detectors.telefone import DDDS_VALIDOS, detectar_telefone


def _fatias(texto: str) -> list[str]:
    return [texto[o.inicio : o.fim] for o in detectar_telefone(texto)]


def test_ddds_validos_sao_67() -> None:
    assert len(DDDS_VALIDOS) == 67


def test_ddds_ausentes_da_faixa_11_a_99() -> None:
    ausentes = {f"{n}" for n in range(11, 100)} - DDDS_VALIDOS
    esperados = {"20", "23", "25", "26", "29", "30", "36", "39", "40", "50", "52"}
    esperados |= {"56", "57", "58", "59", "60", "70", "72", "76", "78", "80", "90"}
    assert len(esperados) == 22
    assert ausentes == esperados


@pytest.mark.parametrize(
    ("texto", "formatado"),
    [
        ("(11) 98765-4321", True),
        ("+55 11 98765-4321", True),
        ("11987654321", False),
        ("(21) 3456-7890", True),
        ("11.98765.4321", False),
        ("+5511987654321", False),
        ("11 98765 4321", True),
        ("11-98765-4321", True),
        ("(11)987654321", True),
    ],
)
def test_casa_e_calcula_formatado(texto: str, formatado: bool) -> None:
    [o] = detectar_telefone(texto)
    assert o.tipo is Tipo.TELEFONE
    assert texto[o.inicio : o.fim] == texto
    assert o.formatado is formatado


def test_ddd_inexistente() -> None:
    assert detectar_telefone("(20) 98765-4321") == []
    assert detectar_telefone("20987654321") == []


def test_celular_sem_o_nove_inicial() -> None:
    assert detectar_telefone("(11) 88765-4321") == []


def test_oito_digitos_sem_ddd() -> None:
    assert detectar_telefone("98765432") == []
    assert detectar_telefone("3456-7890") == []


def test_colado_em_outros_digitos() -> None:
    assert detectar_telefone("011987654321") == []
    assert detectar_telefone("119876543210") == []
    assert detectar_telefone("5511987654321") == []  # +55 só com o '+' (limitação)


def test_prefixo_de_texto_nao_e_digito() -> None:
    assert len(detectar_telefone("tel:11987654321")) == 1


def test_digitos_de_outro_alfabeto() -> None:
    # Dígitos arábico-índicos (U+0660..U+0669) montados por code point, para o linter
    # não acusar caractere ambíguo: "(11) 98765-4321" escrito em outro alfabeto.
    arabico = str.maketrans("0123456789", "".join(chr(0x0660 + n) for n in range(10)))
    texto = "(11) 98765-4321".translate(arabico)
    assert texto.isascii() is False
    assert detectar_telefone(texto) == []


def test_parenteses_desbalanceados_nao_entram_na_fatia() -> None:
    assert _fatias("(11 98765-4321") == ["11 98765-4321"]
    # Falso negativo aceito (decisão 4): o ")" solto impede o casamento.
    assert _fatias("11) 98765-4321") == []


def test_fronteira_so_barra_digitos() -> None:
    # Caracterização: a fronteira só barra dígitos, como no CPF. O design §5.3 fala
    # também em letras; a divergência é consciente. Consequência: em
    # "joao11987654321@exemplo.com" as ocorrências de e-mail e de telefone se
    # sobrepõem, e a Task 11 precisa tratar isso. Mudar a fronteira deve falhar aqui.
    assert _fatias("ab11987654321cd") == ["11987654321"]


def test_nove_separado_nao_casa() -> None:
    # Limitação aceita: separador logo depois do 9 inicial.
    assert detectar_telefone("11 9 8765-4321") == []


def test_fatia_sem_pontuacao_em_volta() -> None:
    texto = "ligue (11) 98765-4321."
    assert _fatias(texto) == ["(11) 98765-4321"]
    assert _fatias("[+55 11 98765-4321]") == ["+55 11 98765-4321"]


def test_varios_telefones_em_ordem() -> None:
    texto = "a (11) 98765-4321 e b (21) 3456-7890"
    assert _fatias(texto) == ["(11) 98765-4321", "(21) 3456-7890"]


@pytest.mark.parametrize("celular", [True, False])
@pytest.mark.parametrize("formatado", [True, False])
def test_ida_e_volta_com_o_gerador(celular: bool, formatado: bool) -> None:
    rng = random.Random(7)
    for _ in range(300):
        tel = gerar_telefone(rng, celular=celular, formatado=formatado)
        [o] = detectar_telefone(tel)
        assert tel[o.inicio : o.fim] == tel
        assert o.formatado is formatado
        [o2] = detectar_telefone(f"contato: {tel}; obrigado")
        assert f"contato: {tel}; obrigado"[o2.inicio : o2.fim] == tel


def test_registro_detectores() -> None:
    assert (detectar_cpf, detectar_cnpj, detectar_email, detectar_telefone) == DETECTORES
    for detector in DETECTORES:
        assert callable(detector)
        assert isinstance(detector("sem dados pessoais"), list)
