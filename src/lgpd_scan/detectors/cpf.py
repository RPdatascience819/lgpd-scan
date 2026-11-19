"""Detector de CPF: casa o formato e valida o dígito verificador."""

import re

from lgpd_scan.detectors.base import Ocorrencia, Tipo
from lgpd_scan.detectors.digitos import dv_cpf

# re.ASCII: sem ele \d casa dígitos de outros alfabetos e dv_cpf levantaria ValueError.
# Máscara opcional nos pontos e no hífen; não pode estar colado em outros dígitos.
_CANDIDATO = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)", re.ASCII)
_MASCARA_COMPLETA = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}", re.ASCII)


def _valido(trecho: str) -> bool:
    digitos = re.sub(r"\D", "", trecho, flags=re.ASCII)
    if len(set(digitos)) == 1:
        return False
    return dv_cpf(digitos[:9]) == digitos[9:]


def detectar_cpf(texto: str) -> list[Ocorrencia]:
    """Devolve os CPFs válidos do texto, na ordem em que aparecem."""
    return [
        Ocorrencia(
            Tipo.CPF,
            m.start(),
            m.end(),
            formatado=_MASCARA_COMPLETA.fullmatch(m.group()) is not None,
        )
        for m in _CANDIDATO.finditer(texto)
        if _valido(m.group())
    ]
