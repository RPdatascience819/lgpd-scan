"""Leitor de CSV em streaming, com detecção de codificação e de delimitador.

Decisões que importam para quem reescreve o arquivo (`anonymize`): a leitura nunca altera
o conteúdo das células. Do `csv.Sniffer` só se usa o delimitador; aspas e espaços seguem o
padrão da biblioteca (RFC 4180), senão apóstrofos e espaços do dado sumiriam.
"""

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

csv.field_size_limit(2**31 - 1)

_TAMANHO_AMOSTRA = 65_536  # caracteres, não bytes
_TAMANHO_BLOCO = 1 << 20  # bytes por leitura na validação da codificação
_DELIMITADORES = ",;\t|"


class ErroLeitura(Exception):
    """Falha ao ler o arquivo. A mensagem cita linha e valor da opção, nunca o conteúdo."""


@dataclass(frozen=True, slots=True)
class FormatoCsv:
    encoding: str  # "utf-8-sig" | "cp1252" | o informado
    delimitador: str  # "," | ";" | "\t" | "|" | o informado


def _linha_do_byte_invalido(caminho: Path, encoding: str) -> int:
    """Número (1-based) da linha física do primeiro byte que `encoding` não decodifica."""
    dados = caminho.read_bytes()
    try:
        dados.decode(encoding)
    except UnicodeDecodeError as erro:
        prefixo = dados[: erro.start].decode(encoding, errors="replace")
        return prefixo.count("\n") + 1
    return 1  # inalcançável: só chamamos depois de uma falha de decodificação


def _decodifica_tudo(caminho: Path, encoding: str) -> None:
    """Lê o arquivo inteiro em blocos; levanta `UnicodeDecodeError` se não decodificar."""
    with open(caminho, encoding=encoding, newline="") as f:
        while f.read(_TAMANHO_BLOCO):
            pass


def _decide_encoding(caminho: Path, encoding: str | None) -> str:
    candidatas = [encoding] if encoding is not None else ["utf-8-sig", "cp1252"]
    for candidata in candidatas:
        try:
            _decodifica_tudo(caminho, candidata)
        except LookupError:
            raise ErroLeitura(f"codificação desconhecida: {candidata!r}") from None
        except UnicodeDecodeError:
            ultima = candidata
            continue
        return candidata
    linha = _linha_do_byte_invalido(caminho, ultima)
    raise ErroLeitura(
        f"byte inválido na linha {linha} (codificação {ultima}); "
        "informe a codificação correta com --encoding"
    ) from None


class LeitorCsv:
    """Lê um CSV linha a linha. Após o construtor, `cabecalho` é final e a largura é fixa."""

    formato: FormatoCsv
    cabecalho: list[str]

    def __init__(
        self, caminho: Path, *, encoding: str | None = None, delimitador: str | None = None
    ) -> None:
        if delimitador is not None and len(delimitador) != 1:
            raise ErroLeitura("o delimitador deve ter exatamente 1 caractere")
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
            return ","

    def _linhas_brutas(self) -> Iterator[list[str]]:
        """Linhas não vazias, como o `csv.reader` as entrega, sem alterar o conteúdo."""
        with open(self._caminho, encoding=self.formato.encoding, newline="") as f:
            leitor = csv.reader(f, delimiter=self.formato.delimitador)
            try:
                for linha in leitor:
                    if linha:
                        yield linha
            except csv.Error:
                raise ErroLeitura(f"CSV malformado na linha {leitor.line_num}") from None

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
