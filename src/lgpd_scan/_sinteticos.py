"""Gerador reprodutível de dados pessoais sintéticos (módulo privado).

Toda função recebe um ``random.Random``: a mesma semente produz a mesma sequência.
Nada aqui lê dados reais nem usa rede.
"""

import random

from lgpd_scan.detectors.digitos import dv_cnpj, dv_cpf

# Provisório: a Tarefa 7 troca esta tupla por ``DDDS_VALIDOS``.
_DDDS = ("11", "21", "31")
_DOMINIOS = ("exemplo.com", "exemplo.org", "example.com")
_ALFABETO_CNPJ = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_DIGITOS = "0123456789"
_NOMES = ("ana", "bruno", "carla", "diego", "elisa", "fabio", "gisele", "hugo")


def _sortear(rng: random.Random, alfabeto: str, tamanho: int) -> str:
    return "".join(rng.choice(alfabeto) for _ in range(tamanho))


def gerar_cpf(rng: random.Random, *, formatado: bool) -> str:
    """Gera um CPF com DV válido, descartando bases de dígitos todos iguais."""
    while True:
        base = _sortear(rng, _DIGITOS, 9)
        if len(set(base)) > 1:
            break
    cpf = base + dv_cpf(base)
    if formatado:
        return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
    return cpf


def gerar_cnpj(rng: random.Random, *, alfanumerico: bool, formatado: bool) -> str:
    """Gera um CNPJ com DV válido; no modo alfanumérico a base tem ao menos uma letra."""
    alfabeto = _ALFABETO_CNPJ if alfanumerico else _DIGITOS
    while True:
        base = _sortear(rng, alfabeto, 12)
        if len(set(base)) == 1:
            continue
        if alfanumerico and base.isdigit():
            continue
        break
    cnpj = base + dv_cnpj(base)
    if formatado:
        return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
    return cnpj


def gerar_telefone(rng: random.Random, *, celular: bool, formatado: bool) -> str:
    """Gera um telefone: celular (9 + 8 dígitos) ou fixo (2-5 + 7 dígitos)."""
    ddd = rng.choice(_DDDS)
    if celular:
        numero = "9" + _sortear(rng, _DIGITOS, 8)
    else:
        numero = rng.choice("2345") + _sortear(rng, _DIGITOS, 7)
    if formatado:
        corte = len(numero) - 4
        return f"({ddd}) {numero[:corte]}-{numero[corte:]}"
    return ddd + numero


def gerar_email(rng: random.Random) -> str:
    """Gera um e-mail em domínio reservado para exemplos."""
    return f"{rng.choice(_NOMES)}{rng.randrange(1000)}@{rng.choice(_DOMINIOS)}"
