"""Testes de confiança, regra da maioria e risco. Dados só sintéticos."""

import csv
import io
import random
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import pytest

from lgpd_scan._sinteticos import gerar_cnpj, gerar_cpf, gerar_email, gerar_telefone
from lgpd_scan.detectors.base import Tipo
from lgpd_scan.detectors.cpf import detectar_cpf
from lgpd_scan.detectors.telefone import detectar_telefone
from lgpd_scan.mascara import mascarar
from lgpd_scan.readers import LeitorCsv
from lgpd_scan.scoring import (
    LIMIAR_MAIORIA,
    Achado,
    Analise,
    Confianca,
    LinhaRelatorio,
    Risco,
    _tipos_sugeridos,
    analisar,
    classificar_celula,
    conta,
    efetivo,
    tipo_sugerido,
)

RNG = random.Random(2026)


def _cpf_e_telefone() -> str:
    """Onze dígitos que são, ao mesmo tempo, CPF válido e celular válido."""
    rng = random.Random(7)
    for _ in range(100_000):
        numero = gerar_cpf(rng, formatado=False)
        if detectar_telefone(numero):
            return numero
    raise AssertionError("não achei um número que seja CPF e telefone")


def _cpf_sem_ddd() -> str:
    """CPF sem máscara começando em 20 (DDD inexistente): nunca é telefone."""
    while True:
        numero = gerar_cpf(RNG, formatado=False)
        if numero.startswith("20"):
            return numero


def _nao_cpf_sem_ddd() -> str:
    """Onze dígitos começando em 20 que não são CPF válido."""
    while True:
        numero = "20" + "".join(RNG.choice("0123456789") for _ in range(9))
        if not detectar_cpf(numero):
            return numero


def _csv(tmp_path: Path, cabecalho: list[str], linhas: list[list[str]]) -> LeitorCsv:
    buffer = io.StringIO(newline="")
    escritor = csv.writer(buffer, lineterminator="\n")
    escritor.writerow(cabecalho)
    escritor.writerows(linhas)
    caminho = tmp_path / "dados.csv"
    caminho.write_bytes(buffer.getvalue().encode("utf-8"))
    return LeitorCsv(caminho)


def _linha(analise: Analise, tipo: Tipo, indice: int = 0) -> LinhaRelatorio:
    achadas = [c for c in analise.colunas if c.tipo == tipo and c.indice_coluna == indice]
    assert len(achadas) == 1
    return achadas[0]


# ---------------------------------------------------------------- tipo_sugerido


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("CPF do cliente", Tipo.CPF),
        ("E-mail", Tipo.EMAIL),
        ("Celular", Tipo.TELEFONE),
        ("hotel", None),
        ("Nº CNPJ", Tipo.CNPJ),
        ("microfone", None),
        ("cancelado", None),
        ("excelente", None),
        ("celula", None),
        ("cpfCliente", Tipo.CPF),
        ("Telefone 1", Tipo.TELEFONE),
        ("telefone1", Tipo.TELEFONE),
        ("e_mail", Tipo.EMAIL),
        ("WhatsApp", Tipo.TELEFONE),
        ("col7", None),
        ("", None),
    ],
)
def test_tipo_sugerido(nome: str, esperado: Tipo | None) -> None:
    assert tipo_sugerido(nome) is esperado


def test_coluna_com_dois_tipos_nao_tem_tipo_sugerido_unico() -> None:
    assert tipo_sugerido("cpf_cnpj") is None
    assert tipo_sugerido("CPF/CNPJ") is None
    assert _tipos_sugeridos("cpf_cnpj") == frozenset({Tipo.CPF, Tipo.CNPJ})


# ------------------------------------------------------------ classificar_celula


def test_formatado_e_alta_em_qualquer_coluna() -> None:
    achados = classificar_celula(gerar_cpf(RNG, formatado=True), "col7")
    assert [(a.ocorrencia.tipo, a.confianca) for a in achados] == [(Tipo.CPF, Confianca.ALTA)]


