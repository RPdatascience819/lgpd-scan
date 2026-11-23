"""Confiança de cada ocorrência, regra da maioria e risco do arquivo (design 5.4, ADR-0007).

Este é o núcleo de decisão: `scan` e `anonymize` o usam, para nunca discordarem.
Nada aqui guarda o trecho original de uma célula; a amostra do relatório nasce mascarada.
"""

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from functools import lru_cache
from itertools import pairwise
from typing import Final

from lgpd_scan.detectors import DETECTORES
from lgpd_scan.detectors.base import Ocorrencia, Tipo
from lgpd_scan.mascara import mascarar
from lgpd_scan.readers import LeitorCsv


class Confianca(StrEnum):
    ALTA = "alta"
    MEDIA = "media"


class Risco(StrEnum):
    NENHUM = "nenhum"
    BAIXO = "baixo"
    MEDIO = "medio"
    ALTO = "alto"


LIMIAR_MAIORIA: Final = 0.5
# 0.5 é exato em ponto flutuante, então Fraction(0.5) == 1/2 e a comparação da regra da
# maioria é feita em aritmética racional, sem arredondamento.
_LIMIAR = Fraction(LIMIAR_MAIORIA)


@dataclass(frozen=True, slots=True)
class Achado:
    ocorrencia: Ocorrencia
    confianca: Confianca
    ambiguo: bool  # conflito CPF e telefone resolvido sem contexto


# Palavras de nome de coluna que indicam um tipo. Comparação por palavra inteira, não por
# substring: "hotel" e "microfone" contêm "tel", mas não são telefone.
_PALAVRAS: Final[dict[str, Tipo]] = {
    "cpf": Tipo.CPF,
    "cnpj": Tipo.CNPJ,
    "email": Tipo.EMAIL,
    "telefone": Tipo.TELEFONE,
    "tel": Tipo.TELEFONE,
    "fone": Tipo.TELEFONE,
    "celular": Tipo.TELEFONE,
    "cel": Tipo.TELEFONE,
    "whatsapp": Tipo.TELEFONE,
}
_NAO_LETRA = re.compile(r"[^a-z]+")


def _palavras(nome: str) -> list[str]:
    separado: list[str] = []
    anterior = ""
    for c in nome:
        if anterior.islower() and c.isupper():  # camelCase: cpfCliente -> cpf Cliente
            separado.append(" ")
        separado.append(c)
        anterior = c
    decomposto = unicodedata.normalize("NFKD", "".join(separado))
    sem_marcas = "".join(c for c in decomposto if not unicodedata.combining(c))
    return [p for p in _NAO_LETRA.split(sem_marcas.casefold()) if p]


@lru_cache(maxsize=1024)
def _tipos_sugeridos(nome: str) -> frozenset[Tipo]:
    """Tipos que o nome da coluna indica: uma palavra, ou duas vizinhas coladas (e + mail)."""
    palavras = _palavras(nome)
    candidatas = [*palavras, *(a + b for a, b in pairwise(palavras))]
    return frozenset(_PALAVRAS[p] for p in candidatas if p in _PALAVRAS)


def tipo_sugerido(nome_coluna: str) -> Tipo | None:
    """O tipo que o nome indica, ou `None` se indicar zero ou mais de um."""
    tipos = _tipos_sugeridos(nome_coluna)
    return next(iter(tipos)) if len(tipos) == 1 else None


def _sobrepoe(a: Ocorrencia, b: Ocorrencia) -> bool:
    return a.inicio < b.fim and b.inicio < a.fim


def classificar_celula(texto: str, nome_coluna: str) -> list[Achado]:
    """Detecta, resolve conflitos e atribui a confiança de cada ocorrência da célula."""
    ocorrencias = sorted(
        (o for detectar in DETECTORES for o in detectar(texto)), key=lambda o: o.inicio
    )
    emails = [o for o in ocorrencias if o.tipo is Tipo.EMAIL]
    # O e-mail já cobre o que está dentro dele (ex.: joao11987654321@exemplo.com).
    ocorrencias = [
        o
        for o in ocorrencias
        if o.tipo is Tipo.EMAIL or not any(e.inicio <= o.inicio and o.fim <= e.fim for e in emails)
    ]

    tipos = _tipos_sugeridos(nome_coluna)
    descartadas: set[Ocorrencia] = set()
    forcadas: dict[Ocorrencia, tuple[Confianca, bool]] = {}
    cpfs = [o for o in ocorrencias if o.tipo is Tipo.CPF]
    telefones = [o for o in ocorrencias if o.tipo is Tipo.TELEFONE]
    for cpf in cpfs:
        for tel in telefones:
            if not _sobrepoe(cpf, tel):
                continue
            if tipos == {Tipo.TELEFONE}:
                descartadas.add(cpf)
                forcadas[tel] = (Confianca.ALTA, False)
            elif tipos == {Tipo.CPF}:
                descartadas.add(tel)
                forcadas[cpf] = (Confianca.ALTA, False)
            else:  # sem contexto, ou contexto dos dois: CPF, confiança média, ambíguo
                descartadas.add(tel)
                forcadas[cpf] = (Confianca.MEDIA, True)

    achados: list[Achado] = []
    for o in ocorrencias:
        if o in descartadas:
            continue
        if o in forcadas:
            confianca, ambiguo = forcadas[o]
        elif o.tipo is Tipo.EMAIL or o.formatado or o.tipo in tipos:
            confianca, ambiguo = Confianca.ALTA, False
        else:
            confianca, ambiguo = Confianca.MEDIA, False
        achados.append(Achado(o, confianca, ambiguo))
    return achados


