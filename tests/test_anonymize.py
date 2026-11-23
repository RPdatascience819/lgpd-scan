"""Testes do comando `anonymize --mode mask`: máscaras, formato preservado e gravação segura."""

import csv
import errno
import io
import os
import random
import sys
from pathlib import Path

import pytest

from lgpd_scan._sinteticos import gerar_cnpj, gerar_cpf, gerar_email, gerar_telefone
from lgpd_scan.anonymize import ResumoAnonimizacao, _mascarar_celula, anonimizar
from lgpd_scan.cli import main
from lgpd_scan.detectors.base import Ocorrencia, Tipo
from lgpd_scan.detectors.cpf import detectar_cpf
from lgpd_scan.detectors.telefone import detectar_telefone
from lgpd_scan.readers import LeitorCsv
from lgpd_scan.scoring import Achado, Analise, Confianca, Risco, analisar, classificar_celula

RNG = random.Random(11)


def _gravar(caminho: Path, linhas: list[list[str]], *, fim: str = "\n", sep: str = ",") -> Path:
    buffer = io.StringIO(newline="")
    csv.writer(buffer, delimiter=sep, lineterminator=fim).writerows(linhas)
    caminho.write_bytes(buffer.getvalue().encode("utf-8"))
    return caminho


def _ler(caminho: Path, *, sep: str = ",", encoding: str = "utf-8") -> list[list[str]]:
    with open(caminho, encoding=encoding, newline="") as f:
        return list(csv.reader(f, delimiter=sep))


def _cpf_sem_ddd() -> str:
    """CPF sem máscara começando em 20 (DDD inexistente): nunca é telefone."""
    while True:
        numero = gerar_cpf(RNG, formatado=False)
        if numero.startswith("20"):
            return numero


def _nao_cpf_sem_ddd() -> str:
    while True:
        numero = "20" + "".join(RNG.choice("0123456789") for _ in range(9))
        if not detectar_cpf(numero):
            return numero


def _conflitos(quantos: int) -> list[str]:
    """Números distintos que são CPF válido e celular válido ao mesmo tempo."""
    rng = random.Random(3)
    achados: list[str] = []
    while len(achados) < quantos:
        numero = gerar_cpf(rng, formatado=False)
        if detectar_telefone(numero) and numero not in achados:
            achados.append(numero)
    return achados


def _mascara_cpf(cpf: str) -> str:
    return "***" + cpf[3:11] + "-**"


# ------------------------------------------------------------------ máscaras do design


def test_cada_tipo_formatado_vira_a_mascara_do_design(tmp_path: Path) -> None:
    cpf = gerar_cpf(RNG, formatado=True)
    cnpj = gerar_cnpj(RNG, alfanumerico=False, formatado=True)
    email = gerar_email(RNG)
    fone = gerar_telefone(RNG, celular=True, formatado=True)
    entrada = _gravar(
        tmp_path / "e.csv",
        [["cpf", "cnpj", "email", "telefone"], [cpf, cnpj, email, fone]],
    )
    saida = tmp_path / "s.csv"
    assert main(["anonymize", str(entrada), "--output", str(saida)]) == 0
    local, dominio = email.split("@")
    assert _ler(saida) == [
        ["cpf", "cnpj", "email", "telefone"],
        [
            _mascara_cpf(cpf),
            cnpj[:3] + "***.***" + cnpj[10:16] + "**",
            local[0] + "*" * (len(local) - 1) + "@" + dominio,
            fone[:6] + "****" + fone[10:],
        ],
    ]


def test_o_texto_em_volta_do_trecho_e_preservado(tmp_path: Path) -> None:
    cpf = gerar_cpf(RNG, formatado=True)
    entrada = _gravar(tmp_path / "e.csv", [["obs"], [f"cliente {cpf} ligou"]])
    saida = tmp_path / "s.csv"
    assert main(["anonymize", str(entrada), "--output", str(saida)]) == 0
    assert _ler(saida) == [["obs"], [f"cliente {_mascara_cpf(cpf)} ligou"]]


def test_trechos_sobrepostos_usam_a_uniao_das_mascaras(tmp_path: Path) -> None:
    # Telefone [0,13) e e-mail [3,25) se sobrepõem: nenhuma ordem de aplicação pode deixar
    # sobrar um dígito que uma das duas máscaras cobriria.
    entrada = _gravar(tmp_path / "e.csv", [["contato"], ["11 98765-4321@exemplo.com"]])
    saida = tmp_path / "s.csv"
    assert main(["anonymize", str(entrada), "--output", str(saida)]) == 0
    assert _ler(saida) == [["contato"], ["11 9****-****@exemplo.com"]]