def test_sem_mascara_em_coluna_cpf_e_alta() -> None:
    achados = classificar_celula(_cpf_sem_ddd(), "cpf")
    assert [a.confianca for a in achados] == [Confianca.ALTA]


def test_sem_mascara_em_coluna_sem_contexto_e_media() -> None:
    achados = classificar_celula(_cpf_sem_ddd(), "col7")
    assert [(a.confianca, a.ambiguo) for a in achados] == [(Confianca.MEDIA, False)]


def test_email_e_sempre_alta() -> None:
    achados = classificar_celula(gerar_email(RNG), "col7")
    assert [(a.ocorrencia.tipo, a.confianca) for a in achados] == [(Tipo.EMAIL, Confianca.ALTA)]


def test_coluna_cpf_cnpj_trata_os_dois_tipos_sem_mascara_como_alta() -> None:
    cpf = _cpf_sem_ddd()
    cnpj = gerar_cnpj(RNG, alfanumerico=False, formatado=False)
    achados = classificar_celula(f"{cpf} {cnpj}", "cpf_cnpj")
    assert sorted((a.ocorrencia.tipo.value, a.confianca) for a in achados) == [
        ("cnpj", Confianca.ALTA),
        ("cpf", Confianca.ALTA),
    ]


def test_conflito_em_coluna_telefone_vira_telefone_alta() -> None:
    numero = _cpf_e_telefone()
    achados = classificar_celula(numero, "telefone")
    assert [(a.ocorrencia.tipo, a.confianca, a.ambiguo) for a in achados] == [
        (Tipo.TELEFONE, Confianca.ALTA, False)
    ]


def test_conflito_em_coluna_cpf_vira_cpf_alta() -> None:
    achados = classificar_celula(_cpf_e_telefone(), "CPF")
    assert [(a.ocorrencia.tipo, a.confianca, a.ambiguo) for a in achados] == [
        (Tipo.CPF, Confianca.ALTA, False)
    ]


@pytest.mark.parametrize("coluna", ["obs", "cpf_telefone"])
def test_conflito_sem_contexto_ou_com_os_dois_vira_cpf_media_ambiguo(coluna: str) -> None:
    achados = classificar_celula(_cpf_e_telefone(), coluna)
    assert [(a.ocorrencia.tipo, a.confianca, a.ambiguo) for a in achados] == [
        (Tipo.CPF, Confianca.MEDIA, True)
    ]


@pytest.mark.parametrize(
    ("coluna", "tipo", "confianca", "ambiguo"),
    [
        ("telefone", Tipo.TELEFONE, Confianca.ALTA, False),
        ("telefone_email", Tipo.TELEFONE, Confianca.ALTA, False),
        ("contato (tel/email)", Tipo.TELEFONE, Confianca.ALTA, False),
        ("cpf", Tipo.CPF, Confianca.ALTA, False),
        ("cpf_email", Tipo.CPF, Confianca.ALTA, False),
        ("cpf_telefone", Tipo.CPF, Confianca.MEDIA, True),
        ("obs", Tipo.CPF, Confianca.MEDIA, True),
    ],
)
def test_conflito_decide_pela_pertinencia_de_cpf_e_telefone(
    coluna: str, tipo: Tipo, confianca: Confianca, ambiguo: bool
) -> None:
    achados = classificar_celula(_cpf_e_telefone(), coluna)
    assert [(a.ocorrencia.tipo, a.confianca, a.ambiguo) for a in achados] == [
        (tipo, confianca, ambiguo)
    ]


def test_conflito_por_sobreposicao_parcial_com_mais_55() -> None:
    texto = "+55 " + _cpf_e_telefone()
    # Pré-condição: os dois detectores acham algo, e os intervalos não são idênticos.
    assert detectar_telefone(texto)[0].inicio == 0
    assert detectar_cpf(texto)[0].inicio == 4
    achados = classificar_celula(texto, "telefone")
    assert len(achados) == 1
    assert achados[0].ocorrencia.tipo is Tipo.TELEFONE
    assert achados[0].ocorrencia.inicio == 0


