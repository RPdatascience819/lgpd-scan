"""Privacidade como propriedade testada (design 5.7): nenhuma saída traz valor completo."""

import ast
import random
import re
from pathlib import Path

import pytest

import lgpd_scan
from lgpd_scan._sinteticos import gerar_cnpj, gerar_cpf, gerar_email, gerar_telefone
from lgpd_scan.cli import main

PROIBIDOS = frozenset({"socket", "http", "urllib", "requests"})
RAIZ_SRC = Path(lgpd_scan.__file__).parent


def _valores(rng: random.Random) -> list[str]:
    """Os valores originais gravados no CSV, nas formas formatada e não formatada."""
    cpf_f = gerar_cpf(rng, formatado=True)
    cnpj_f = gerar_cnpj(rng, alfanumerico=False, formatado=True)
    tel_f = gerar_telefone(rng, celular=True, formatado=True)
    return [
        cpf_f,
        cpf_f.replace(".", "").replace("-", ""),
        cnpj_f,
        cnpj_f.replace(".", "").replace("/", "").replace("-", ""),
        gerar_email(rng),
        tel_f,
        re.sub(r"\D", "", tel_f),
        gerar_telefone(rng, celular=False, formatado=False),
    ]


def _formas_proibidas(valores: list[str]) -> set[str]:
    proibidas = set(valores)
    proibidas.update(re.sub(r"\D", "", v) for v in valores if len(re.sub(r"\D", "", v)) >= 8)
    return proibidas


@pytest.fixture
def csv_sintetico(tmp_path: Path) -> tuple[Path, set[str]]:
    rng = random.Random(77)
    cpf, cpf_puro, cnpj, cnpj_puro, email, tel, tel_puro, fixo = _valores(rng)
    linhas = [
        f"{cpf},{cnpj},{email},{tel}",
        f"{cpf_puro},{cnpj_puro},{email},{tel_puro}",
        f"{cpf},{cnpj},{email},{fixo}",
    ]
    arquivo = tmp_path / "pessoas.csv"
    arquivo.write_text("cpf,cnpj,email,telefone\n" + "\n".join(linhas) + "\n", encoding="utf-8")
    return arquivo, _formas_proibidas([cpf, cpf_puro, cnpj, cnpj_puro, email, tel, tel_puro, fixo])


def _sem_vazamento(texto: str, proibidas: set[str]) -> None:
    vazados = [v for v in proibidas if v in texto]
    assert not vazados, f"{len(vazados)} valor(es) original(is) apareceram na saída"


@pytest.mark.parametrize("formato", ["table", "json"])
def test_stdout_e_stderr_nao_trazem_valor_original(
    csv_sintetico: tuple[Path, set[str]], capsys: pytest.CaptureFixture[str], formato: str
) -> None:
    arquivo, proibidas = csv_sintetico
    assert main(["scan", str(arquivo), "--format", formato]) == 1
    captura = capsys.readouterr()
    assert captura.out  # há relatório: o teste não passa por saída vazia
    _sem_vazamento(captura.out, proibidas)
    _sem_vazamento(captura.err, proibidas)


@pytest.mark.parametrize("formato", ["table", "json"])
def test_arquivo_de_output_nao_traz_valor_original(
    csv_sintetico: tuple[Path, set[str]],
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    formato: str,
) -> None:
    arquivo, proibidas = csv_sintetico
    destino = tmp_path / f"relatorio.{formato}"
    assert main(["scan", str(arquivo), "--format", formato, "--output", str(destino)]) == 1
    captura = capsys.readouterr()
    texto = destino.read_text(encoding="utf-8")
    assert "cpf" in texto  # o relatório foi de fato gravado
    _sem_vazamento(texto, proibidas)
    _sem_vazamento(captura.out, proibidas)
    _sem_vazamento(captura.err, proibidas)