@pytest.mark.parametrize("invertida", [False, True])
def test_a_uniao_das_mascaras_nao_depende_da_ordem_das_ocorrencias(
    monkeypatch: pytest.MonkeyPatch, invertida: bool
) -> None:
    # CPF e telefone no mesmo trecho: cada máscara mantém dígitos que a outra esconde. Com a
    # união, só sobram os que as duas mantêm (ordens 7 e 8), seja qual for a ordem.
    texto = "12345678901"
    cpf = Achado(Ocorrencia(Tipo.CPF, 0, 11, False), Confianca.ALTA, False)
    fone = Achado(Ocorrencia(Tipo.TELEFONE, 0, 11, False), Confianca.ALTA, False)
    achados = [fone, cpf] if invertida else [cpf, fone]
    monkeypatch.setattr("lgpd_scan.anonymize.classificar_celula", lambda *_a: achados)
    analise = Analise("x.csv", 0, [], Risco.NENHUM, frozenset())
    novo, tipos = _mascarar_celula(texto, "obs", 0, analise, incluir_suspeitas=False)
    assert novo == "*******89**"
    assert tipos == {Tipo.CPF, Tipo.TELEFONE}


def test_ambiguo_resolvido_como_telefone_sai_com_a_mascara_de_telefone(tmp_path: Path) -> None:
    conflitos = _conflitos(2)
    fones = [gerar_telefone(RNG, celular=True, formatado=True) for _ in range(6)]
    entrada = _gravar(tmp_path / "e.csv", [["obs"], *[[v] for v in [*conflitos, *fones]]])
    saida = tmp_path / "s.csv"
    assert main(["anonymize", str(entrada), "--output", str(saida)]) == 0
    celulas = [linha[0] for linha in _ler(saida)[1:]]
    # Máscara de telefone (DDD, 1º dígito e 4 últimos), e não a de CPF.
    assert celulas[:2] == [n[:3] + "****" + n[7:] for n in conflitos]


# ------------------------------------------------------- a garantia do design (seção 7)


def test_scan_na_saida_nao_acha_nada_que_conte(tmp_path: Path) -> None:
    conflitos = _conflitos(3)
    linhas: list[list[str]] = [["cpf", "cnpj", "email", "telefone", "obs"]]
    for i in range(20):
        formatado = i % 2 == 0
        linhas.append(
            [
                gerar_cpf(RNG, formatado=formatado),
                gerar_cnpj(RNG, alfanumerico=i % 3 == 0, formatado=formatado),
                gerar_email(RNG),
                conflitos[i % 3]
                if i % 5 == 0
                else gerar_telefone(RNG, celular=True, formatado=formatado),
                f"fale com {gerar_telefone(RNG, celular=False, formatado=formatado)}",
            ]
        )
    entrada = _gravar(tmp_path / "e.csv", linhas)
    saida = tmp_path / "s.csv"
    antes = analisar(LeitorCsv(entrada), "e.csv")
    assert any(c.contam and c.confianca.value == "alta" for c in antes.colunas)
    assert main(["anonymize", str(entrada), "--output", str(saida)]) == 0
    depois = analisar(LeitorCsv(saida), "s.csv")
    assert [c for c in depois.colunas if c.contam] == []
    assert not [c for c in depois.colunas if c.contam and c.confianca.value == "alta"]


def test_codigo_pedido_sem_a_flag_nada_muda_e_com_a_flag_os_suspeitos_somem(
    tmp_path: Path,
) -> None:
    suspeitos = [_cpf_sem_ddd() for _ in range(10)]
    celulas = [*suspeitos, *[_nao_cpf_sem_ddd() for _ in range(90)]]
    RNG.shuffle(celulas)
    entrada = _gravar(tmp_path / "e.csv", [["codigo_pedido"], *[[c] for c in celulas]])
    sem_flag = tmp_path / "sem.csv"
    com_flag = tmp_path / "com.csv"
    assert main(["anonymize", str(entrada), "--output", str(sem_flag)]) == 0
    assert sem_flag.read_bytes() == entrada.read_bytes()
    saida = main(["anonymize", str(entrada), "--output", str(com_flag), "--incluir-suspeitas"])
    assert saida == 0
    mascaradas = [linha[0] for linha in _ler(com_flag)[1:]]
    assert not set(suspeitos) & set(mascaradas)
    assert [c for c in mascaradas if "*" in c] == [
        _mascara_cpf_pura(s) for s in celulas if s in suspeitos
    ]
    depois = analisar(LeitorCsv(com_flag), "com.csv")
    assert all(c.suspeitas == 0 for c in depois.colunas)