def test_ocorrencia_dentro_de_email_e_descartada() -> None:
    texto = f"joao{_cpf_e_telefone()}@exemplo.com"
    # Pré-condição: sem o descarte, o telefone dentro do e-mail apareceria.
    assert detectar_telefone(texto)
    achados = classificar_celula(texto, "col7")
    assert [a.ocorrencia.tipo for a in achados] == [Tipo.EMAIL]


def test_ocorrencia_fora_do_email_na_mesma_celula_continua() -> None:
    texto = f"{gerar_email(RNG)} {gerar_cpf(RNG, formatado=True)}"
    achados = classificar_celula(texto, "col7")
    assert [a.ocorrencia.tipo for a in achados] == [Tipo.EMAIL, Tipo.CPF]


def test_celula_sem_dado_pessoal() -> None:
    assert classificar_celula("texto qualquer", "cpf") == []


def test_conta() -> None:
    ocorrencia = detectar_cpf(_cpf_sem_ddd())[0]
    alta = Achado(ocorrencia, Confianca.ALTA, ambiguo=False)
    media = Achado(ocorrencia, Confianca.MEDIA, ambiguo=False)
    vazia = Analise("a.csv", 0, [], Risco.NENHUM, frozenset())
    com_media = Analise("a.csv", 0, [], Risco.NENHUM, frozenset({(2, Tipo.CPF)}))
    assert conta(alta, 2, vazia)
    assert not conta(media, 2, vazia)
    assert conta(media, 2, com_media)
    assert not conta(media, 3, com_media)


# ---------------------------------------------------------------------- analisar


def test_limiar_exportado() -> None:
    assert LIMIAR_MAIORIA == 0.5


def test_arquivo_sem_diretorio(tmp_path: Path) -> None:
    leitor = _csv(tmp_path, ["a"], [["x"]])
    assert analisar(leitor, "dados/clientes.csv").arquivo == "clientes.csv"
    assert analisar(leitor, "dados\\clientes.csv").arquivo == "clientes.csv"
    assert analisar(leitor, "clientes.csv").arquivo == "clientes.csv"


def test_maioria_codigo_pedido_vira_suspeita(tmp_path: Path) -> None:
    celulas = [_cpf_sem_ddd() for _ in range(10)] + [_nao_cpf_sem_ddd() for _ in range(990)]
    RNG.shuffle(celulas)
    leitor = _csv(tmp_path, ["codigo_pedido"], [[c] for c in celulas])
    analise = analisar(leitor, "pedidos.csv")
    assert analise.linhas == 1000
    assert [c.tipo for c in analise.colunas] == [Tipo.CPF]  # nenhuma linha TELEFONE
    linha = analise.colunas[0]
    assert (linha.suspeitas, linha.contam) == (10, 0)
    assert linha.confianca is Confianca.MEDIA
    assert analise.risco is Risco.NENHUM
    assert analise.media_conta == frozenset()


def test_maioria_inversa_col7_conta_e_risco_medio(tmp_path: Path) -> None:
    celulas = [_cpf_sem_ddd() for _ in range(95)] + ["sem dado"] * 5
    leitor = _csv(tmp_path, ["col7"], [[c] for c in celulas])
    analise = analisar(leitor, "x.csv")
    linha = analise.colunas[0]
    assert (linha.contam, linha.suspeitas) == (95, 0)
    assert linha.confianca is Confianca.MEDIA
    assert analise.media_conta == frozenset({(0, Tipo.CPF)})
    assert analise.risco is Risco.MEDIO


