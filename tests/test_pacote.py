import importlib.metadata
import socket

import pytest

import lgpd_scan
from lgpd_scan.cli import main


def test_versao_do_pacote_bate_com_metadados() -> None:
    assert lgpd_scan.__version__ == importlib.metadata.version("lgpd-scan")


def test_cli_version_imprime_e_sai_com_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as saida:
        main(["--version"])
    assert saida.value.code == 0
    assert capsys.readouterr().out.strip() == f"lgpd-scan {lgpd_scan.__version__}"


def test_rede_esta_bloqueada_na_suite() -> None:
    with pytest.raises(RuntimeError, match="rede bloqueada"):
        socket.socket()
