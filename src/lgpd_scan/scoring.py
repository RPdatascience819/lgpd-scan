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
from typing import Final, NamedTuple

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
    # Conflito CPF e telefone resolvido sem contexto. Na coluna que `analisar` resolve como
    # telefone, o achado continua ambiguo=True, mas vale como a `alternativa` (ver `efetivo`).
    ambiguo: bool
    # No ambíguo, o telefone descartado (o span pode incluir o +55); `analisar` decide pela
    # maioria da coluna se vale o CPF ou esta alternativa.
    alternativa: Ocorrencia | None = None


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
    forcadas: dict[Ocorrencia, tuple[Confianca, bool, Ocorrencia | None]] = {}
    cpfs = [o for o in ocorrencias if o.tipo is Tipo.CPF]
    telefones = [o for o in ocorrencias if o.tipo is Tipo.TELEFONE]
    # Um CPF que se sobrepõe a dois telefones (ou o inverso) é praticamente impossível; se
    # acontecer, o resultado depende da ordem destes laços.
    for cpf in cpfs:
        for tel in telefones:
            if not _sobrepoe(cpf, tel):
                continue
            # Só a pertinência de CPF e TELEFONE importa; EMAIL, CNPJ etc. não interferem.
            if Tipo.TELEFONE in tipos and Tipo.CPF not in tipos:
                descartadas.add(cpf)
                forcadas[tel] = (Confianca.ALTA, False, None)
            elif Tipo.CPF in tipos and Tipo.TELEFONE not in tipos:
                descartadas.add(tel)
                forcadas[cpf] = (Confianca.ALTA, False, None)
            elif tel.formatado and not cpf.formatado:
                # Sem contexto: o telefone com máscara vence o CPF sem máscara (confiança normal).
                descartadas.add(cpf)
            else:  # sem contexto, ou contexto dos dois: CPF, confiança média, ambíguo
                descartadas.add(tel)
                forcadas[cpf] = (Confianca.MEDIA, True, tel)

    achados: list[Achado] = []
    for o in ocorrencias:
        if o in descartadas:
            continue
        alternativa = None
        if o in forcadas:
            confianca, ambiguo, alternativa = forcadas[o]
        elif o.tipo is Tipo.EMAIL or o.formatado or o.tipo in tipos:
            confianca, ambiguo = Confianca.ALTA, False
        else:
            confianca, ambiguo = Confianca.MEDIA, False
        achados.append(Achado(o, confianca, ambiguo, alternativa))
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
    # Há ocorrência de conflito CPF e telefone resolvido sem contexto: na linha CPF, como CPF
    # MEDIA; na linha TELEFONE, quando a coluna foi resolvida como telefone pela maioria.
    ambiguo: bool


@dataclass(frozen=True, slots=True)
class Analise:
    arquivo: str  # só o nome do arquivo, sem diretório
    linhas: int
    colunas: list[LinhaRelatorio]  # ordenadas por (indice_coluna, tipo)
    risco: Risco
    media_conta: frozenset[tuple[int, Tipo]]  # pares cuja confiança média conta
    # Colunas em que a maioria é de telefone: os achados ambíguos valem como TELEFONE.
    ambiguos_como_telefone: frozenset[int] = frozenset()


class _Acumulador:
    """Contagens de um par (coluna, tipo), atualizadas célula a célula.

    `altas` e `medias` só contam achados não ambíguos; os ambíguos (só no par CPF) ficam em
    `amb`, porque seu destino (CPF ou telefone) só se sabe ao final da coluna.
    """

    __slots__ = (
        "altas",
        "amb",
        "amb_celulas",
        "amostra",
        "amostra_firme",
        "celulas",
        "celulas_firmes",
        "medias",
    )

    def __init__(self) -> None:
        self.celulas = 0  # células com ≥1 ocorrência do tipo, de qualquer confiança
        self.celulas_firmes = 0  # idem, sem contar a ocorrência ambígua
        self.altas = 0
        self.medias = 0
        self.amb = 0  # ocorrências ambíguas
        self.amb_celulas = 0  # células com ambíguo e sem telefone firme na célula
        self.amostra = ""  # primeira ocorrência (mascarada), ambígua ou não
        self.amostra_firme = ""  # primeira ocorrência não ambígua


class _Vista(NamedTuple):
    """O par (coluna, tipo) depois de decidir para onde vão os ambíguos."""

    altas: int
    medias: int  # MEDIA que depende da maioria
    extra: int  # ambíguos que entram em `contam` (coluna resolvida como telefone)
    celulas: int  # base da regra da maioria
    celulas_exibidas: int
    amostra: str
    ambiguo: bool