def test_fronteira_de_50_por_cento_conta_e_uma_celula_a_menos_nao(tmp_path: Path) -> None:
    vazias = ["", "   "]  # células vazias ou só com espaços ficam fora do denominador
    # 4 CPFs em 8 preenchidas = exatamente 50%.
    cpfs = [_cpf_sem_ddd() for _ in range(4)]
    no_limite = _csv(tmp_path, ["col7"], [[c] for c in [*cpfs, *["texto"] * 4, *vazias]])
    a = analisar(no_limite, "a.csv")
    assert (a.colunas[0].contam, a.colunas[0].suspeitas) == (4, 0)
    assert a.media_conta == frozenset({(0, Tipo.CPF)})
    # 3 CPFs em 8 preenchidas = 37,5%.
    abaixo = _csv(tmp_path, ["col7"], [[c] for c in [*cpfs[:3], *["texto"] * 5, *vazias]])
    b = analisar(abaixo, "b.csv")
    assert (b.colunas[0].contam, b.colunas[0].suspeitas) == (0, 3)
    assert b.media_conta == frozenset()


def test_maioria_conta_celulas_e_nao_ocorrencias(tmp_path: Path) -> None:
    duas = f"{_cpf_sem_ddd()} {_cpf_sem_ddd()}"
    celulas = [duas] * 3 + ["texto"] * 7  # 6 ocorrências, mas só 3 de 10 células
    leitor = _csv(tmp_path, ["col7"], [[c] for c in celulas])
    linha = analisar(leitor, "x.csv").colunas[0]
    assert (linha.contam, linha.suspeitas) == (0, 6)
    assert linha.pct_preenchidas == pytest.approx(30.0)


def test_pct_preenchidas_ignora_vazias(tmp_path: Path) -> None:
    celulas = [_cpf_sem_ddd(), "texto", "", "  "]
    leitor = _csv(tmp_path, ["col7"], [[c] for c in celulas])
    assert analisar(leitor, "x.csv").colunas[0].pct_preenchidas == pytest.approx(50.0)


def test_risco_alto_com_cpf_alta(tmp_path: Path) -> None:
    leitor = _csv(tmp_path, ["cpf"], [[_cpf_sem_ddd()]])
    assert analisar(leitor, "x.csv").risco is Risco.ALTO
    leitor = _csv(tmp_path, ["col7"], [[gerar_cpf(RNG, formatado=True)]])
    assert analisar(leitor, "x.csv").risco is Risco.ALTO


def test_risco_medio_so_com_email(tmp_path: Path) -> None:
    leitor = _csv(tmp_path, ["contato"], [[gerar_email(RNG)]])
    assert analisar(leitor, "x.csv").risco is Risco.MEDIO


def test_risco_medio_so_com_telefone(tmp_path: Path) -> None:
    leitor = _csv(tmp_path, ["contato"], [[gerar_telefone(RNG, celular=True, formatado=True)]])
    assert analisar(leitor, "x.csv").risco is Risco.MEDIO


def test_risco_baixo_so_com_cnpj(tmp_path: Path) -> None:
    cnpj = gerar_cnpj(RNG, alfanumerico=False, formatado=True)
    leitor = _csv(tmp_path, ["empresa"], [[cnpj]])
    analise = analisar(leitor, "x.csv")
    assert analise.risco is Risco.BAIXO


def test_risco_nenhum_sem_dados(tmp_path: Path) -> None:
    leitor = _csv(tmp_path, ["a", "b"], [["x", "y"], ["z", ""]])
    analise = analisar(leitor, "x.csv")
    assert analise.risco is Risco.NENHUM
    assert analise.colunas == []
    assert analise.linhas == 2


def test_risco_nenhum_com_so_suspeitas(tmp_path: Path) -> None:
    celulas = [_cpf_sem_ddd()] + ["texto"] * 9
    leitor = _csv(tmp_path, ["col7"], [[c] for c in celulas])
    analise = analisar(leitor, "x.csv")
    assert analise.colunas[0].suspeitas == 1
    assert analise.risco is Risco.NENHUM


