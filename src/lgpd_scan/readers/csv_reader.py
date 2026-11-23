"""Leitor de CSV em streaming, com detecção de codificação e de delimitador.

Decisões que importam para quem reescreve o arquivo (`anonymize`): a leitura nunca altera
o conteúdo das células. Do `csv.Sniffer` só se usa o delimitador; aspas e espaços seguem o
padrão da biblioteca (RFC 4180), senão apóstrofos e espaços do dado sumiriam.
"""

import codecs
import csv
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

# Limite de caracteres por campo. O Excel limita uma célula a 32.767 caracteres (Microsoft,
# "Excel specifications and limits"); 16 Mi é 512 vezes isso. Sem limite, uma aspa aberta e
# nunca fechada engoliria o arquivo inteiro num único campo, com pico de memória do tamanho
# dele. Lido na hora do uso (`_linhas_brutas`), para os testes poderem reduzi-lo.
_LIMITE_CAMPO = 16 * 1024 * 1024

_TAMANHO_AMOSTRA = 65_536  # caracteres, não bytes
_TAMANHO_BLOCO = 1 << 20  # bytes por leitura na validação da codificação
_DELIMITADORES = ",;\t|"
# O csv só recusa estes caracteres como delimitador a partir do Python 3.13; no 3.11 e no 3.12
# ele os aceita e o arquivo viraria uma coluna só.
_DELIMITADORES_PROIBIDOS = frozenset('"\r\n')


class ErroLeitura(Exception):
    """Falha ao ler o arquivo. A mensagem cita linha e valor da opção, nunca o conteúdo."""


@dataclass(frozen=True, slots=True)
class FormatoCsv:
    encoding: str  # "utf-8-sig" | "cp1252" | o informado
    delimitador: str  # "," | ";" | "\t" | "|" | o informado


def _linha_do_erro(caminho: Path, encoding: str) -> int | None:
    """Decodifica em streaming (blocos fixos). Devolve a linha (1-based) do primeiro byte
    inválido, ou `None` se o arquivo inteiro decodifica."""
    # O decodificador incremental do utf-8-sig consome o BOM e desloca `erro.start` em 3 bytes.
    # Para achar a linha o BOM é irrelevante (não contém "\n"), e "utf-8" aceita os mesmos bytes.
    # Compara o nome normalizado: "UTF-8-SIG" e "utf_8_sig" são apelidos do mesmo codec.
    encoding = "utf-8" if codecs.lookup(encoding).name == "utf-8-sig" else encoding
    decodificador = codecs.getincrementaldecoder(encoding)()
    linhas_antes = 0
    with open(caminho, "rb") as f:
        while bloco := f.read(_TAMANHO_BLOCO):
            estado = decodificador.getstate()  # (bytes pendentes, flag interna)
            try:
                linhas_antes += decodificador.decode(bloco).count("\n")
            except UnicodeDecodeError as erro:
                # `erro.start` é relativo ao que o decodificador recebeu: pendentes + bloco.
                entrada = estado[0] + bloco
                valido = codecs.getincrementaldecoder(encoding)()
                valido.setstate((b"", estado[1]))
                return linhas_antes + valido.decode(entrada[: erro.start]).count("\n") + 1
    try:
        decodificador.decode(b"", final=True)
    except UnicodeDecodeError:
        return linhas_antes + 1  # sequência truncada no fim do arquivo
    return None


def _decide_encoding(caminho: Path, encoding: str | None) -> str:
    if encoding is not None:
        candidatas = [encoding]
    else:
        with open(caminho, "rb") as f:
            marca = f.read(2)
        # BOM de UTF-16. A marca do UTF-32 LE (FF FE 00 00) também começa com FF FE: fora do
        # escopo.
        candidatas = ["utf-16"] if marca in (b"\xff\xfe", b"\xfe\xff") else ["utf-8-sig", "cp1252"]
    linha = None
    for candidata in candidatas:
        try:
            # `_is_text_encoding` é atributo privado, mas é o único jeito estável de recusar
            # codecs que não são de texto (hex, zlib, base64...) antes de usá-los.
            if not codecs.lookup(candidata)._is_text_encoding:
                raise LookupError(candidata)
            linha = _linha_do_erro(caminho, candidata)
        except (LookupError, TypeError, ValueError):
            raise ErroLeitura(f"codificação não suportada: {candidata!r}") from None
        if linha is None:
            return candidata
    raise ErroLeitura(
        f"byte inválido na linha {linha} (codificação {candidata}); "
        "informe a codificação correta com --encoding"
    ) from None