def _vista(acc: _Acumulador, tipo: Tipo, resolvida: bool, cpf: _Acumulador | None) -> _Vista | None:
    if not resolvida:
        return _Vista(
            acc.altas, acc.medias + acc.amb, 0, acc.celulas, acc.celulas, acc.amostra, acc.amb > 0
        )
    if tipo is Tipo.CPF:  # os ambíguos saem da linha CPF
        if not acc.celulas_firmes:
            return None
        return _Vista(
            acc.altas,
            acc.medias,
            0,
            acc.celulas_firmes,
            acc.celulas_firmes,
            acc.amostra_firme,
            False,
        )
    assert cpf is not None  # TELEFONE de coluna resolvida: os ambíguos vêm do acumulador CPF
    return _Vista(
        acc.altas,
        acc.medias,
        cpf.amb,
        acc.celulas,
        acc.celulas + cpf.amb_celulas,
        acc.amostra,  # a coluna só resolve como telefone com telefone firme: há amostra
        True,
    )


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
            todos: set[Tipo] = set()
            firmes: set[Tipo] = set()
            tem_ambiguo = False
            for achado in classificar_celula(texto, cabecalho[indice]):
                o = achado.ocorrencia
                acc = acumuladores.get((indice, o.tipo))
                if acc is None:
                    acc = acumuladores[(indice, o.tipo)] = _Acumulador()
                if not acc.amostra:
                    acc.amostra = mascarar(texto[o.inicio : o.fim], o.tipo)
                todos.add(o.tipo)
                if achado.ambiguo and achado.alternativa is not None:
                    acc.amb += 1
                    tem_ambiguo = True
                    continue
                firmes.add(o.tipo)
                if not acc.amostra_firme:
                    acc.amostra_firme = mascarar(texto[o.inicio : o.fim], o.tipo)
                if achado.confianca is Confianca.ALTA:
                    acc.altas += 1
                else:
                    acc.medias += 1
            for tipo in todos:
                acumuladores[(indice, tipo)].celulas += 1
            for tipo in firmes:
                acumuladores[(indice, tipo)].celulas_firmes += 1
            if tem_ambiguo and Tipo.TELEFONE not in firmes:
                acumuladores[(indice, Tipo.CPF)].amb_celulas += 1

    # Coluna com ambíguos: vira telefone se a maioria for de telefone (não ambíguo) e não de CPF.
    como_telefone: set[int] = set()
    for (indice, tipo), acc in acumuladores.items():
        if tipo is not Tipo.CPF or not acc.amb:
            continue
        tel = acumuladores.get((indice, Tipo.TELEFONE))
        tel_celulas = tel.celulas if tel else 0
        if (
            Fraction(tel_celulas, preenchidas[indice]) >= _LIMIAR
            and Fraction(acc.celulas, preenchidas[indice]) < _LIMIAR
        ):
            como_telefone.add(indice)

    vistas: dict[tuple[int, Tipo], _Vista] = {}
    for (indice, tipo), acc in acumuladores.items():
        cpf = acumuladores.get((indice, Tipo.CPF))
        vista = _vista(acc, tipo, indice in como_telefone, cpf)
        if vista is not None:
            vistas[(indice, tipo)] = vista

    media_conta = frozenset(
        par for par, v in vistas.items() if Fraction(v.celulas, preenchidas[par[0]]) >= _LIMIAR
    )
    colunas: list[LinhaRelatorio] = []
    cpf_alta = False
    medio = False
    baixo = False
    for (indice, tipo), v in sorted(vistas.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        medias_que_contam = v.medias if (indice, tipo) in media_conta else 0
        contam = v.altas + medias_que_contam + v.extra
        suspeitas = v.medias - medias_que_contam
        ha_altas = v.altas >= medias_que_contam + v.extra
        confianca = Confianca.ALTA if contam and ha_altas else Confianca.MEDIA
        colunas.append(
            LinhaRelatorio(
                indice_coluna=indice,
                coluna=cabecalho[indice],
                tipo=tipo,
                contam=contam,
                suspeitas=suspeitas,
                pct_preenchidas=v.celulas_exibidas / preenchidas[indice] * 100,
                confianca=confianca,
                amostra=v.amostra,
                ambiguo=v.ambiguo,
            )
        )
        if tipo is Tipo.CPF and v.altas:
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
        ambiguos_como_telefone=frozenset(como_telefone),
    )


def _vale_como_telefone(achado: Achado, indice_coluna: int, analise: Analise) -> bool:
    return (
        achado.ambiguo
        and achado.alternativa is not None
        and indice_coluna in analise.ambiguos_como_telefone
    )


def conta(achado: Achado, indice_coluna: int, analise: Analise) -> bool:
    """Se o achado entra no risco e no `anonymize`.

    ALTA sempre; MEDIA só com a maioria do par; o ambíguo de uma coluna resolvida como
    telefone (`ambiguos_como_telefone`) também conta.
    """
    if achado.confianca is Confianca.ALTA or _vale_como_telefone(achado, indice_coluna, analise):
        return True
    return (indice_coluna, achado.ocorrencia.tipo) in analise.media_conta


def efetivo(achado: Achado, indice_coluna: int, analise: Analise) -> Ocorrencia:
    """A ocorrência a mascarar: a alternativa (telefone) se o ambíguo foi resolvido assim."""
    if achado.alternativa is not None and _vale_como_telefone(achado, indice_coluna, analise):
        return achado.alternativa
    return achado.ocorrencia
