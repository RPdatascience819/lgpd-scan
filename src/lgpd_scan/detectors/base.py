"""Tipos compartilhados por todos os detectores."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class Tipo(StrEnum):
    """Categoria de dado pessoal detectada."""

    CPF = "cpf"
    CNPJ = "cnpj"
    EMAIL = "email"
    TELEFONE = "telefone"


@dataclass(frozen=True, slots=True)
class Ocorrencia:
    """Posição de um dado pessoal dentro do texto de uma célula.

    Não guarda o valor encontrado, de propósito: nenhuma estrutura do programa
    acumula dados pessoais. Quem precisa do trecho fatia o texto da célula.
    """

    tipo: Tipo
    inicio: int  # índice no texto da célula; texto[inicio:fim] é o trecho
    fim: int
    formatado: bool  # True só quando o trecho segue a máscara completa do tipo


Detector = Callable[[str], list[Ocorrencia]]