class LeitorCsv:
    """Lê um CSV linha a linha. Após o construtor, `cabecalho` é final e a largura é fixa."""

    formato: FormatoCsv
    cabecalho: list[str]

    def __init__(
        self, caminho: Path, *, encoding: str | None = None, delimitador: str | None = None
    ) -> None:
        if delimitador is not None:
            if len(delimitador) != 1:
                raise ErroLeitura("o delimitador deve ter exatamente 1 caractere")
            if delimitador in _DELIMITADORES_PROIBIDOS:
                raise ErroLeitura("delimitador não aceito: aspas e quebras de linha")
            try:
                csv.reader([], delimiter=delimitador)  # o próprio csv recusa aspas e quebras
            except (ValueError, TypeError):
                raise ErroLeitura("delimitador não aceito pelo csv") from None
        self._caminho = caminho
        decidida = _decide_encoding(caminho, encoding)
        escolhido = delimitador if delimitador is not None else self._detecta_delimitador(decidida)
        self.formato = FormatoCsv(decidida, escolhido)
        self.cabecalho = self._mede_cabecalho()

    def _detecta_delimitador(self, encoding: str) -> str:
        with open(self._caminho, encoding=encoding, newline="") as f:
            amostra = f.read(_TAMANHO_AMOSTRA)
        try:
            return csv.Sniffer().sniff(amostra, delimiters=_DELIMITADORES).delimiter
        except csv.Error:
            # O Sniffer falha com CRLF e campos entre aspas: conta cada candidato no cabeçalho.
            # Mesmo cabeçalho de `_mede_cabecalho`: primeira linha não vazia, só por "\n".
            cabecalho = next(
                (linha.rstrip("\r") for linha in amostra.split("\n") if linha.rstrip("\r")), ""
            )
            return max(_DELIMITADORES, key=cabecalho.count) if cabecalho else ","

    def _linhas_brutas(self) -> Iterator[list[str]]:
        """Linhas não vazias, como o `csv.reader` as entrega, sem alterar o conteúdo."""
        # O módulo csv só tem limite global ao processo (não por leitor): eleva-se durante a
        # leitura e restaura-se no `finally`, que roda ao fim da iteração, no close() e na coleta.
        antigo = csv.field_size_limit(_LIMITE_CAMPO)
        try:
            with open(self._caminho, encoding=self.formato.encoding, newline="") as f:
                leitor = csv.reader(f, delimiter=self.formato.delimitador)
                try:
                    for linha in leitor:
                        if linha:
                            yield linha
                except csv.Error as erro:
                    if "field larger than field limit" in str(erro):
                        raise ErroLeitura(
                            f"campo maior que {_LIMITE_CAMPO} caracteres na linha "
                            f"{leitor.line_num}; pode ser uma aspa sem fechamento antes dela"
                        ) from None
                    raise ErroLeitura(f"CSV malformado na linha {leitor.line_num}") from None
        finally:
            csv.field_size_limit(antigo)

    def _mede_cabecalho(self) -> list[str]:
        cabecalho: list[str] | None = None
        largura = 0
        for linha in self._linhas_brutas():
            if cabecalho is None:
                cabecalho = linha
            largura = max(largura, len(linha))
        if cabecalho is None:
            return []
        extras = [f"coluna_{n}" for n in range(len(cabecalho) + 1, largura + 1)]
        return [*cabecalho, *extras]

    def linhas(self) -> Iterator[list[str]]:
        """Dados sem o cabeçalho, cada linha com `len(cabecalho)` células. Reabre o arquivo."""
        largura = len(self.cabecalho)
        primeira = True
        for linha in self._linhas_brutas():
            if primeira:
                primeira = False
                continue
            yield [*linha, *([""] * (largura - len(linha)))]
