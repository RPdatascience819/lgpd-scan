"""Robustez do `scan`: nome de coluna, --output atômico, caminhos e pipe quebrado."""

import json
import os
import random
import re
import sys
from pathlib import Path

import pytest

from lgpd_scan import cli
from lgpd_scan._sinteticos import gerar_cpf, gerar_email
from lgpd_scan.cli import main
from lgpd_scan.report import nome_de_coluna_seguro

RNG = random.Random(11)


def _csv(caminho: Path, cabecalho: str, linhas: list[str]) -> Path:
    caminho.write_text("\n".join([cabecalho, *linhas]) + "\n", encoding="utf-8")
    return caminho


def _com_cpf(pasta: Path) -> Path:
    return _csv(pasta / "cpf.csv", "cpf", [gerar_cpf(RNG, formatado=True) for _ in range(5)])


def test_nome_de_coluna_seguro_mascara_cpf_e_email_e_deixa_o_resto() -> None:
    assert nome_de_coluna_seguro("cpf") == "cpf"
    assert nome_de_coluna_seguro("e-mail") == "e-mail"
    cpf = gerar_cpf(RNG, formatado=True)
    email = gerar_email(RNG)
    mascarado = nome_de_coluna_seguro(f"{cpf},{email}")
    assert cpf not in mascarado
    assert email not in mascarado
    assert "***" in mascarado
    assert mascarado.endswith("@exemplo.com") or mascarado.endswith("@example.com")


def _sem_cabecalho(pasta: Path) -> tuple[Path, str, str]:
    cpf = gerar_cpf(RNG, formatado=True)
    email = gerar_email(RNG)
    linhas = [f"{gerar_cpf(RNG, formatado=True)},{gerar_email(RNG)}" for _ in range(3)]
    return _csv(pasta / "sem.csv", f"{cpf},{email}", linhas), cpf, email


@pytest.mark.parametrize("formato", ["table", "json"])
@pytest.mark.parametrize("para_arquivo", [False, True])
def test_csv_sem_cabecalho_nao_vaza_a_primeira_linha_e_avisa(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], formato: str, para_arquivo: bool
) -> None:
    arquivo, cpf, email = _sem_cabecalho(tmp_path)
    argv = ["scan", str(arquivo), "--format", formato]
    destino = tmp_path / "r.out"
    if para_arquivo:
        argv += ["--output", str(destino)]
    assert main(argv) == 1
    captura = capsys.readouterr()
    saida = destino.read_text(encoding="utf-8") if para_arquivo else captura.out
    assert saida
    for proibido in (cpf, re.sub(r"\D", "", cpf), email):
        assert proibido not in saida
        assert proibido not in captura.err
    assert "não ter cabeçalho" in captura.err
    assert "não é suportado" in captura.err


def test_cabecalho_normal_nao_e_alterado_nem_gera_aviso(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arquivo = _csv(tmp_path / "ok.csv", "cpf,e-mail", [f"{gerar_cpf(RNG, formatado=True)},x"])
    main(["scan", str(arquivo), "--format", "json"])
    captura = capsys.readouterr()
    assert json.loads(captura.out)["colunas"][0]["coluna"] == "cpf"
    assert "aviso" not in captura.err


def test_delimitador_vazio_da_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["scan", str(_com_cpf(tmp_path)), "--delimiter", ""]) == 2
    assert "delimitador" in capsys.readouterr().err


def test_output_hardlink_da_entrada_da_2_e_nao_toca_no_arquivo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    entrada = _com_cpf(tmp_path)
    antes = entrada.read_bytes()
    ligacao = tmp_path / "apelido.csv"
    try:
        os.link(entrada, ligacao)
    except (OSError, NotImplementedError, AttributeError) as erro:
        pytest.skip(f"hardlink não suportado neste sistema: {erro}")
    assert main(["scan", str(entrada), "--output", str(ligacao)]) == 2
    assert "entrada" in capsys.readouterr().err
    assert entrada.read_bytes() == antes
    assert ligacao.read_bytes() == antes