def _mascara_cpf_pura(cpf: str) -> str:
    return "***" + cpf[3:9] + "**"


# --------------------------------------------------------------- formato preservado


def test_celula_entre_aspas_com_delimitador_e_quebra_de_linha_sobrevive(tmp_path: Path) -> None:
    cpf = gerar_cpf(RNG, formatado=True)
    complicada = f'linha 1; com ponto e vírgula\nlinha 2 {cpf} "entre aspas"'
    entrada = _gravar(tmp_path / "e.csv", [["id", "obs"], ["1", complicada]], sep=";")
    saida = tmp_path / "s.csv"
    assert main(["anonymize", str(entrada), "--output", str(saida)]) == 0
    esperado = complicada.replace(cpf, _mascara_cpf(cpf))
    assert _ler(saida, sep=";") == [["id", "obs"], ["1", esperado]]


def test_cabecalho_delimitador_e_ordem_das_colunas_ficam(tmp_path: Path) -> None:
    cpf = gerar_cpf(RNG, formatado=True)
    entrada = _gravar(tmp_path / "e.csv", [["z", "cpf", "a"], ["x", cpf, "y"]], sep="|")
    saida = tmp_path / "s.csv"
    assert main(["anonymize", str(entrada), "--output", str(saida)]) == 0
    assert saida.read_bytes().splitlines()[0] == b"z|cpf|a"
    assert _ler(saida, sep="|") == [["z", "cpf", "a"], ["x", _mascara_cpf(cpf), "y"]]


def test_cp1252_com_ponto_e_virgula_continua_cp1252_com_ponto_e_virgula(tmp_path: Path) -> None:
    cpf = gerar_cpf(RNG, formatado=True)
    texto = f"nome;cpf;obs\nJoão da Conceição;{cpf};ação\n"
    entrada = tmp_path / "e.csv"
    entrada.write_bytes(texto.encode("cp1252"))
    saida = tmp_path / "s.csv"
    assert main(["anonymize", str(entrada), "--output", str(saida)]) == 0
    linhas = saida.read_bytes().split(b"\n")
    assert linhas[0] == b"nome;cpf;obs"
    assert linhas[1] == f"João da Conceição;{_mascara_cpf(cpf)};ação".encode("cp1252")
    assert b"\xef\xbb\xbf" not in saida.read_bytes()


def test_utf8_com_bom_regrava_o_bom(tmp_path: Path) -> None:
    entrada = tmp_path / "e.csv"
    entrada.write_bytes("nome,obs\nAna,ok\n".encode("utf-8-sig"))
    saida = tmp_path / "s.csv"
    assert main(["anonymize", str(entrada), "--output", str(saida)]) == 0
    assert saida.read_bytes() == entrada.read_bytes()
    assert saida.read_bytes().startswith(b"\xef\xbb\xbf")
    assert not saida.read_bytes().startswith(b"\xef\xbb\xbf\xef\xbb\xbf")


def test_utf8_sem_bom_nao_ganha_bom(tmp_path: Path) -> None:
    # O leitor chama de utf-8-sig todo UTF-8 detectado; a cópia não pode inventar um BOM.
    entrada = tmp_path / "e.csv"
    entrada.write_bytes("nome,obs\nAna,ação\n".encode())
    saida = tmp_path / "s.csv"
    assert main(["anonymize", str(entrada), "--output", str(saida)]) == 0
    assert saida.read_bytes() == entrada.read_bytes()


def test_utf16_continua_utf16(tmp_path: Path) -> None:
    cpf = gerar_cpf(RNG, formatado=True)
    entrada = tmp_path / "e.csv"
    entrada.write_bytes(f"nome,cpf\r\nAna,{cpf}\r\n".encode("utf-16"))
    saida = tmp_path / "s.csv"
    assert main(["anonymize", str(entrada), "--output", str(saida)]) == 0
    assert saida.read_bytes()[:2] in (b"\xff\xfe", b"\xfe\xff")
    assert saida.read_bytes().decode("utf-16") == f"nome,cpf\r\nAna,{_mascara_cpf(cpf)}\r\n"


