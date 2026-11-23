"""Relatório do `scan`: tabela no terminal (Rich) e JSON estável (design 5.5).

Nada aqui vê o valor original de uma célula: a `amostra` de `LinhaRelatorio` já nasce
mascarada em `scoring`, e este módulo só a repassa.
"""

import json
from typing import TextIO

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from lgpd_scan.detectors.base import Tipo
from lgpd_scan.scoring import Analise, Confianca, LinhaRelatorio

SCHEMA_VERSION = 1

# Largura usada quando o destino não é um terminal (arquivo ou pipe): sem ela o Rich assume 80
# colunas e a amostra mascarada de um e-mail longo seria dobrada de forma ilegível.
LARGURA_FORA_DO_TERMINAL = 200

# Marca curta das linhas ambíguas (conflito CPF x telefone resolvido sem contexto), acrescentada
# à confiança. Ao lado da amostra ficaria longe do que ela qualifica: a confiança é a coluna que
# diz "quanto confiar" nesta linha.
MARCA_AMBIGUO = "(amb.)"
MARCA_SUSPEITA = "(suspeita)"

NOTA_SUSPEITAS = (
    "Suspeitas não entram no risco. Use --incluir-suspeitas no anonymize para mascará-las."
)
SEM_ACHADOS = "Nenhum dado pessoal encontrado."

_NOME_TIPO = {
    Tipo.CPF: "CPF",
    Tipo.CNPJ: "CNPJ",
    Tipo.EMAIL: "E-mail",
    Tipo.TELEFONE: "Telefone",
}
_NOME_CONFIANCA = {Confianca.ALTA: "alta", Confianca.MEDIA: "média"}


def criar_console(destino: TextIO) -> Console:
    """Console para `destino`; fora de um terminal, largo o bastante para não dobrar a amostra."""
    console = Console(file=destino, highlight=False)
    if console.is_terminal:
        return console
    return Console(
        file=destino, highlight=False, force_terminal=False, width=LARGURA_FORA_DO_TERMINAL
    )


def _milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _percentual(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def renderizar_json(analise: Analise) -> str:
    """O relatório em JSON, ASCII puro (`\\uXXXX` para o resto), chaves na ordem do esquema v1."""
    documento = {
        "schema_version": SCHEMA_VERSION,
        "arquivo": analise.arquivo,
        "linhas": analise.linhas,
        "risco": analise.risco.value,
        "colunas": [
            {
                "coluna": c.coluna,
                "indice_coluna": c.indice_coluna,
                "tipo": c.tipo.value,
                "contam": c.contam,
                "suspeitas": c.suspeitas,
                "pct_preenchidas": round(c.pct_preenchidas, 1),
                "confianca": c.confianca.value,
                "amostra": c.amostra,
                "ambiguo": c.ambiguo,
            }
            for c in analise.colunas
        ],
    }
    return json.dumps(documento, ensure_ascii=True, indent=2)


def _so_suspeita(linha: LinhaRelatorio) -> bool:
    return linha.contam == 0 and linha.suspeitas > 0


def renderizar_tabela(analise: Analise, console: Console) -> None:
    """Imprime o título, a tabela (ou "nada encontrado") e a nota de suspeitas."""
    # `Text` em toda célula e no título: nome de coluna vem do arquivo e não pode ser
    # interpretado como markup do Rich (`[bold]`) nem como emoji (`:smile:`).
    titulo = (
        f"LGPD-Scan · {analise.arquivo} · {_milhar(analise.linhas)} linhas · "
        f"risco {analise.risco.value.upper()}"
    )
    console.print(Text(titulo))
    console.print()
    if not analise.colunas:
        console.print(Text(SEM_ACHADOS))
        return

    tabela = Table(box=box.SIMPLE_HEAD, pad_edge=False)
    # overflow="fold" em todas: dobra a linha em vez de cortar com reticências, mesmo no
    # cabeçalho, para nunca esconder parte de um nome de coluna ou da amostra.
    tabela.add_column("Coluna", overflow="fold")
    tabela.add_column("Tipo", overflow="fold")
    tabela.add_column("Contam", justify="right", overflow="fold")
    tabela.add_column("Suspeitas", justify="right", overflow="fold")
    tabela.add_column("% preench.", justify="right", overflow="fold")
    tabela.add_column("Confiança", overflow="fold")
    tabela.add_column("Amostra", overflow="fold")
    for linha in analise.colunas:
        confianca = _NOME_CONFIANCA[linha.confianca]
        if linha.ambiguo:
            confianca = f"{confianca} {MARCA_AMBIGUO}"
        amostra = linha.amostra
        if _so_suspeita(linha):
            amostra = f"{amostra}  {MARCA_SUSPEITA}"
        tabela.add_row(
            Text(linha.coluna),
            Text(_NOME_TIPO[linha.tipo]),
            Text(_milhar(linha.contam)),
            Text(_milhar(linha.suspeitas)),
            Text(_percentual(linha.pct_preenchidas)),
            Text(confianca),
            Text(amostra),
        )
    console.print(tabela)
    if any(linha.suspeitas > 0 for linha in analise.colunas):
        console.print(Text(NOTA_SUSPEITAS))