def test_cpf_alta_pesa_mais_que_email(tmp_path: Path) -> None:
    leitor = _csv(tmp_path, ["a", "b"], [[gerar_email(RNG), gerar_cpf(RNG, formatado=True)]])
    assert analisar(leitor, "x.csv").risco is Risco.ALTO


def test_colunas_duplicadas_geram_duas_linhas(tmp_path: Path) -> None:
    fone = gerar_telefone(RNG, celular=True, formatado=True)
    leitor = _csv(tmp_path, ["telefone", "telefone"], [[fone, fone]])
    analise = analisar(leitor, "x.csv")
    assert [(c.indice_coluna, c.coluna) for c in analise.colunas] == [
        (0, "telefone"),
        (1, "telefone"),
    ]


def test_colunas_ordenadas_por_indice_e_tipo(tmp_path: Path) -> None:
    texto = f"{gerar_email(RNG)} {gerar_cpf(RNG, formatado=True)}"
    leitor = _csv(tmp_path, ["obs", "email"], [[texto, gerar_email(RNG)]])
    analise = analisar(leitor, "x.csv")
    chaves = [(c.indice_coluna, c.tipo.value) for c in analise.colunas]
    assert chaves == [(0, "cpf"), (0, "email"), (1, "email")]
    assert chaves == sorted(chaves)


def test_amostra_e_a_primeira_ocorrencia_ja_mascarada(tmp_path: Path) -> None:
    primeiro = gerar_cpf(RNG, formatado=True)
    segundo = gerar_cpf(RNG, formatado=True)
    leitor = _csv(tmp_path, ["cpf"], [[f"cliente {primeiro}"], [segundo]])
    linha = analisar(leitor, "x.csv").colunas[0]
    assert linha.amostra == mascarar(primeiro, Tipo.CPF)
    assert primeiro not in linha.amostra
    assert linha.contam == 2


def test_amostra_vem_da_primeira_ocorrencia_mesmo_que_seja_suspeita(tmp_path: Path) -> None:
    suspeita = _cpf_sem_ddd()
    leitor = _csv(tmp_path, ["col7"], [[suspeita]] + [["texto"]] * 9)
    linha = analisar(leitor, "x.csv").colunas[0]
    assert linha.suspeitas == 1
    assert linha.amostra == mascarar(suspeita, Tipo.CPF)


def test_confianca_predominante(tmp_path: Path) -> None:
    formatado = gerar_cpf(RNG, formatado=True)
    # 1 ALTA (formatado) e 3 MEDIA que contam: predomina MEDIA.
    mais_medias = _csv(tmp_path, ["col7"], [[formatado]] + [[_cpf_sem_ddd()] for _ in range(3)])
    assert analisar(mais_medias, "x.csv").colunas[0].confianca is Confianca.MEDIA
    # 3 ALTA e 1 MEDIA: predomina ALTA.
    mais_altas = _csv(
        tmp_path,
        ["col7"],
        [[gerar_cpf(RNG, formatado=True)] for _ in range(3)] + [[_cpf_sem_ddd()]],
    )
    assert analisar(mais_altas, "x.csv").colunas[0].confianca is Confianca.ALTA
    # Empate favorece ALTA (altas >= médias que contam).
    empate = _csv(tmp_path, ["col7"], [[formatado], [_cpf_sem_ddd()]])
    assert analisar(empate, "x.csv").colunas[0].confianca is Confianca.ALTA


def test_ambiguo_propaga_para_a_linha(tmp_path: Path) -> None:
    leitor = _csv(tmp_path, ["obs"], [[_cpf_e_telefone()]])
    analise = analisar(leitor, "x.csv")
    linha = _linha(analise, Tipo.CPF)
    assert linha.ambiguo
    assert linha.confianca is Confianca.MEDIA
    assert linha.contam == 1  # 1 de 1 célula: passa da maioria
    leitor = _csv(tmp_path, ["telefone"], [[_cpf_e_telefone()]])
    assert not _linha(analisar(leitor, "x.csv"), Tipo.TELEFONE).ambiguo