@pytest.mark.parametrize("fim", ["\n", "\r\n"])
def test_o_final_de_linha_do_arquivo_e_preservado(tmp_path: Path, fim: str) -> None:
    cpf = gerar_cpf(RNG, formatado=True)
    entrada = _gravar(tmp_path / "e.csv", [["a", "cpf"], ["x", cpf], ["y", cpf]], fim=fim)
    saida = tmp_path / "s.csv"
    assert main(["anonymize", str(entrada), "--output", str(saida)]) == 0
    esperado = fim.join(["a,cpf", f"x,{_mascara_cpf(cpf)}", f"y,{_mascara_cpf(cpf)}", ""])
    assert saida.read_bytes() == esperado.encode("utf-8")


def test_arquivo_sem_nada_a_mascarar_grava_a_copia_e_sai_com_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    entrada = _gravar(tmp_path / "e.csv", [["nome", "obs"], ["ana", "ok"], ["bruno", "ok"]])
    saida = tmp_path / "s.csv"
    assert main(["anonymize", str(entrada), "--output", str(saida)]) == 0
    assert saida.read_bytes() == entrada.read_bytes()
    assert "0 célula" in capsys.readouterr().out


def test_comportamento_conhecido_da_tabela_retangular(tmp_path: Path) -> None:
    # Linhas em branco somem, linhas curtas ganham células vazias e colunas a mais ganham
    # `coluna_N`: o leitor entrega uma tabela retangular.
    entrada = tmp_path / "e.csv"
    entrada.write_bytes(b"a,b\n1\n\n2,3,4\n")
    saida = tmp_path / "s.csv"
    assert main(["anonymize", str(entrada), "--output", str(saida)]) == 0
    assert _ler(saida) == [["a", "b", "coluna_3"], ["1", "", ""], ["2", "3", "4"]]


# ---------------------------------------------------------------- cabeçalho sem dados


