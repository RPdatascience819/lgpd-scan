"""Testes do gerador de dados sintéticos."""

import random
import re

from lgpd_scan import _sinteticos
from lgpd_scan._sinteticos import gerar_cnpj, gerar_cpf, gerar_email, gerar_telefone
from lgpd_scan.detectors.digitos import dv_cnpj, dv_cpf
from lgpd_scan.detectors.telefone import DDDS_VALIDOS


def test_ddds_em_ordem_estavel() -> None:
    # O teste de semente roda num processo só e não pega a ordem do frozenset
    # variando com PYTHONHASHSEED; a tupla ordenada garante a reprodutibilidade.
    assert tuple(sorted(DDDS_VALIDOS)) == _sinteticos._DDDS


def _sequencia(semente: int) -> list[str]:
    rng = random.Random(semente)
    saida: list[str] = []
    for _ in range(20):
        saida.append(gerar_cpf(rng, formatado=True))
        saida.append(gerar_cnpj(rng, alfanumerico=True, formatado=False))
        saida.append(gerar_telefone(rng, celular=True, formatado=True))
        saida.append(gerar_email(rng))
    return saida


def test_mesma_semente_gera_a_mesma_sequencia() -> None:
    assert _sequencia(42) == _sequencia(42)
    assert _sequencia(42) != _sequencia(43)


def test_cpf_formatado_casa_o_padrao() -> None:
    rng = random.Random(0)
    for _ in range(100):
        assert re.fullmatch(r"\d{3}\.\d{3}\.\d{3}-\d{2}", gerar_cpf(rng, formatado=True))


def test_cpf_gerado_tem_dv_valido_e_nao_repete_digitos() -> None:
    rng = random.Random(0)
    for _ in range(500):
        cpf = gerar_cpf(rng, formatado=False)
        assert re.fullmatch(r"\d{11}", cpf)
        assert len(set(cpf)) > 1
        assert cpf[9:] == dv_cpf(cpf[:9])


def test_cnpj_alfanumerico_tem_letra_na_base_e_dv_valido() -> None:
    rng = random.Random(0)
    for _ in range(200):
        cnpj = gerar_cnpj(rng, alfanumerico=True, formatado=False)
        assert len(cnpj) == 14
        assert any(c.isalpha() for c in cnpj[:12])
        assert cnpj[12:] == dv_cnpj(cnpj[:12])


def test_cnpj_numerico_formatado() -> None:
    rng = random.Random(0)
    for _ in range(200):
        cnpj = gerar_cnpj(rng, alfanumerico=False, formatado=True)
        assert re.fullmatch(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", cnpj)
        puro = re.sub(r"\D", "", cnpj)
        assert len(set(puro)) > 1
        assert puro[12:] == dv_cnpj(puro[:12])


def test_cnpj_alfanumerico_formatado_casa_o_padrao() -> None:
    rng = random.Random(0)
    padrao = r"[0-9A-Z]{2}\.[0-9A-Z]{3}\.[0-9A-Z]{3}/[0-9A-Z]{4}-\d{2}"
    for _ in range(100):
        assert re.fullmatch(padrao, gerar_cnpj(rng, alfanumerico=True, formatado=True))


def test_telefone_celular_e_fixo() -> None:
    rng = random.Random(0)
    for _ in range(100):
        cel_fmt = gerar_telefone(rng, celular=True, formatado=True)
        cel_puro = gerar_telefone(rng, celular=True, formatado=False)
        fixo_fmt = gerar_telefone(rng, celular=False, formatado=True)
        fixo_puro = gerar_telefone(rng, celular=False, formatado=False)
        assert re.fullmatch(r"\(\d{2}\) 9\d{4}-\d{4}", cel_fmt)
        assert re.fullmatch(r"\d{2}9\d{8}", cel_puro)
        assert re.fullmatch(r"\(\d{2}\) [2-5]\d{3}-\d{4}", fixo_fmt)
        assert re.fullmatch(r"\d{2}[2-5]\d{7}", fixo_puro)


def test_email_usa_so_dominios_reservados() -> None:
    rng = random.Random(0)
    dominios = {gerar_email(rng).split("@")[1] for _ in range(200)}
    assert dominios <= {"exemplo.com", "exemplo.org", "example.com"}
