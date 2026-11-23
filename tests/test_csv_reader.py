"""Testes do leitor de CSV. Todo arquivo nasce em `tmp_path`, gravado em bytes."""

import csv
import tracemalloc
from pathlib import Path

import pytest

from lgpd_scan.readers import ErroLeitura, FormatoCsv, LeitorCsv


def _grava(tmp_path: Path, conteudo: bytes, nome: str = "dados.csv") -> Path:
    caminho = tmp_path / nome
    caminho.write_bytes(conteudo)
    return caminho


def _todas(leitor: LeitorCsv) -> list[list[str]]:
    return list(leitor.linhas())


def test_utf8_com_bom_e_virgula(tmp_path: Path) -> None:
    caminho = _grava(tmp_path, b"\xef\xbb\xbfnome,obs\nAna,x\n")
    leitor = LeitorCsv(caminho)
    assert leitor.formato == FormatoCsv("utf-8-sig", ",")
    assert leitor.cabecalho == ["nome", "obs"]
    assert _todas(leitor) == [["Ana", "x"]]


def test_cp1252_com_ponto_e_virgula(tmp_path: Path) -> None:
    caminho = _grava(tmp_path, "nome;obs\nJoaçã;x\n".encode("cp1252"))
    leitor = LeitorCsv(caminho)
    assert leitor.formato == FormatoCsv("cp1252", ";")
    assert _todas(leitor) == [["Joaçã", "x"]]


def test_encoding_e_delimitador_informados(tmp_path: Path) -> None:
    caminho = _grava(tmp_path, "a|b\nJoaçã|2\n".encode("latin-1"))
    leitor = LeitorCsv(caminho, encoding="latin-1", delimitador="|")
    assert leitor.formato == FormatoCsv("latin-1", "|")
    assert _todas(leitor) == [["Joaçã", "2"]]


def test_linha_curta_e_completada(tmp_path: Path) -> None:
    leitor = LeitorCsv(_grava(tmp_path, b"a,b,c\n1,2\n"))
    assert _todas(leitor) == [["1", "2", ""]]


def test_linha_longa_gera_colunas_extras_com_posicao_1_based(tmp_path: Path) -> None:
    leitor = LeitorCsv(_grava(tmp_path, b"a,b,c\n1,2,3,4,5\n6,7\n"))
    assert leitor.cabecalho == ["a", "b", "c", "coluna_4", "coluna_5"]
    assert _todas(leitor) == [["1", "2", "3", "4", "5"], ["6", "7", "", "", ""]]


def test_cabecalho_duplicado_e_preservado(tmp_path: Path) -> None:
    leitor = LeitorCsv(_grava(tmp_path, b"a,a\n1,2\n"))
    assert leitor.cabecalho == ["a", "a"]


def test_campo_de_200_mil_caracteres(tmp_path: Path) -> None:
    grande = "x" * 200_000
    leitor = LeitorCsv(_grava(tmp_path, f"a,b\n{grande},2\n".encode()))
    assert _todas(leitor) == [[grande, "2"]]


def test_arquivo_vazio(tmp_path: Path) -> None:
    leitor = LeitorCsv(_grava(tmp_path, b""))
    assert leitor.cabecalho == []
    assert leitor.formato.delimitador == ","
    assert _todas(leitor) == []


def test_so_cabecalho(tmp_path: Path) -> None:
    leitor = LeitorCsv(_grava(tmp_path, b"a,b\n"))
    assert leitor.cabecalho == ["a", "b"]
    assert _todas(leitor) == []


def test_uma_coluna_so_recua_para_virgula(tmp_path: Path) -> None:
    leitor = LeitorCsv(_grava(tmp_path, b"nome\nAna\nBia\n"))
    assert leitor.formato.delimitador == ","
    assert leitor.cabecalho == ["nome"]
    assert _todas(leitor) == [["Ana"], ["Bia"]]