def test_output_com_force_color_sai_sem_ansi_e_com_amostra_inteira(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setenv("COLUMNS", "40")
    email = "a" * 40 + "@exemplo.com"
    arquivo = _csv(tmp_path / "longo.csv", "email_do_cliente", [email, email])
    destino = tmp_path / "r.txt"
    assert main(["scan", str(arquivo), "--output", str(destino)]) == 1
    texto = destino.read_text(encoding="utf-8")
    assert "\x1b[" not in texto
    assert "a" + "*" * 39 + "@exemplo.com" in texto


def test_falha_na_renderizacao_preserva_o_arquivo_anterior_e_nao_deixa_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def falha(*_a: object, **_k: object) -> str:
        raise OSError("falha simulada")

    monkeypatch.setattr(cli, "renderizar_json", falha)
    destino = tmp_path / "r.json"
    destino.write_text("anterior", encoding="utf-8")
    codigo = main(["scan", str(_com_cpf(tmp_path)), "--format", "json", "--output", str(destino)])
    assert codigo == 2
    assert destino.read_text(encoding="utf-8") == "anterior"
    assert not list(tmp_path.glob("*.tmp"))
    assert "Traceback" not in capsys.readouterr().err


def test_falha_na_troca_remove_o_tmp_e_preserva_o_anterior(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def falha(*_a: object, **_k: object) -> None:
        raise PermissionError("troca simulada")

    monkeypatch.setattr(os, "replace", falha)
    destino = tmp_path / "r.txt"
    destino.write_text("anterior", encoding="utf-8")
    assert main(["scan", str(_com_cpf(tmp_path)), "--output", str(destino)]) == 2
    assert destino.read_text(encoding="utf-8") == "anterior"
    assert not list(tmp_path.glob("*.tmp"))


def test_permissao_negada_ao_checar_o_arquivo_da_2_sem_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    arquivo = _com_cpf(tmp_path)

    def nega(self: Path) -> bool:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "exists", nega)
    assert main(["scan", str(arquivo)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("lgpd-scan: erro: ")
    assert "Traceback" not in err


def test_laco_de_symlink_ao_resolver_da_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def laco(self: Path, strict: bool = False) -> Path:
        raise RuntimeError("Symlink loop")

    monkeypatch.setattr(Path, "resolve", laco)
    saida = tmp_path / "r.txt"
    assert main(["scan", str(_com_cpf(tmp_path)), "--output", str(saida)]) == 2
    assert capsys.readouterr().err.startswith("lgpd-scan: erro: ")


class _StdoutQuebrado:
    """Um stdout cujo leitor já fechou (`| head`)."""

    def write(self, _texto: str) -> int:
        raise BrokenPipeError

    def flush(self) -> None:
        raise BrokenPipeError

    def isatty(self) -> bool:
        return False

    def __init__(self, fd: int) -> None:
        self._fd = fd

    def fileno(self) -> int:
        return self._fd  # um descritor válido: o programa o redireciona para o nulo


@pytest.mark.parametrize("formato", ["table", "json"])
def test_pipe_quebrado_no_stdout_nao_troca_o_codigo_de_risco(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, formato: str
) -> None:
    arquivo = _com_cpf(tmp_path)
    fd = os.open(os.devnull, os.O_WRONLY)
    try:
        monkeypatch.setattr(sys, "stdout", _StdoutQuebrado(fd))
        assert main(["scan", str(arquivo), "--format", formato]) == 1
    finally:
        os.close(fd)


def test_ctrl_c_vira_interrompido_e_130(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def interrompe(*_a: object, **_k: object) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "main", interrompe)
    with pytest.raises(SystemExit) as saida:
        cli.executar()
    assert saida.value.code == 130
    assert capsys.readouterr().err.strip() == "lgpd-scan: interrompido"
