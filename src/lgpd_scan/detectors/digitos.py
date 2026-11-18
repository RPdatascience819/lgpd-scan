"""Dígitos verificadores de CPF e CNPJ (numérico e alfanumérico).

O CNPJ alfanumérico segue a IN RFB 2.229/2024: as 12 primeiras posições aceitam
``[0-9A-Z]``, cada caractere vale ``ord(c) - 48`` (``A`` = 17) e os dois dígitos
verificadores continuam sempre numéricos.
"""

import re

_BASE_CPF = re.compile(r"[0-9]{9}")
_BASE_CNPJ = re.compile(r"[0-9A-Z]{12}")


def _digito(valores: list[int], peso_maximo: int) -> int:
    """Módulo 11: pesos 2..peso_maximo da direita para a esquerda, reiniciando em 2."""
    soma = sum(v * (2 + i % (peso_maximo - 1)) for i, v in enumerate(reversed(valores)))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def dv_cpf(base: str) -> str:
    """Calcula os 2 dígitos verificadores de uma base de CPF com 9 dígitos."""
    if not _BASE_CPF.fullmatch(base):
        raise ValueError(f"base de CPF inválida: esperados 9 dígitos, recebido {base!r}")
    valores = [int(c) for c in base]
    d1 = _digito(valores, 11)
    d2 = _digito([*valores, d1], 11)
    return f"{d1}{d2}"


def dv_cnpj(base: str) -> str:
    """Calcula os 2 dígitos verificadores de uma base de CNPJ com 12 caracteres ``[0-9A-Z]``."""
    if not _BASE_CNPJ.fullmatch(base):
        raise ValueError(f"base de CNPJ inválida: esperados 12 de [0-9A-Z], recebido {base!r}")
    valores = [ord(c) - 48 for c in base]
    d1 = _digito(valores, 9)
    d2 = _digito([*valores, d1], 9)
    return f"{d1}{d2}"
