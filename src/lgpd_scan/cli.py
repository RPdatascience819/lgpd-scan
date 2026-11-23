"""Interface de linha de comando do LGPD-Scan.

Códigos de saída (contrato público, design 5.1): 0 = nada que conte (ou só CNPJ), 1 = risco
médio ou alto, 2 = erro de uso ou de leitura. Mensagens de erro vão para o stderr, em
português, e nunca trazem o conteúdo de uma célula.
"""

import argparse
import contextlib
import errno
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from lgpd_scan import __version__
from lgpd_scan.readers import ErroLeitura, LeitorCsv
from lgpd_scan.report import (
    criar_console,
    nome_de_coluna_seguro,
    renderizar_json,
    renderizar_tabela,
    tabela_como_texto,
)
from lgpd_scan.scoring import Analise, Risco, analisar

# Lido uma vez, no import: os testes trocam esta constante, nunca `os.name` (no Python 3.11 o
# pathlib lê `os.name` a cada `Path()`, e trocá-lo derruba o pytest).
_WINDOWS = os.name == "nt"

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
        # `samefile` exige que os dois existam; cobre hardlinks e diferenças de maiúsculas.
        return os.path.samefile(a, b)
    except OSError:
        return False


def _gravar_atomico(texto: str, destino: Path) -> None:
    """Grava num temporário ao lado e troca: uma falha nunca deixa o relatório pela metade."""
    # `mkstemp` cria com O_EXCL e nome aleatório: nunca toca num arquivo do usuário, como um
    # `r.json.tmp` que já exista. Limitação aceita: o `os.replace` não preserva permissões nem
    # ACL do arquivo que estava no destino.
    fd, nome = tempfile.mkstemp(dir=destino.parent, prefix="." + destino.name + ".", suffix=".tmp")
    temporario = Path(nome)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(texto)
        os.replace(temporario, destino)
    except BaseException:
        temporario.unlink(missing_ok=True)
        raise


def _desviar_stdout_para_o_nulo() -> None:
    """Depois de um pipe quebrado, manda o fd 1 para o nulo: nem a saída do interpretador
    ao encerrar pode trocar o código de saída."""
    with contextlib.suppress(OSError, ValueError, AttributeError):
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


def _e_pipe_fechado(erro: OSError) -> bool:
    """BrokenPipeError, ou EINVAL no Windows, que é como ele sinaliza o pipe fechado."""
    return isinstance(erro, BrokenPipeError) or (_WINDOWS and erro.errno == errno.EINVAL)


def _escrever_no_stdout(analise: Analise, formato: str) -> int | None:
    """Escreve o relatório. Devolve `SAIDA_ERRO` se não deu para escrever, senão `None`."""
    try:
        if formato == "json":
            sys.stdout.write(renderizar_json(analise) + "\n")
        else:
            renderizar_tabela(analise, criar_console(sys.stdout))
        sys.stdout.flush()
    except SystemExit:
        # O Rich trata o pipe quebrado sozinho: redireciona o fd 1 e encerra com SystemExit(1),
        # que se confundiria com "risco médio ou alto". Aqui o código de risco já está decidido.
        _desviar_stdout_para_o_nulo()
    except OSError as erro:
        if _e_pipe_fechado(erro):  # `lgpd-scan scan x.csv | head`
            _desviar_stdout_para_o_nulo()
        else:  # disco cheio, por exemplo
            return _erro(
                f"não foi possível escrever a saída: {erro.strerror or type(erro).__name__}"
            )
    return None


def _aviso_de_cabecalho(cabecalho: list[str]) -> None:
    if any(nome_de_coluna_seguro(nome) != nome for nome in cabecalho):
        print(
            "lgpd-scan: aviso: a primeira linha parece conter dados pessoais; o CSV pode não "
            "ter cabeçalho. CSV sem cabeçalho não é suportado nesta versão.",
            file=sys.stderr,
        )


def _verificar_caminhos(arquivo: Path, saida: Path | None) -> str | None:
    """A mensagem de erro de entrada e saída, ou `None` se estão em ordem."""
    try:
        if saida is not None and _e_o_mesmo_arquivo(arquivo, saida):
            return "--output não pode ser o arquivo de entrada"
        if not arquivo.exists():
            return f"arquivo não encontrado: {arquivo}"
        if not arquivo.is_file():
            return f"não é um arquivo: {arquivo}"
    except (OSError, RuntimeError) as erro:
        # PermissionError na travessia (Python 3.11 a 3.13) e laço de symlink (RuntimeError).
        detalhe = getattr(erro, "strerror", None) or type(erro).__name__
        return f"não foi possível acessar o caminho: {detalhe}"
    return None


def _comando_scan(args: argparse.Namespace) -> int:
    arquivo: Path = args.arquivo
    saida: Path | None = args.output
    problema = _verificar_caminhos(arquivo, saida)
    if problema is not None:
        return _erro(problema)
    try:
        leitor = LeitorCsv(arquivo, encoding=args.encoding, delimitador=args.delimiter)
        analise = analisar(leitor, arquivo.name)
    except ErroLeitura as erro:
        return _erro(str(erro))
    except OSError as erro:
        return _erro(f"não foi possível ler o arquivo: {erro.strerror or type(erro).__name__}")

    _aviso_de_cabecalho(leitor.cabecalho)
    if saida is None:
        falha = _escrever_no_stdout(analise, args.format)
        if falha is not None:
            return falha
    else:
        try:
            if args.format == "json":
                texto = renderizar_json(analise) + "\n"
            else:
                texto = tabela_como_texto(analise)
            _gravar_atomico(texto, saida)
        except OSError as erro:
            return _erro(
                f"não foi possível gravar o relatório: {erro.strerror or type(erro).__name__}"
            )
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
    try:
        codigo = main()
    except KeyboardInterrupt:
        print("lgpd-scan: interrompido", file=sys.stderr)
        codigo = 130
    sys.exit(codigo)