@dataclass(frozen=True, slots=True)
class LinhaRelatorio:
    indice_coluna: int
    coluna: str
    tipo: Tipo
    contam: int
    suspeitas: int
    pct_preenchidas: float  # células da coluna com ≥1 ocorrência do tipo / preenchidas * 100
    confianca: Confianca  # predominante entre as que contam (ou MEDIA se só suspeitas)
    amostra: str  # primeira ocorrência, já mascarada
    ambiguo: bool


@dataclass(frozen=True, slots=True)
class Analise:
    arquivo: str  # só o nome do arquivo, sem diretório
    linhas: int
    colunas: list[LinhaRelatorio]  # ordenadas por (indice_coluna, tipo)
    risco: Risco
    media_conta: frozenset[tuple[int, Tipo]]  # pares cuja confiança média conta


class _Acumulador:
    """Contagens de um par (coluna, tipo), atualizadas célula a célula."""

    __slots__ = ("altas", "ambiguo", "amostra", "celulas", "medias")

    def __init__(self) -> None:
        self.celulas = 0  # células com ≥1 ocorrência do tipo, de qualquer confiança
        self.altas = 0
        self.medias = 0
        self.amostra = ""
        self.ambiguo = False


def analisar(leitor: LeitorCsv, nome_arquivo: str) -> Analise:
    """Uma passagem sobre o arquivo: acumula por (coluna, tipo) e decide a maioria ao final."""
    cabecalho = leitor.cabecalho
    preenchidas = [0] * len(cabecalho)
    acumuladores: dict[tuple[int, Tipo], _Acumulador] = {}
    total = 0
    for linha in leitor.linhas():
        total += 1
        for indice, texto in enumerate(linha):
            if not texto.strip():
                continue
            preenchidas[indice] += 1
            vistos: set[Tipo] = set()
            for achado in classificar_celula(texto, cabecalho[indice]):
                o = achado.ocorrencia
                acc = acumuladores.get((indice, o.tipo))
                if acc is None:
                    acc = acumuladores[(indice, o.tipo)] = _Acumulador()
                    acc.amostra = mascarar(texto[o.inicio : o.fim], o.tipo)
                if o.tipo not in vistos:
                    vistos.add(o.tipo)
                    acc.celulas += 1
                if achado.confianca is Confianca.ALTA:
                    acc.altas += 1
                else:
                    acc.medias += 1
                acc.ambiguo = acc.ambiguo or achado.ambiguo

    media_conta = frozenset(
        par
        for par, acc in acumuladores.items()
        if Fraction(acc.celulas, preenchidas[par[0]]) >= _LIMIAR
    )
    colunas: list[LinhaRelatorio] = []
    cpf_alta = False
    medio = False
    baixo = False
    for (indice, tipo), acc in sorted(acumuladores.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        medias_que_contam = acc.medias if (indice, tipo) in media_conta else 0
        contam = acc.altas + medias_que_contam
        suspeitas = acc.medias - medias_que_contam
        confianca = Confianca.ALTA if contam and acc.altas >= medias_que_contam else Confianca.MEDIA
        colunas.append(
            LinhaRelatorio(
                indice_coluna=indice,
                coluna=cabecalho[indice],
                tipo=tipo,
                contam=contam,
                suspeitas=suspeitas,
                pct_preenchidas=acc.celulas / preenchidas[indice] * 100,
                confianca=confianca,
                amostra=acc.amostra,
                ambiguo=acc.ambiguo,
            )
        )
        if tipo is Tipo.CPF and acc.altas:
            cpf_alta = True
        if contam and tipo is not Tipo.CNPJ:
            medio = True
        if contam and tipo is Tipo.CNPJ:
            baixo = True
    if cpf_alta:
        risco = Risco.ALTO
    elif medio:
        risco = Risco.MEDIO
    elif baixo:
        risco = Risco.BAIXO
    else:
        risco = Risco.NENHUM
    return Analise(
        arquivo=re.split(r"[\\/]", nome_arquivo)[-1],
        linhas=total,
        colunas=colunas,
        risco=risco,
        media_conta=media_conta,
    )


def conta(achado: Achado, indice_coluna: int, analise: Analise) -> bool:
    """Se o achado entra no risco e no `anonymize`: ALTA sempre; MEDIA só com a maioria."""
    if achado.confianca is Confianca.ALTA:
        return True
    return (indice_coluna, achado.ocorrencia.tipo) in analise.media_conta
