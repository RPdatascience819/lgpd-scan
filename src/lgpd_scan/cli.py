"""Interface de linha de comando do LGPD-Scan.

Códigos de saída (contrato público, design 5.1): 0 = nada que conte (ou só CNPJ), 1 = risco
médio ou alto, 2 = erro de uso ou de leitura. Mensagens de erro vão para o stderr, em
português, e nunca trazem o conteúdo de uma célula.
"""

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from lgpd_scan import __version__
from lgpd_scan.readers import ErroLeitura, LeitorCsv
from lgpd_scan.report import criar_console, renderizar_json, renderizar_tabela
from lgpd_scan.scoring import Risco, analisar

SAIDA_OK = 0
SAIDA_RISCO = 1
SAIDA_ERRO = 2


def _criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lgpd-scan",
        description="Encontra dados pessoais brasileiros, avalia o risco e anonimiza.",
    )
    parser.add_argument("--version", action="version", version=f"lgpd-scan {__version__}")
    subcomandos = parser.add_subparsers(dest="comando", required=True, metavar="COMANDO")
    scan = subcomandos.add_parser(
        "scan",
        help="analisa um arquivo e relata os dados pessoais encontrados",
        description=(
            "Analisa um arquivo CSV e relata os dados pessoais encontrados e o risco. "
            "Código de saída: 0 sem risco médio ou alto, 1 com risco médio ou alto, "
            "2 em erro de uso ou de leitura."
        ),
    )
    scan.add_argument("arquivo", metavar="ARQUIVO", type=Path, help="arquivo CSV a analisar")
    scan.add_argument(
        "--format",
        choices=("table", "json"),
        default="table",
        help="formato do relatório (padrão: table)",
    )
    scan.add_argument(
        "--output",
        metavar="CAMINHO",
        type=Path,
        help="grava o relatório neste arquivo, em vez de imprimir (sobrescreve se existir)",
    )
    scan.add_argument(
        "--encoding", metavar="ENC", help="codificação do arquivo (padrão: detectada)"
    )
    scan.add_argument(
        "--delimiter", metavar="CHAR", help="delimitador de campos (padrão: detectado)"
    )
    return parser


def _erro(mensagem: str) -> int:
    print(f"lgpd-scan: erro: {mensagem}", file=sys.stderr)
    return SAIDA_ERRO


def _e_o_mesmo_arquivo(a: Path, b: Path) -> bool:
    """Se `a` e `b` são o mesmo arquivo, mesmo por grafias diferentes do caminho."""
    if a.resolve() == b.resolve():
        return True
    try:
        # `samefile` exige que os dois existam; cobre links e diferenças de maiúsculas.
        return os.path.samefile(a, b)
    except OSError:
        return False


def _gravar(texto: str, destino: Path) -> None:
    with open(destino, "w", encoding="utf-8", newline="") as f:
        f.write(texto)


def _comando_scan(args: argparse.Namespace) -> int:
    arquivo: Path = args.arquivo
    saida: Path | None = args.output
    if saida is not None and _e_o_mesmo_arquivo(arquivo, saida):
        return _erro("--output não pode ser o arquivo de entrada")
    if not arquivo.exists():
        return _erro(f"arquivo não encontrado: {arquivo}")
    if not arquivo.is_file():
        return _erro(f"não é um arquivo: {arquivo}")
    try:
        leitor = LeitorCsv(arquivo, encoding=args.encoding, delimitador=args.delimiter)
        analise = analisar(leitor, arquivo.name)
    except ErroLeitura as erro:
        return _erro(str(erro))
    except OSError as erro:
        return _erro(f"não foi possível ler o arquivo: {erro.strerror or type(erro).__name__}")

    try:
        if args.format == "json":
            texto = renderizar_json(analise) + "\n"
            if saida is None:
                sys.stdout.write(texto)
            else:
                _gravar(texto, saida)
        elif saida is None:
            renderizar_tabela(analise, criar_console(sys.stdout))
        else:
            with open(saida, "w", encoding="utf-8", newline="") as f:
                renderizar_tabela(analise, criar_console(f))
    except OSError as erro:
        return _erro(f"não foi possível gravar o relatório: {erro.strerror or type(erro).__name__}")
    if saida is not None:
        print(f"Relatório gravado em {saida}", file=sys.stderr)
    return SAIDA_RISCO if analise.risco in (Risco.MEDIO, Risco.ALTO) else SAIDA_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Executa a CLI e devolve o código de saída."""
    args = _criar_parser().parse_args(argv)
    if args.comando == "scan":
        return _comando_scan(args)
    return SAIDA_ERRO  # inalcançável: o argparse exige um subcomando conhecido


def _tolerar_caracteres_invalidos() -> None:
    """Troca por `?` o que o terminal não codifica, em vez de derrubar o programa.

    No Windows, com a saída redirecionada, o Python ≤ 3.14 escreve em cp1252: um nome de
    coluna com emoji levantaria `UnicodeEncodeError` (código 1, que no CI se confunde com
    "risco médio ou alto"). Fica aqui, e não em `main`, para não afetar quem chama `main`
    como biblioteca (e os testes com `capsys`).
    """
    for fluxo in (sys.stdout, sys.stderr):
        reconfigurar = getattr(fluxo, "reconfigure", None)
        if reconfigurar is not None:
            reconfigurar(errors="replace")


def executar() -> NoReturn:
    """Ponto de entrada do console script `lgpd-scan`."""
    _tolerar_caracteres_invalidos()
    sys.exit(main())
