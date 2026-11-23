"""Detector de telefone brasileiro: casa o formato e valida o DDD."""

import re

from lgpd_scan.detectors.base import Ocorrencia, Tipo

# Plano de numeração da Anatel: https://www.gov.br/anatel/pt-br/regulado/numeracao/plano-de-numeracao-brasileiro
DDDS_VALIDOS: frozenset[str] = frozenset(
    f"{n}"
    for n in (
        *range(11, 20),
        21,
        22,
        24,
        27,
        28,
        *range(31, 36),
        37,
        38,
        *range(41, 50),
        51,
        *range(53, 56),
        *range(61, 70),
        71,
        73,
        74,
        75,
        77,
        79,
        *range(81, 90),
        *range(91, 100),
    )
)

# re.ASCII: sem ele \d casa dígitos de outros alfabetos.
# Separadores só em três pontos, todos opcionais: depois do +55 (espaço), entre o DDD
# e o número, e antes dos últimos 4 dígitos. Parênteses no DDD: os dois ou nenhum.
# O +55 só vale com o '+': "5511987654321" (13 dígitos colados) não casa, limitação
# aceita. Também não casa um espaço depois do 9 ("11 9 8765-4321").
# O DDD é validado fora da regex, contra DDDS_VALIDOS.
_CANDIDATO = re.compile(
    r"(?<!\d)(?:\+55 ?)?(?:\((\d{2})\)|(\d{2}))[ .-]?(?:9\d{4}|[2-5]\d{3})[ .-]?\d{4}(?!\d)",
    re.ASCII,
)


def detectar_telefone(texto: str) -> list[Ocorrencia]:
    """Devolve os telefones com DDD válido do texto, na ordem em que aparecem."""
    return [
        Ocorrencia(
            Tipo.TELEFONE,
            m.start(),
            m.end(),
            formatado=any(c in m.group() for c in "( -"),
        )
        for m in _CANDIDATO.finditer(texto)
        if (m.group(1) or m.group(2)) in DDDS_VALIDOS
    ]
