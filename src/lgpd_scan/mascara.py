"""Mascaramento de um trecho detectado, preservando pontuação e comprimento.

Só os caracteres em que `str.isalnum()` é verdadeiro viram `*`; o resto (pontos, traços,
parênteses, espaços, `@`) fica onde está. As posições mantidas são contadas entre os
alfanuméricos, de modo que o mesmo critério serve ao trecho formatado e ao sem máscara.
"""

from lgpd_scan.detectors.base import Tipo

_CPF_MANTIDOS = frozenset(range(3, 9))
_CNPJ_MANTIDOS = frozenset({0, 1, 8, 9, 10, 11})


def _mascarar_por_ordem(trecho: str, mantidos: frozenset[int]) -> str:
    """Troca por `*` o alfanumérico cuja ordem (entre os alfanuméricos) não está em `mantidos`."""
    saida: list[str] = []
    ordem = 0
    for c in trecho:
        if c.isalnum():
            saida.append(c if ordem in mantidos else "*")
            ordem += 1
        else:
            saida.append(c)
    return "".join(saida)


def _mascarar_telefone(trecho: str) -> str:
    total = sum(c.isalnum() for c in trecho)
    inicio = 2 if trecho.startswith("+55") else 0  # os dígitos do +55 ficam
    # Depois do +55: 2 do DDD, o primeiro dígito do número e os 4 últimos.
    mantidos = {*range(inicio), inicio, inicio + 1, inicio + 2, *range(total - 4, total)}
    return _mascarar_por_ordem(trecho, frozenset(mantidos))


def _mascarar_email(trecho: str) -> str:
    local, arroba, dominio = trecho.partition("@")
    alfanumericos = sum(c.isalnum() for c in local)
    # Parte local com um só alfanumérico: mantê-lo mostraria tudo.
    mantidos = frozenset({0}) if alfanumericos > 1 else frozenset()
    return _mascarar_por_ordem(local, mantidos) + arroba + dominio


def mascarar(trecho: str, tipo: Tipo) -> str:
    """Devolve `trecho` mascarado conforme o `tipo`; o comprimento e a pontuação se preservam."""
    match tipo:
        case Tipo.CPF:
            return _mascarar_por_ordem(trecho, _CPF_MANTIDOS)
        case Tipo.CNPJ:
            return _mascarar_por_ordem(trecho, _CNPJ_MANTIDOS)
        case Tipo.TELEFONE:
            return _mascarar_telefone(trecho)
        case Tipo.EMAIL:
            return _mascarar_email(trecho)