def test_apostrofos_do_dado_ficam_intactos(tmp_path: Path) -> None:
    leitor = LeitorCsv(_grava(tmp_path, b"nome;obs\nD'Avila;tem 'aspas'\nO'Neil;'a;b'\n"))
    assert leitor.formato.delimitador == ";"
    assert _todas(leitor) == [["D'Avila", "tem 'aspas'", ""], ["O'Neil", "'a", "b'"]]
    assert leitor.cabecalho == ["nome", "obs", "coluna_3"]


def test_espacos_do_dado_ficam_intactos(tmp_path: Path) -> None:
    leitor = LeitorCsv(_grava(tmp_path, b"a, b, c\n1, 2, 3\n"))
    assert leitor.cabecalho == ["a", " b", " c"]
    assert _todas(leitor) == [["1", " 2", " 3"]]


def test_amostra_do_sniff_e_texto_nao_bytes(tmp_path: Path) -> None:
    # Cabecalho com multibyte logo na fronteira de 64 KiB de bytes: nao pode quebrar.
    corpo = "a;b\n" + "ã;1\n" * 30_000
    leitor = LeitorCsv(_grava(tmp_path, corpo.encode()))
    assert leitor.formato == FormatoCsv("utf-8-sig", ";")
    assert len(_todas(leitor)) == 30_000


def test_bytes_invalidos_cp1252_levantam_erro_sem_conteudo(tmp_path: Path) -> None:
    caminho = _grava(tmp_path, b"a,b\nAna,1\nSEGREDO,\x81\n")
    with pytest.raises(ErroLeitura) as info:
        LeitorCsv(caminho)
    mensagem = str(info.value)
    assert "--encoding" in mensagem
    assert "SEGREDO" not in mensagem
    assert "linha 3" in mensagem
    assert info.value.__cause__ is None


def test_encoding_informado_que_falha(tmp_path: Path) -> None:
    caminho = _grava(tmp_path, b"a,b\nAna,\xe7\n")
    with pytest.raises(ErroLeitura, match="linha 2") as info:
        LeitorCsv(caminho, encoding="utf-8")
    assert info.value.__cause__ is None


def test_encoding_desconhecido(tmp_path: Path) -> None:
    with pytest.raises(ErroLeitura, match="xyz"):
        LeitorCsv(_grava(tmp_path, b"a\n"), encoding="xyz")


@pytest.mark.parametrize("delimitador", ["", ";;"])
def test_delimitador_invalido(tmp_path: Path, delimitador: str) -> None:
    with pytest.raises(ErroLeitura, match="delimitador"):
        LeitorCsv(_grava(tmp_path, b"a\n"), delimitador=delimitador)


def test_csv_error_vira_erro_leitura_com_linha(tmp_path: Path) -> None:
    caminho = _grava(tmp_path, b"a,b\n1,2\n" + b"y" * 50 + b",3\n")
    antigo = csv.field_size_limit()
    csv.field_size_limit(10)  # o leitor fixa o limite so na importacao; aqui o reduzimos
    try:
        with pytest.raises(ErroLeitura, match="linha 3") as info:
            LeitorCsv(caminho)
    finally:
        csv.field_size_limit(antigo)
    assert "yyyy" not in str(info.value)
    assert info.value.__cause__ is None


def test_csv_error_em_linhas_tambem_vira_erro_leitura(tmp_path: Path) -> None:
    caminho = _grava(tmp_path, b"a,b\n1,2\n" + b"y" * 50 + b",3\n")
    leitor = LeitorCsv(caminho)
    antigo = csv.field_size_limit()
    csv.field_size_limit(10)
    try:
        with pytest.raises(ErroLeitura, match="linha 3") as info:
            _todas(leitor)
    finally:
        csv.field_size_limit(antigo)
    assert info.value.__cause__ is None


def test_linhas_totalmente_vazias_sao_puladas(tmp_path: Path) -> None:
    leitor = LeitorCsv(_grava(tmp_path, b"a,b\n\n1,2\n\n,\n"))
    assert _todas(leitor) == [["1", "2"], ["", ""]]


def test_linhas_reabre_o_arquivo_a_cada_chamada(tmp_path: Path) -> None:
    leitor = LeitorCsv(_grava(tmp_path, b"a\n1\n2\n"))
    assert _todas(leitor) == _todas(leitor) == [["1"], ["2"]]


