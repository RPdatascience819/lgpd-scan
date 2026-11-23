"""Cópia anonimizada de um CSV (`anonymize --mode mask`, design 5.6).

O núcleo de decisão é o mesmo do `scan` (`lgpd_scan.scoring`): `analisar` decide o que conta
e, célula a célula, `conta` e `efetivo` dizem o que mascarar e com qual tipo. Assim o
`anonymize` nunca discorda do `scan`. Nada aqui imprime ou guarda o valor de uma célula.
"""

import codecs
import csv
import os
import re
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from lgpd_scan._arquivos import e_o_mesmo_arquivo
from lgpd_scan.detectors.base import Tipo
from lgpd_scan.mascara import mascarar
from lgpd_scan.readers import ErroLeitura, LeitorCsv
from lgpd_scan.report import nome_de_coluna_seguro
from lgpd_scan.scoring import Analise, analisar, classificar_celula, conta, efetivo

_QUEBRA = re.compile(r"\r\n|\r|\n")
_BLOCO_QUEBRA: Final = 1 << 16  # caracteres por leitura ao procurar a primeira quebra de linha
_LIMITE_QUEBRA: Final = 1 << 24  # sem quebra até aqui, o arquivo tem uma linha só: vale o padrão
_QUEBRA_PADRAO: Final = "\r\n"  # o padrão do módulo csv


@dataclass(frozen=True, slots=True)
class ResumoAnonimizacao:
    """O que mudou na cópia. Só contagens: nunca valores."""

    celulas_alteradas: dict[Tipo, int]  # células em que o tipo foi mascarado, uma vez por célula
    cabecalho_alterado: bool = False  # algum nome de coluna trazia dado pessoal (CSV sem cabeçalho)


def _final_de_linha(caminho: Path, encoding: str) -> str:
    """O terminador da primeira quebra de linha do arquivo, para a cópia não trocar LF por CRLF.

    Devolve `"\\r\\n"` ou `"\\n"` (e `"\\r"`, se for o que o arquivo usa); sem nenhuma quebra,
    o padrão do módulo csv (`"\\r\\n"`).
    """
    lido = ""
    with open(caminho, encoding=encoding, newline="") as f:
        while len(lido) < _LIMITE_QUEBRA:
            bloco = f.read(_BLOCO_QUEBRA)
            lido += bloco
            achado = _QUEBRA.search(lido)
            # Um "\r" no fim do que foi lido pode ser metade de um "\r\n": lê mais um bloco.
            if achado is not None and (
                achado.group() != "\r" or achado.end() < len(lido) or not bloco
            ):
                return achado.group()
            if not bloco:
                return _QUEBRA_PADRAO
    return _QUEBRA_PADRAO


def _encoding_de_saida(caminho: Path, encoding: str) -> str:
    """O encoding para regravar o arquivo, sem inventar um BOM que a entrada não tinha.

    O leitor chama de `utf-8-sig` todo UTF-8 detectado, com ou sem BOM; gravar com esse codec
    acrescentaria um BOM a um arquivo que não o tinha.
    """
    if codecs.lookup(encoding).name != "utf-8-sig":
        return encoding
    with open(caminho, "rb") as f:
        return "utf-8-sig" if f.read(3) == codecs.BOM_UTF8 else "utf-8"


def _mascarar_celula(
    texto: str, nome_coluna: str, indice: int, analise: Analise, incluir_suspeitas: bool
) -> tuple[str, frozenset[Tipo]]:
    """A célula mascarada e os tipos que mudaram nela.

    Entra na máscara o achado que conta no `scan` (`conta`) e, com `incluir_suspeitas`, também
    a suspeita. O tipo e o trecho são os de `efetivo`: um ambíguo resolvido como telefone sai
    com a máscara de telefone. Trechos sobrepostos usam a união das máscaras: um caractere é
    mascarado se qualquer ocorrência que o cobre o mascarar, e a ordem não importa.
    """
    if not texto.strip():
        return texto, frozenset()
    ocorrencias = [
        efetivo(achado, indice, analise)
        for achado in classificar_celula(texto, nome_coluna)
        if incluir_suspeitas or conta(achado, indice, analise)
    ]
    caracteres = list(texto)
    for o in ocorrencias:
        for k, c in enumerate(mascarar(texto[o.inicio : o.fim], o.tipo)):
            if c == "*" and texto[o.inicio + k].isalnum():
                caracteres[o.inicio + k] = "*"
    novo = "".join(caracteres)
    if novo == texto:
        return texto, frozenset()
    return novo, frozenset(o.tipo for o in ocorrencias)


