"""Detector de CNPJ numérico e alfanumérico: casa o formato e valida o DV."""

import re

from lgpd_scan.detectors.base import Ocorrencia, Tipo
from lgpd_scan.detectors.digitos import dv_cnpj

# re.ASCII: sem ele \d casa dígitos de outros alfabetos e dv_cnpj levantaria ValueError.
# Só maiúsculas (ADR-0005). Máscara opcional em cada separador; o DV é sempre numérico.
_CANDIDATO = re.compile(
    r"(?<![0-9A-Za-z])[0-9A-Z]{2}\.?[0-9A-Z]{3}\.?[0-9A-Z]{3}/?[0-9A-Z]{4}-?\d{2}(?![0-9A-Za-z])",
    re.ASCII,
)
_MASCARA_COMPLETA = re.compile(r"[0-9A-Z]{2}\.[0-9A-Z]{3}\.[0-9A-Z]{3}/[0-9A-Z]{4}-\d{2}", re.ASCII)


def _valido(trecho: str) -> bool:
    limpo = re.sub(r"[./-]", "", trecho, flags=re.ASCII)
    base = limpo[:12]
    if len(set(base)) == 1:
        return False
    return dv_cnpj(base) == limpo[12:]


def detectar_cnpj(texto: str) -> list[Ocorrencia]:
    """Devolve os CNPJs válidos do texto, na ordem em que aparecem."""
    return [
        Ocorrencia(
            Tipo.CNPJ,
            m.start(),
            m.end(),
            formatado=_MASCARA_COMPLETA.fullmatch(m.group()) is not None,
        )
        for m in _CANDIDATO.finditer(texto)
        if _valido(m.group())
    ]