def test_analisar_le_o_arquivo_numa_unica_passagem(tmp_path: Path) -> None:
    leitor = _csv(tmp_path, ["cpf"], [[_cpf_sem_ddd()] for _ in range(5)])
    chamadas = 0
    original = leitor.linhas

    def contada() -> Iterator[list[str]]:
        nonlocal chamadas
        chamadas += 1
        return original()

    leitor.linhas = contada  # type: ignore[method-assign]
    analisar(leitor, "x.csv")
    assert chamadas == 1


# --------------------------------------------- ambíguos: formato e maioria da coluna


def test_telefone_formatado_vence_cpf_sem_mascara_sem_contexto() -> None:
    texto = "+55 " + _cpf_e_telefone()
    achados = classificar_celula(texto, "obs")
    assert [(a.ocorrencia.tipo, a.confianca, a.ambiguo, a.alternativa) for a in achados] == [
        (Tipo.TELEFONE, Confianca.ALTA, False, None)
    ]


def test_telefone_formatado_em_parenteses_nao_se_sobrepoe_a_cpf() -> None:
    # Não há como sobrepor: o CPF exige 11 dígitos seguidos ou a máscara 000.000.000-00.
    rng = random.Random(1)
    for _ in range(2000):
        telefone = gerar_telefone(rng, celular=True, formatado=True)
        assert not detectar_cpf(telefone)
        assert [a.ocorrencia.tipo for a in classificar_celula(telefone, "obs")] == [Tipo.TELEFONE]


def test_ambiguo_guarda_o_telefone_descartado_como_alternativa() -> None:
    numero = _cpf_e_telefone()
    (achado,) = classificar_celula(numero, "obs")
    assert achado.ambiguo
    assert achado.alternativa is not None
    assert achado.alternativa.tipo is Tipo.TELEFONE
    assert (achado.alternativa.inicio, achado.alternativa.fim) == (0, len(numero))
    (firme,) = classificar_celula(numero, "telefone")
    assert firme.alternativa is None


def _mil_celulares(tmp_path: Path) -> LeitorCsv:
    rng = random.Random(5)
    celulas = [gerar_telefone(rng, celular=True, formatado=False) for _ in range(1000)]
    return _csv(tmp_path, ["contato"], [[c] for c in celulas])


def test_coluna_de_celulares_resolve_os_ambiguos_como_telefone(tmp_path: Path) -> None:
    leitor = _mil_celulares(tmp_path)
    # Pré-condição: alguns celulares também passam no DV do CPF e saem ambíguos.
    ambiguos = [
        a for linha in leitor.linhas() for a in classificar_celula(linha[0], "contato") if a.ambiguo
    ]
    assert len(ambiguos) > 0
    analise = analisar(leitor, "x.csv")
    assert [c.tipo for c in analise.colunas] == [Tipo.TELEFONE]  # nenhuma linha CPF
    linha = analise.colunas[0]
    assert (linha.contam, linha.suspeitas, linha.ambiguo) == (1000, 0, True)
    assert linha.pct_preenchidas == pytest.approx(100.0)
    assert analise.ambiguos_como_telefone == frozenset({0})
    assert analise.risco is Risco.MEDIO
    primeiro = ambiguos[0]
    assert conta(primeiro, 0, analise)
    efetiva = efetivo(primeiro, 0, analise)
    assert efetiva.tipo is Tipo.TELEFONE
    assert efetiva == primeiro.alternativa


def test_efetivo_devolve_o_cpf_quando_a_coluna_nao_vira_telefone() -> None:
    (achado,) = classificar_celula(_cpf_e_telefone(), "obs")
    vazia = Analise("a.csv", 0, [], Risco.NENHUM, frozenset())
    assert efetivo(achado, 0, vazia) == achado.ocorrencia
    assert not conta(achado, 0, vazia)