def test_mensagens_nunca_contem_texto_de_celula(tmp_path: Path) -> None:
    caminho = _grava(tmp_path, b"nome\nCELULASECRETA\x81\n")
    with pytest.raises(ErroLeitura) as info:
        LeitorCsv(caminho)
    assert "CELULASECRETA" not in str(info.value)


def test_excel_crlf_com_aspas_cai_no_recuo_do_cabecalho(tmp_path: Path) -> None:
    texto = (
        'nome;cpf;obs\r\nJoão Ávila;123;"tem; ponto e vírgula"\r\n'
        'Maria D\'Ávila;;"linha\r\nquebrada"\r\n'
    )
    leitor = LeitorCsv(_grava(tmp_path, texto.encode("cp1252")))
    assert leitor.formato == FormatoCsv("cp1252", ";")
    assert leitor.cabecalho == ["nome", "cpf", "obs"]
    assert _todas(leitor) == [
        ["João Ávila", "123", "tem; ponto e vírgula"],
        ["Maria D'Ávila", "", "linha\r\nquebrada"],
    ]


def test_cabecalho_sem_candidato_devolve_virgula(tmp_path: Path) -> None:
    # Sniffer falha (CRLF + aspas); o cabeçalho não tem nenhum delimitador candidato.
    leitor = LeitorCsv(_grava(tmp_path, b'nome\r\n"a;b"\r\n"c\r\nd"\r\n'))
    assert leitor.formato.delimitador == ","


def test_sniffer_que_acerta_continua_igual(tmp_path: Path) -> None:
    leitor = LeitorCsv(_grava(tmp_path, b"a|b|c\n1|2|3\n4|5|6\n"))
    assert leitor.formato.delimitador == "|"


def test_utf16_pela_marca_de_ordem_de_bytes(tmp_path: Path) -> None:
    leitor = LeitorCsv(_grava(tmp_path, "nome\tcpf\r\nJoão\t1\r\n".encode("utf-16")))
    assert leitor.formato == FormatoCsv("utf-16", "\t")
    assert leitor.cabecalho == ["nome", "cpf"]
    assert _todas(leitor) == [["João", "1"]]


@pytest.mark.parametrize("delimitador", ['"', "\n", "\r"])
def test_delimitador_recusado_pelo_csv_vira_erro_leitura(tmp_path: Path, delimitador: str) -> None:
    with pytest.raises(ErroLeitura, match="delimitador") as info:
        LeitorCsv(_grava(tmp_path, b"a\n"), delimitador=delimitador)
    assert info.value.__cause__ is None


def test_espaco_continua_aceito_como_delimitador(tmp_path: Path) -> None:
    leitor = LeitorCsv(_grava(tmp_path, b"a b\n1 2\n"), delimitador=" ")
    assert leitor.cabecalho == ["a", "b"]


def test_erro_de_codificacao_em_arquivo_grande_usa_pouca_memoria(tmp_path: Path) -> None:
    linha = b"abcdefghij,0123456789,Ana Bia\n"  # 30 bytes
    n = 700_000  # ~21 MB
    caminho = _grava(tmp_path, linha * (n - 1) + b"x,\x81\n")
    tracemalloc.start()
    try:
        with pytest.raises(ErroLeitura) as info:
            LeitorCsv(caminho)
        pico = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert f"linha {n}" in str(info.value)
    assert pico < 8 * 1024 * 1024


def test_numero_da_linha_com_multibyte_atravessando_blocos(tmp_path: Path) -> None:
    # Linhas com "ã" (2 bytes em UTF-8) cruzam a fronteira de bloco em posições variadas.
    linha = "ãb,ç\n".encode()
    n = (3 * (1 << 20)) // len(linha) + 7
    caminho = _grava(tmp_path, linha * n + b"\xff\n")
    with pytest.raises(ErroLeitura) as info:
        LeitorCsv(caminho, encoding="utf-8")
    assert f"linha {n + 1}" in str(info.value)
