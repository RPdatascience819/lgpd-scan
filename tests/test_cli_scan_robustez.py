"""Robustez do `scan`: nome de coluna, --output atômico, caminhos e pipe quebrado."""

import errno
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
    assert "@" in mascarado and mascarado.split("@")[0].count("*") >= 1


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


def test_falha_antes_de_gravar_preserva_o_anterior(
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


def test_entrada_com_nome_terminado_em_tmp_nao_e_destruida(tmp_path: Path) -> None:
    entrada = tmp_path / "dados.csv.tmp"
    entrada.write_text("cpf\n" + gerar_cpf(RNG, formatado=True) + "\n", encoding="utf-8")
    antes = entrada.read_bytes()
    destino = tmp_path / "dados.csv"
    assert main(["scan", str(entrada), "--output", str(destino)]) == 1
    assert entrada.read_bytes() == antes
    assert "risco ALTO" in destino.read_text(encoding="utf-8")


def test_tmp_do_usuario_preexistente_continua_intacto(tmp_path: Path) -> None:
    alheio = tmp_path / "r.json.tmp"
    alheio.write_text("do usuario", encoding="utf-8")
    destino = tmp_path / "r.json"
    codigo = main(["scan", str(_com_cpf(tmp_path)), "--format", "json", "--output", str(destino)])
    assert codigo == 1
    assert alheio.read_text(encoding="utf-8") == "do usuario"
    assert json.loads(destino.read_text(encoding="utf-8"))["risco"] == "alto"


def test_nenhum_temporario_sobra_no_sucesso(tmp_path: Path) -> None:
    destino = tmp_path / "r.txt"
    assert main(["scan", str(_com_cpf(tmp_path)), "--output", str(destino)]) == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == ["cpf.csv", "r.txt"]


def test_falha_durante_a_escrita_do_temporario_preserva_o_anterior(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _EscritaQuebrada:
        def __init__(self, fd: int) -> None:
            self._fd = fd

        def __enter__(self) -> "_EscritaQuebrada":
            return self

        def __exit__(self, *_a: object) -> None:
            os.close(self._fd)

        def write(self, _texto: str) -> int:
            raise OSError("disco cheio simulado")

    monkeypatch.setattr(os, "fdopen", lambda fd, *_a, **_k: _EscritaQuebrada(fd))
    destino = tmp_path / "r.txt"
    destino.write_text("anterior", encoding="utf-8")
    assert main(["scan", str(_com_cpf(tmp_path)), "--output", str(destino)]) == 2
    assert destino.read_text(encoding="utf-8") == "anterior"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["cpf.csv", "r.txt"]


def _digitos_seguidos(texto: str) -> int:
    return max((len(m) for m in re.findall(r"[0-9]+", texto)), default=0)


def test_dados_colados_no_nome_nao_deixam_9_digitos_seguidos() -> None:
    cpf_puro = gerar_cpf(RNG, formatado=False)
    cpf_f = gerar_cpf(RNG, formatado=True)
    outro = gerar_cpf(RNG, formatado=False)
    nomes = [
        cpf_puro + outro,
        cpf_f + cpf_f,
        "(11) 91234-5678" + cpf_puro,
        "11" + cpf_puro,  # telefone sobreposto a um CPF
        f"a {cpf_f} b {gerar_email(RNG)} c {cpf_puro}{outro} d",
    ]
    for nome in nomes:
        seguro = nome_de_coluna_seguro(nome)
        assert _digitos_seguidos(seguro) < 9, nome
        assert len(seguro) == len(nome)


def test_nome_legitimo_com_9_digitos_e_mascarado_aceito_como_falso_positivo() -> None:
    assert nome_de_coluna_seguro("pedido_1234567890123") == "pedido_*************"


@pytest.mark.parametrize(
    ("erro", "nt", "esperado"),
    [
        (OSError(errno.ENOSPC, "No space left on device"), True, 2),
        (OSError(errno.ENOSPC, "No space left on device"), False, 2),
        (OSError(errno.EINVAL, "Invalid argument"), True, 1),
        (OSError(errno.EINVAL, "Invalid argument"), False, 2),
        (BrokenPipeError(errno.EPIPE, "Broken pipe"), True, 1),
        (BrokenPipeError(errno.EPIPE, "Broken pipe"), False, 1),
    ],
)
@pytest.mark.parametrize("formato", ["table", "json"])
def test_oserror_no_stdout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    erro: OSError,
    nt: bool,
    esperado: int,
    formato: str,
) -> None:
    arquivo = _com_cpf(tmp_path)
    fd = os.open(os.devnull, os.O_WRONLY)
    try:
        falso = _StdoutQuebrado(fd, erro)
        monkeypatch.setattr(sys, "stdout", falso)
        monkeypatch.setattr(os, "name", "nt" if nt else "posix")
        codigo = main(["scan", str(arquivo), "--format", formato])
    finally:
        os.close(fd)
    assert codigo == esperado
    if esperado == 2:
        assert "não foi possível escrever a saída" in capsys.readouterr().err


class _StdoutQuebrado:
    """Um stdout cujo `write` falha com o erro dado (pipe fechado, disco cheio...)."""

    def __init__(self, fd: int, erro: OSError) -> None:
        self._fd = fd
        self._erro = erro

    def write(self, _texto: str) -> int:
        raise self._erro

    def flush(self) -> None:
        raise self._erro

    def isatty(self) -> bool:
        return False

    def fileno(self) -> int:
        return self._fd  # um descritor válido: o programa o redireciona para o nulo


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