def anonimizar(
    entrada: Path,
    saida: Path,
    *,
    incluir_suspeitas: bool,
    forcar: bool,
    encoding: str | None,
    delimitador: str | None,
) -> ResumoAnonimizacao:
    """Grava em `saida` uma cópia de `entrada` com os dados pessoais mascarados.

    Duas passagens em streaming: `analisar` decide o que conta; depois cada linha é
    reescrita, no mesmo encoding (inclusive o BOM do `utf-8-sig`), delimitador e final de linha.

    A gravação é atômica: o texto vai para um temporário exclusivo ao lado do destino e só
    então troca o destino (`os.replace`); em qualquer erro o temporário some e o destino
    anterior fica intacto. Limitação aceita: o arquivo novo nasce com as permissões do
    temporário (só o dono, em sistemas POSIX), não com as do que foi substituído.

    Comportamento herdado do leitor, que entrega uma tabela retangular: linhas totalmente em
    branco somem, linhas curtas saem completadas com células vazias e colunas a mais ganham
    `coluna_N` no cabeçalho. O aspeamento também pode mudar (só se aspeia o que precisa).

    Um nome de coluna que traga dado pessoal (CSV sem cabeçalho: a primeira linha de dados
    virou "cabeçalho") sai mascarado por `nome_de_coluna_seguro`; `cabecalho_alterado` avisa.

    Raises:
        ErroLeitura: a saída é a própria entrada, é um diretório ou já existe sem `forcar`,
            ou o arquivo de entrada não pôde ser lido como CSV.
        OSError: falha ao ler ou gravar.
    """
    if e_o_mesmo_arquivo(entrada, saida):
        raise ErroLeitura("--output não pode ser o arquivo de entrada")
    if saida.is_dir():
        raise ErroLeitura(f"a saída é um diretório: {saida}")
    if saida.exists() and not forcar:
        raise ErroLeitura(f"o arquivo de saída já existe: {saida}; use --force para sobrescrever")

    leitor = LeitorCsv(entrada, encoding=encoding, delimitador=delimitador)
    analise = analisar(leitor, entrada.name)
    cabecalho = leitor.cabecalho
    cabecalho_seguro = [nome_de_coluna_seguro(nome) for nome in cabecalho]
    fim_de_linha = _final_de_linha(entrada, leitor.formato.encoding)
    encoding_de_saida = _encoding_de_saida(entrada, leitor.formato.encoding)
    alteradas: Counter[Tipo] = Counter()

    # `mkstemp` cria com O_EXCL e nome aleatório: nunca toca num arquivo do usuário.
    fd, nome = tempfile.mkstemp(dir=saida.parent, prefix="." + saida.name + ".", suffix=".tmp")
    temporario = Path(nome)
    try:
        with os.fdopen(fd, "w", encoding=encoding_de_saida, newline="") as f:
            escritor = csv.writer(
                f, delimiter=leitor.formato.delimitador, lineterminator=fim_de_linha
            )
            if cabecalho:
                escritor.writerow(cabecalho_seguro)
            for linha in leitor.linhas():
                nova: list[str] = []
                for indice, texto in enumerate(linha):
                    mascarada, tipos = _mascarar_celula(
                        texto, cabecalho[indice], indice, analise, incluir_suspeitas
                    )
                    alteradas.update(tipos)
                    nova.append(mascarada)
                escritor.writerow(nova)
        os.replace(temporario, saida)
    except BaseException:
        temporario.unlink(missing_ok=True)
        raise
    return ResumoAnonimizacao(dict(alteradas), cabecalho_seguro != cabecalho)