def test_obs_minoritaria_com_ambiguos_continua_cpf_suspeito(tmp_path: Path) -> None:
    celulas = [_cpf_e_telefone() for _ in range(3)] + ["texto"] * 17
    analise = analisar(_csv(tmp_path, ["obs"], [[c] for c in celulas]), "x.csv")
    assert [c.tipo for c in analise.colunas] == [Tipo.CPF]
    linha = analise.colunas[0]
    assert (linha.contam, linha.suspeitas, linha.ambiguo) == (0, 3, True)
    assert analise.ambiguos_como_telefone == frozenset()
    assert analise.risco is Risco.NENHUM


def test_coluna_so_de_ambiguos_nao_resolve_por_falta_de_telefone_firme(tmp_path: Path) -> None:
    celulas = [_cpf_e_telefone() for _ in range(10)]
    analise = analisar(_csv(tmp_path, ["obs"], [[c] for c in celulas]), "x.csv")
    assert [c.tipo for c in analise.colunas] == [Tipo.CPF]
    assert analise.colunas[0].contam == 10
    assert analise.ambiguos_como_telefone == frozenset()


def test_codigo_pedido_continua_sem_telefone(tmp_path: Path) -> None:
    celulas = [_cpf_sem_ddd() for _ in range(10)] + [_nao_cpf_sem_ddd() for _ in range(90)]
    analise = analisar(_csv(tmp_path, ["codigo_pedido"], [[c] for c in celulas]), "x.csv")
    assert [c.tipo for c in analise.colunas] == [Tipo.CPF]
    assert analise.ambiguos_como_telefone == frozenset()


def test_nenhum_valor_original_aparece_na_analise(tmp_path: Path) -> None:
    valores = [
        gerar_cpf(RNG, formatado=True),
        gerar_cpf(RNG, formatado=False),
        gerar_email(RNG),
        gerar_telefone(RNG, celular=True, formatado=True),
        gerar_cnpj(RNG, alfanumerico=True, formatado=True),
        _cpf_e_telefone(),
    ]
    leitor = _csv(tmp_path, ["a", "b", "obs"], [valores[:3], valores[3:], valores[::2]])
    texto = repr(analisar(leitor, "x.csv"))
    for valor in valores:
        assert valor not in texto


# ------------------------------------------- fronteiras da resolução dos ambíguos


def _conflitos(quantos: int) -> list[str]:
    """Números distintos que são CPF válido e celular válido ao mesmo tempo."""
    rng = random.Random(3)
    achados: list[str] = []
    while len(achados) < quantos:
        numero = gerar_cpf(rng, formatado=False)
        if detectar_telefone(numero) and numero not in achados:
            achados.append(numero)
    return achados


def _fone() -> str:
    return gerar_telefone(RNG, celular=True, formatado=True)


def _obs(tmp_path: Path, celulas: list[str]) -> Analise:
    return analisar(_csv(tmp_path, ["obs"], [[c] for c in celulas]), "x.csv")


def test_ambiguo_e_telefone_firme_na_mesma_celula_nao_passam_de_100_por_cento(
    tmp_path: Path,
) -> None:
    (conflito,) = _conflitos(1)
    analise = _obs(tmp_path, [f"{conflito} {_fone()}", _fone(), _fone(), _fone()])
    assert analise.ambiguos_como_telefone == frozenset({0})
    (linha,) = analise.colunas
    assert linha.tipo is Tipo.TELEFONE
    assert linha.pct_preenchidas == pytest.approx(100.0)
    assert linha.contam == 5  # 4 telefones firmes + 1 ambíguo


