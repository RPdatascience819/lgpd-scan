"""Testes do relatório (tabela Rich e JSON). Dados só sintéticos."""

import io
import json

from rich.console import Console

from lgpd_scan.detectors.base import Tipo
from lgpd_scan.report import renderizar_json, renderizar_tabela
from lgpd_scan.scoring import Analise, Confianca, LinhaRelatorio, Risco

CHAVES_ANALISE = ["schema_version", "arquivo", "linhas", "risco", "colunas"]
CHAVES_COLUNA = [
    "coluna",
    "indice_coluna",
    "tipo",
    "contam",
    "suspeitas",
    "pct_preenchidas",
    "confianca",
    "amostra",
    "ambiguo",
]


def _linha(**campos: object) -> LinhaRelatorio:
    base: dict[str, object] = {
        "indice_coluna": 0,
        "coluna": "cpf",
        "tipo": Tipo.CPF,
        "contam": 998,
        "suspeitas": 0,
        "pct_preenchidas": 99.84,
        "confianca": Confianca.ALTA,
        "amostra": "***.172.244-**",
        "ambiguo": False,
    }
    base.update(campos)
    return LinhaRelatorio(**base)  # type: ignore[arg-type]


def _analise(*colunas: LinhaRelatorio, linhas: int = 1000, risco: Risco = Risco.ALTO) -> Analise:
    return Analise(
        arquivo="clientes.csv",
        linhas=linhas,
        colunas=list(colunas),
        risco=risco,
        media_conta=frozenset(),
    )


def _tabela(analise: Analise, largura: int = 200) -> str:
    buffer = io.StringIO()
    renderizar_tabela(analise, Console(file=buffer, width=largura, force_terminal=False))
    return buffer.getvalue()


def test_json_tem_as_chaves_e_os_tipos_do_esquema_v1() -> None:
    dados = json.loads(renderizar_json(_analise(_linha())))
    assert list(dados) == CHAVES_ANALISE
    assert dados["schema_version"] == 1
    assert dados["arquivo"] == "clientes.csv"
    assert dados["linhas"] == 1000
    assert dados["risco"] == "alto"
    (coluna,) = dados["colunas"]
    assert list(coluna) == CHAVES_COLUNA
    assert coluna["coluna"] == "cpf"
    assert coluna["indice_coluna"] == 0
    assert coluna["tipo"] == "cpf"
    assert coluna["contam"] == 998
    assert coluna["suspeitas"] == 0
    assert isinstance(coluna["pct_preenchidas"], float)
    assert coluna["confianca"] == "alta"
    assert coluna["amostra"] == "***.172.244-**"
    assert coluna["ambiguo"] is False


def test_json_arredonda_pct_preenchidas_a_uma_casa() -> None:
    dados = json.loads(renderizar_json(_analise(_linha(pct_preenchidas=99.84999))))
    assert dados["colunas"][0]["pct_preenchidas"] == 99.8


def test_json_e_ascii_puro_e_devolve_nome_acentuado_intacto() -> None:
    saida = renderizar_json(_analise(_linha(coluna="situação 😀")))
    assert saida.isascii()
    assert json.loads(saida)["colunas"][0]["coluna"] == "situação 😀"


def test_json_sem_achados_tem_lista_vazia() -> None:
    dados = json.loads(renderizar_json(_analise(risco=Risco.NENHUM)))
    assert dados["colunas"] == []
    assert dados["risco"] == "nenhum"


def test_tabela_tem_o_titulo_com_milhar_em_ponto_e_risco_em_maiusculas() -> None:
    saida = _tabela(_analise(_linha()))
    assert saida.splitlines()[0] == "LGPD-Scan · clientes.csv · 1.000 linhas · risco ALTO"


def test_tabela_tem_as_colunas_do_design_e_percentual_com_virgula() -> None:
    saida = _tabela(_analise(_linha()))
    cabecalho = next(linha for linha in saida.splitlines() if "Coluna" in linha)
    ordem = ["Coluna", "Tipo", "Contam", "Suspeitas", "% preench.", "Confiança", "Amostra"]
    posicoes = [cabecalho.index(nome) for nome in ordem]
    assert posicoes == sorted(posicoes)
    assert "99,8" in saida
    assert "99.8" not in saida
    assert "***.172.244-**" in saida
    assert "CPF" in saida


def test_tabela_mostra_a_nota_so_quando_ha_suspeitas() -> None:
    sem = _tabela(_analise(_linha()))
    com = _tabela(_analise(_linha(contam=0, suspeitas=3, confianca=Confianca.MEDIA)))
    nota = "Suspeitas não entram no risco. Use --incluir-suspeitas no anonymize para mascará-las."
    assert nota not in sem
    assert nota in com


def test_tabela_marca_a_linha_de_suspeita_e_a_ambigua() -> None:
    suspeita = _linha(coluna="codigo", contam=0, suspeitas=10, confianca=Confianca.MEDIA)
    ambigua = _linha(coluna="contato", tipo=Tipo.TELEFONE, ambiguo=True)
    saida = _tabela(_analise(suspeita, ambigua))
    linha_suspeita = next(linha for linha in saida.splitlines() if "codigo" in linha)
    linha_ambigua = next(linha for linha in saida.splitlines() if "contato" in linha)
    assert "(suspeita)" in linha_suspeita
    assert "(suspeita)" not in linha_ambigua
    assert "(amb.)" in linha_ambigua
    assert "(amb.)" not in linha_suspeita


def test_tabela_sem_achados_diz_que_nada_foi_encontrado() -> None:
    saida = _tabela(_analise(risco=Risco.NENHUM))
    assert "Nenhum dado pessoal encontrado." in saida
    assert "Coluna" not in saida


def test_tabela_nao_interpreta_markup_nem_emoji_do_nome_da_coluna() -> None:
    saida = _tabela(_analise(_linha(coluna="[bold]x[/bold] :smile:")))
    assert "[bold]x[/bold] :smile:" in saida


def test_tabela_nao_trunca_com_reticencias_em_console_estreito() -> None:
    longa = _linha(
        coluna="uma_coluna_com_nome_bem_comprido", amostra="m" + "*" * 30 + "@exemplo.com"
    )
    saida = _tabela(_analise(longa), largura=60)
    assert "…" not in saida
    assert saida.count("*") == 30  # a amostra inteira está lá, só dobrada em várias linhas