def test_csv_sem_cabecalho_nao_deixa_valor_original_na_saida(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    primeira = [gerar_cpf(RNG, formatado=True), gerar_email(RNG)]
    linhas = [primeira, *[[gerar_cpf(RNG, formatado=True), gerar_email(RNG)] for _ in range(3)]]
    entrada = _gravar(tmp_path / "e.csv", linhas)
    saida = tmp_path / "s.csv"
    assert main(["anonymize", str(entrada), "--output", str(saida)]) == 0
    texto = saida.read_text(encoding="utf-8")
    for linha in linhas:
        for valor in linha:
            assert valor not in texto
    assert _ler(saida)[0][0] == _mascara_cpf(primeira[0])
    assert "pode não ter cabeçalho" in capsys.readouterr().err


def test_cabecalho_normal_sai_identico_e_sem_aviso(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    entrada = _gravar(tmp_path / "e.csv", [["nome", "e-mail"], ["ana", "x"]])
    saida = tmp_path / "s.csv"
    assert main(["anonymize", str(entrada), "--output", str(saida)]) == 0
    assert saida.read_bytes() == entrada.read_bytes()
    assert capsys.readouterr().err == ""


# ------------------------------------------------------------------- gravação segura


def _dados(pasta: Path, nome: str = "dados.csv") -> Path:
    return _gravar(pasta / nome, [["cpf"], [gerar_cpf(RNG, formatado=True)]])


def test_saida_igual_a_entrada_da_2_e_nao_toca_no_arquivo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    entrada = _dados(tmp_path)
    antes = entrada.read_bytes()
    assert main(["anonymize", str(entrada), "--output", str(entrada)]) == 2
    assert "entrada" in capsys.readouterr().err
    monkeypatch.chdir(tmp_path)  # a mesma entrada por um caminho relativo
    assert main(["anonymize", str(entrada), "--output", "dados.csv", "--force"]) == 2
    assert entrada.read_bytes() == antes


def test_entrada_terminada_em_tmp_nao_e_destruida(tmp_path: Path) -> None:
    entrada = _dados(tmp_path, "dados.csv.tmp")
    antes = entrada.read_bytes()
    saida = tmp_path / "dados.csv"
    assert main(["anonymize", str(entrada), "--output", str(saida)]) == 0
    assert entrada.read_bytes() == antes
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dados.csv", "dados.csv.tmp"]


def test_hardlink_da_entrada_como_saida_da_2(tmp_path: Path) -> None:
    entrada = _dados(tmp_path)
    antes = entrada.read_bytes()
    ligacao = tmp_path / "apelido.csv"
    try:
        os.link(entrada, ligacao)
    except (OSError, NotImplementedError, AttributeError) as erro:
        pytest.skip(f"hardlink não suportado neste sistema: {erro}")
    assert main(["anonymize", str(entrada), "--output", str(ligacao), "--force"]) == 2
    assert entrada.read_bytes() == antes
    assert ligacao.read_bytes() == antes


def test_saida_existente_sem_force_da_2_e_nao_toca_em_nada(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    entrada = _dados(tmp_path)
    saida = tmp_path / "s.csv"
    saida.write_text("anterior", encoding="utf-8")
    assert main(["anonymize", str(entrada), "--output", str(saida)]) == 2
    assert "--force" in capsys.readouterr().err
    assert saida.read_text(encoding="utf-8") == "anterior"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dados.csv", "s.csv"]


def test_saida_existente_com_force_e_sobrescrita(tmp_path: Path) -> None:
    entrada = _dados(tmp_path)
    saida = tmp_path / "s.csv"
    saida.write_text("anterior", encoding="utf-8")
    assert main(["anonymize", str(entrada), "--output", str(saida), "--force"]) == 0
    assert saida.read_text(encoding="utf-8").startswith("cpf\n***.")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dados.csv", "s.csv"]


def test_saida_que_e_diretorio_da_2(tmp_path: Path) -> None:
    entrada = _dados(tmp_path)
    pasta = tmp_path / "pasta"
    pasta.mkdir()
    assert main(["anonymize", str(entrada), "--output", str(pasta), "--force"]) == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dados.csv", "pasta"]


def test_falha_no_meio_da_escrita_preserva_o_destino_e_nao_deixa_temporario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    entrada = _gravar(
        tmp_path / "dados.csv", [["cpf"], *[[gerar_cpf(RNG, formatado=True)] for _ in range(5)]]
    )
    saida = tmp_path / "s.csv"
    saida.write_text("anterior", encoding="utf-8")
    chamadas: list[int] = []

    def quebra_na_terceira(texto: str, nome: str) -> list[Achado]:
        chamadas.append(1)
        if len(chamadas) == 3:
            raise OSError(errno.ENOSPC, "disco cheio simulado")
        return classificar_celula(texto, nome)

    # Só a segunda passagem (a que grava) usa o nome importado em `anonymize`.
    monkeypatch.setattr("lgpd_scan.anonymize.classificar_celula", quebra_na_terceira)
    assert main(["anonymize", str(entrada), "--output", str(saida), "--force"]) == 2
    assert len(chamadas) == 3  # a falha veio no meio, com linhas já gravadas
    assert saida.read_text(encoding="utf-8") == "anterior"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dados.csv", "s.csv"]
    assert "Traceback" not in capsys.readouterr().err


def test_falha_na_troca_remove_o_temporario_e_preserva_o_destino(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def falha(*_a: object, **_k: object) -> None:
        raise PermissionError("troca simulada")

    entrada = _dados(tmp_path)
    saida = tmp_path / "s.csv"
    saida.write_text("anterior", encoding="utf-8")
    monkeypatch.setattr(os, "replace", falha)
    assert main(["anonymize", str(entrada), "--output", str(saida), "--force"]) == 2
    assert saida.read_text(encoding="utf-8") == "anterior"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dados.csv", "s.csv"]


# ------------------------------------------------------------------------- API e CLI


def test_anonimizar_devolve_o_total_de_celulas_alteradas_por_tipo(tmp_path: Path) -> None:
    entrada = _gravar(
        tmp_path / "e.csv",
        [
            ["cpf", "email", "obs"],
            [gerar_cpf(RNG, formatado=True), gerar_email(RNG), "nada"],
            [
                gerar_cpf(RNG, formatado=True),
                gerar_email(RNG),
                f"{gerar_cpf(RNG, formatado=True)} {gerar_email(RNG)}",
            ],
        ],
    )
    resumo = anonimizar(
        entrada,
        tmp_path / "s.csv",
        incluir_suspeitas=False,
        forcar=False,
        encoding=None,
        delimitador=None,
    )
    assert isinstance(resumo, ResumoAnonimizacao)
    assert resumo.celulas_alteradas == {Tipo.CPF: 3, Tipo.EMAIL: 3}


def test_resumo_no_stdout_traz_tipos_e_caminho_sem_valores(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cpf, email = gerar_cpf(RNG, formatado=True), gerar_email(RNG)
    entrada = _gravar(tmp_path / "e.csv", [["cpf", "email"], [cpf, email]])
    saida = tmp_path / "s.csv"
    assert main(["anonymize", str(entrada), "--output", str(saida)]) == 0
    out = capsys.readouterr().out
    assert "2 célula" in out
    assert "cpf: 1" in out
    assert "email: 1" in out
    assert str(saida) in out
    assert cpf not in out
    assert email not in out


def test_output_e_obrigatorio(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as saida:
        main(["anonymize", str(_dados(tmp_path))])
    assert saida.value.code == 2


def test_mode_so_aceita_mask(tmp_path: Path) -> None:
    entrada = _dados(tmp_path)
    assert (
        main(["anonymize", str(entrada), "--output", str(tmp_path / "a.csv"), "--mode", "mask"])
        == 0
    )
    with pytest.raises(SystemExit) as saida:
        main(["anonymize", str(entrada), "--output", str(tmp_path / "b.csv"), "--mode", "hash"])
    assert saida.value.code == 2


def test_ajuda_em_portugues(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as saida:
        main(["anonymize", "--help"])
    assert saida.value.code == 0
    ajuda = capsys.readouterr().out
    assert "cópia anonimizada" in ajuda
    assert "sobrescreve" in ajuda
    assert "--incluir-suspeitas" in ajuda


def test_arquivo_inexistente_da_2_em_portugues(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    saida = tmp_path / "s.csv"
    assert main(["anonymize", str(tmp_path / "nao_existe.csv"), "--output", str(saida)]) == 2
    assert "lgpd-scan: erro: arquivo não encontrado" in capsys.readouterr().err
    assert not saida.exists()


def test_erro_de_leitura_da_2_sem_traceback_e_sem_saida(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    entrada = tmp_path / "e.csv"
    entrada.write_bytes(b"a,b\n\xff\xfe\x81,2\n")
    saida = tmp_path / "s.csv"
    assert main(["anonymize", str(entrada), "--output", str(saida), "--encoding", "utf-8"]) == 2
    erro = capsys.readouterr().err
    assert "lgpd-scan: erro:" in erro
    assert "Traceback" not in erro
    assert not saida.exists()


def test_encoding_e_delimitador_informados_sao_usados(tmp_path: Path) -> None:
    cpf = gerar_cpf(RNG, formatado=True)
    entrada = tmp_path / "e.csv"
    entrada.write_bytes(f"a#cpf\nç#{cpf}\n".encode("latin-1"))
    saida = tmp_path / "s.csv"
    argv = ["anonymize", str(entrada), "--output", str(saida)]
    assert main([*argv, "--encoding", "latin-1", "--delimiter", "#"]) == 0
    assert saida.read_bytes() == f"a#cpf\nç#{_mascara_cpf(cpf)}\n".encode("latin-1")


def test_pipe_fechado_no_resumo_nao_muda_o_codigo_de_saida(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _StdoutQuebrado:
        def __init__(self, fd: int) -> None:
            self._fd = fd

        def write(self, _texto: str) -> int:
            raise BrokenPipeError(errno.EPIPE, "Broken pipe")

        def flush(self) -> None:
            raise BrokenPipeError(errno.EPIPE, "Broken pipe")

        def fileno(self) -> int:
            return self._fd

    entrada = _dados(tmp_path)
    saida = tmp_path / "s.csv"
    fd = os.open(os.devnull, os.O_WRONLY)
    try:
        monkeypatch.setattr(sys, "stdout", _StdoutQuebrado(fd))
        assert main(["anonymize", str(entrada), "--output", str(saida)]) == 0
    finally:
        os.close(fd)
    assert saida.exists()


def test_erro_ao_escrever_o_resumo_da_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class _DiscoCheio:
        def write(self, _texto: str) -> int:
            raise OSError(errno.ENOSPC, "No space left on device")

        def flush(self) -> None:
            raise OSError(errno.ENOSPC, "No space left on device")

    entrada = _dados(tmp_path)
    monkeypatch.setattr(sys, "stdout", _DiscoCheio())
    assert main(["anonymize", str(entrada), "--output", str(tmp_path / "s.csv")]) == 2
    assert "não foi possível escrever a saída" in capsys.readouterr().err