def test_dois_ambiguos_na_mesma_celula_somam_dois(tmp_path: Path) -> None:
    primeiro, segundo = _conflitos(2)
    analise = _obs(tmp_path, [f"{primeiro} {segundo}", _fone(), _fone(), _fone()])
    assert analise.ambiguos_como_telefone == frozenset({0})
    (linha,) = analise.colunas
    assert (linha.tipo, linha.contam) == (Tipo.TELEFONE, 5)  # 3 firmes + 2 ambíguos


def test_fronteira_da_perna_do_telefone_exatos_50_por_cento_resolve(tmp_path: Path) -> None:
    (conflito,) = _conflitos(1)
    no_limite = _obs(tmp_path, [conflito, *[_fone() for _ in range(4)], *["texto"] * 3])
    assert no_limite.ambiguos_como_telefone == frozenset({0})  # 4 de 8
    abaixo = _obs(tmp_path, [conflito, *[_fone() for _ in range(3)], *["texto"] * 4])
    assert abaixo.ambiguos_como_telefone == frozenset()  # 3 de 8
    assert {c.tipo for c in abaixo.colunas} == {Tipo.CPF, Tipo.TELEFONE}


def test_perna_do_cpf_telefone_e_cpf_com_50_por_cento_nao_resolve(tmp_path: Path) -> None:
    primeiro, segundo = _conflitos(2)
    analise = _obs(tmp_path, [primeiro, segundo, _fone(), _fone()])
    assert analise.ambiguos_como_telefone == frozenset()  # telefone 2/4 e CPF 2/4
    assert {c.tipo for c in analise.colunas} == {Tipo.CPF, Tipo.TELEFONE}


# --------------------------------- contrato com o anonymize: conta() e efetivo()


def test_contagem_por_conta_e_efetivo_bate_com_analisar(tmp_path: Path) -> None:
    rng = random.Random(11)  # local ao teste: não depende da ordem dos outros testes
    conflitos = _conflitos(6)
    cabecalho = ["contato", "obs", "col7", "empresa"]
    linhas: list[list[str]] = []
    for _ in range(300):
        contato = rng.choice(conflitos) if rng.random() < 0.05 else ""
        if not contato and rng.random() < 0.9:
            contato = gerar_telefone(rng, celular=True, formatado=False)
        sorteio = rng.random()
        if sorteio < 0.10:
            obs = rng.choice(conflitos)
        elif sorteio < 0.15:
            obs = f"{gerar_email(rng)} {gerar_telefone(rng, celular=True, formatado=True)}"
        else:
            obs = "texto"
        col7 = _cpf_sem_ddd_com(rng) if rng.random() < 0.8 else "sem dado"
        empresa = gerar_cnpj(rng, alfanumerico=False, formatado=rng.random() < 0.5)
        linhas.append([contato, obs, col7, empresa])
    leitor = _csv(tmp_path, cabecalho, linhas)
    analise = analisar(leitor, "x.csv")

    # Os cenários realmente aconteceram.
    assert analise.ambiguos_como_telefone
    assert any(c.suspeitas > 0 for c in analise.colunas)
    assert analise.media_conta

    contagem: Counter[tuple[int, Tipo]] = Counter()
    ingenua: Counter[tuple[int, Tipo]] = Counter()  # reconta sem efetivo(): deve divergir
    for linha in leitor.linhas():
        for indice, texto in enumerate(linha):
            for achado in classificar_celula(texto, cabecalho[indice]):
                if conta(achado, indice, analise):
                    contagem[(indice, efetivo(achado, indice, analise).tipo)] += 1
                    ingenua[(indice, achado.ocorrencia.tipo)] += 1
    esperado = {(c.indice_coluna, c.tipo): c.contam for c in analise.colunas if c.contam}
    assert dict(contagem) == esperado
    assert dict(ingenua) != esperado


def _cpf_sem_ddd_com(rng: random.Random) -> str:
    while True:
        numero = gerar_cpf(rng, formatado=False)
        if numero.startswith("20"):
            return numero
