"""Detector de e-mail: regex pragmática, não a gramática completa da RFC 5322."""

import re

from lgpd_scan.detectors.base import Ocorrencia, Tipo

# Sem re.ASCII de propósito: e-mail não tem dígito verificador a proteger (a razão da
# flag em cpf/cnpj) e precisa aceitar letras Unicode ("joão@..."). Não "padronizar".
# A fronteira à esquerda impede começar no meio da parte local (nunca um e-mail parcial)
# e mantém a busca linear. O TLD só tem letras e não pode ser seguido de \w nem "-".
# \u0300-\u036f: marcas combinantes. Não são \w no `re` do Python, e uma letra acentuada
# em NFD (comum vindo do macOS: "a" + U+0303) perderia a base ou cortaria o e-mail no meio.
# O português só usa marcas dessa faixa (til, agudo, grave, circunflexo, cedilha).
# Limitação: o TLD segue só com letras, então "exemplo.côm" em NFD não é detectado;
# TLDs são ASCII na prática, e cortar o trecho no meio seria pior.
_EMAIL = re.compile(
    r"(?<![\w\u0300-\u036f.%+-])[\w\u0300-\u036f.%+-]+@(?:[\w\u0300-\u036f-]+\.)+"
    r"[^\W\d_]{2,}(?![\w\u0300-\u036f-])",
)


def detectar_email(texto: str) -> list[Ocorrencia]:
    """Devolve os e-mails do texto, na ordem em que aparecem."""
    return [
        Ocorrencia(Tipo.EMAIL, m.start(), m.end(), formatado=True) for m in _EMAIL.finditer(texto)
    ]
