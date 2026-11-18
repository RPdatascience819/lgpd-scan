"""Interface de linha de comando do LGPD-Scan."""

import argparse
import sys
from collections.abc import Sequence
from typing import NoReturn

from lgpd_scan import __version__


def _criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lgpd-scan",
        description="Encontra dados pessoais brasileiros, avalia o risco e anonimiza.",
    )
    parser.add_argument("--version", action="version", version=f"lgpd-scan {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Executa a CLI e devolve o código de saída."""
    parser = _criar_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 2


def executar() -> NoReturn:
    """Ponto de entrada do console script `lgpd-scan`."""
    sys.exit(main())