@pytest.mark.parametrize("formato", ["table", "json"])
def test_csv_sem_cabecalho_nao_vaza_a_primeira_linha_como_nome_de_coluna(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], formato: str
) -> None:
    rng = random.Random(78)
    cpf, email = gerar_cpf(rng, formatado=True), gerar_email(rng)
    linhas = [f"{gerar_cpf(rng, formatado=True)},{gerar_email(rng)}" for _ in range(3)]
    arquivo = tmp_path / "sem_cabecalho.csv"
    arquivo.write_text("\n".join([f"{cpf},{email}", *linhas]) + "\n", encoding="utf-8")
    assert main(["scan", str(arquivo), "--format", formato]) == 1
    captura = capsys.readouterr()
    assert captura.out
    _sem_vazamento(captura.out, _formas_proibidas([cpf, email]))
    _sem_vazamento(captura.err, _formas_proibidas([cpf, email]))


def test_anonymize_nao_traz_valor_original_no_stdout_no_stderr_nem_na_copia(
    csv_sintetico: tuple[Path, set[str]], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    arquivo, proibidas = csv_sintetico
    copia = tmp_path / "anonimizado.csv"
    assert main(["anonymize", str(arquivo), "--output", str(copia)]) == 0
    captura = capsys.readouterr()
    assert str(copia) in captura.out  # há resumo: o teste não passa por saída vazia
    _sem_vazamento(captura.out, proibidas)
    _sem_vazamento(captura.err, proibidas)
    texto = copia.read_text(encoding="utf-8")
    assert texto.startswith("cpf,cnpj,email,telefone\n")  # a cópia foi de fato gravada
    _sem_vazamento(texto, proibidas)


def test_anonymize_de_csv_sem_cabecalho_nao_vaza_a_primeira_linha(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rng = random.Random(79)
    cpf, email = gerar_cpf(rng, formatado=True), gerar_email(rng)
    linhas = [f"{gerar_cpf(rng, formatado=True)},{gerar_email(rng)}" for _ in range(3)]
    arquivo = tmp_path / "sem_cabecalho.csv"
    arquivo.write_text("\n".join([f"{cpf},{email}", *linhas]) + "\n", encoding="utf-8")
    copia = tmp_path / "anonimizado.csv"
    assert main(["anonymize", str(arquivo), "--output", str(copia)]) == 0
    captura = capsys.readouterr()
    assert "cabeçalho" in captura.err  # o aviso saiu, sem valor
    proibidas = _formas_proibidas([cpf, email])
    _sem_vazamento(captura.out, proibidas)
    _sem_vazamento(captura.err, proibidas)
    _sem_vazamento(copia.read_text(encoding="utf-8"), proibidas)


def test_o_detector_de_vazamento_acusa_um_vazamento_real() -> None:
    with pytest.raises(AssertionError, match="apareceram"):
        _sem_vazamento("cpf 111.444.777-35 no texto", {"111.444.777-35"})


def _modulos_importados(codigo: str) -> set[str]:
    """Nomes completos dos módulos importados (`urllib.request`, `socket`...)."""
    achados: set[str] = set()
    for no in ast.walk(ast.parse(codigo)):
        if isinstance(no, ast.Import):
            achados.update(alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
            achados.add(no.module)
            achados.update(f"{no.module}.{alias.name}" for alias in no.names)
    return achados


def _raizes_proibidas(codigo: str) -> set[str]:
    return {m.split(".")[0] for m in _modulos_importados(codigo)} & PROIBIDOS


def test_a_varredura_acusa_importacao_proibida_em_todas_as_formas() -> None:
    assert _raizes_proibidas("import socket") == {"socket"}
    assert _raizes_proibidas("import urllib.request") == {"urllib"}
    assert _raizes_proibidas("from urllib.request import urlopen") == {"urllib"}
    assert _raizes_proibidas("from urllib import request") == {"urllib"}
    assert _raizes_proibidas("import os, http.client") == {"http"}
    assert _raizes_proibidas("def f():\n    import requests\n") == {"requests"}
    assert _raizes_proibidas("import json\nfrom pathlib import Path") == set()


def test_nenhum_modulo_do_pacote_importa_rede() -> None:
    arquivos = sorted(RAIZ_SRC.rglob("*.py"))
    assert len(arquivos) >= 10  # a varredura enxerga o pacote, não uma pasta vazia
    infratores = {
        str(a.relative_to(RAIZ_SRC)): sorted(_raizes_proibidas(a.read_text(encoding="utf-8")))
        for a in arquivos
        if _raizes_proibidas(a.read_text(encoding="utf-8"))
    }
    assert infratores == {}
