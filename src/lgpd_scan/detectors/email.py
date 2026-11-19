"""Detector de e-mail: regex pragmática, não a gramática completa da RFC 5322."""

import re

from lgpd_scan.detectors.base import Ocorrencia, Tipo

# Sem re.ASCII de propósito: e-mail não tem dígito verificador a proteger (a razão da
# flag em cpf/cnpj) e precisa aceitar letras Unicode ("joão@..."). Não "padronizar".
# A fronteira à esquerda impede começar no meio da parte local (nunca um e-mail parcial)
# e mantém a busca linear. O TLD só tem letras e não pode ser seguido de \w nem "-".
_EMAIL = re.compile(
    r"(?<![\w.%+-])[\w.%+-]+@(?:[\w-]+\.)+[^\W\d_]{2,}(?![\w-])",
)


def detectar_email(texto: str) -> list[Ocorrencia]:
    """Devolve os e-mails do texto, na ordem em que aparecem."""
    return [
        Ocorrencia(Tipo.EMAIL, m.start(), m.end(), formatado=True) for m in _EMAIL.finditer(texto)
    ]
