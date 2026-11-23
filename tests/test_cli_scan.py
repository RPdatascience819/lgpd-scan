"""Testes do comando `scan`: códigos de saída, erros, --output e saída no Windows."""

import json
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

from lgpd_scan._sinteticos import gerar_cnpj, gerar_cpf, gerar_email, gerar_telefone
from lgpd_scan.cli import main

RNG = random.Random(10)


def _csv(caminho: Path, cabecalho: str, linhas: list[str]) -> Path:
    caminho.write_text("\n".join([cabecalho, *linhas]) + "\n", encoding="utf-8")
    return caminho


def _so_cnpj(pasta: Path) -> Path:
    linhas = [gerar_cnpj(RNG, alfanumerico=False, formatado=True) for _ in range(5)]
    return _csv(pasta / "cnpj.csv", "cnpj", linhas)


def _com_cpf(pasta: Path) -> Path:
    linhas = [gerar_cpf(RNG, formatado=True) for _ in range(5)]
    return _csv(pasta / "cpf.csv", "cpf", linhas)


def test_so_cnpj_sai_com_0(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["scan", str(_so_cnpj(tmp_path))]) == 0
    assert "risco BAIXO" in capsys.readouterr().out


def test_so_suspeitas_sai_com_0(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    linhas = [gerar_cpf(RNG, formatado=False), "abc", "def", "ghi", "jkl", "mno"]
    arquivo = _csv(tmp_path / "suspeita.csv", "codigo", linhas)
    assert main(["scan", str(arquivo)]) == 0
    saida = capsys.readouterr().out
    assert "(suspeita)" in saida
    assert "risco NENHUM" in saida


def test_arquivo_sem_achados_sai_com_0(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    arquivo = _csv(tmp_path / "vazio.csv", "nome", ["ana", "bruno"])
    assert main(["scan", str(arquivo)]) == 0
    assert "Nenhum dado pessoal encontrado." in capsys.readouterr().out


def test_cpf_formatado_sai_com_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["scan", str(_com_cpf(tmp_path))]) == 1
    assert "risco ALTO" in capsys.readouterr().out


def test_email_ou_telefone_sai_com_1(tmp_path: Path) -> None:
    emails = _csv(tmp_path / "e.csv", "email", [gerar_email(RNG) for _ in range(4)])
    fones = _csv(
        tmp_path / "t.csv",
        "telefone",
        [gerar_telefone(RNG, celular=True, formatado=True) for _ in range(4)],
    )
    assert main(["scan", str(emails)]) == 1
    assert main(["scan", str(fones)]) == 1


def test_sem_arquivo_e_erro_de_uso_com_2() -> None:
    with pytest.raises(SystemExit) as saida:
        main(["scan"])
    assert saida.value.code == 2


def test_sem_subcomando_e_erro_de_uso_com_2() -> None:
    with pytest.raises(SystemExit) as saida:
        main([])
    assert saida.value.code == 2


def test_formato_desconhecido_e_erro_de_uso_com_2(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as saida:
        main(["scan", str(_so_cnpj(tmp_path)), "--format", "xml"])
    assert saida.value.code == 2


def test_arquivo_inexistente_da_2_com_erro_em_portugues(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["scan", str(tmp_path / "nao_existe.csv")]) == 2
    captura = capsys.readouterr()
    assert captura.out == ""
    assert captura.err.startswith("lgpd-scan: erro: ")
    assert "não encontrado" in captura.err
    assert "Traceback" not in captura.err


def test_diretorio_no_lugar_do_arquivo_da_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["scan", str(tmp_path)]) == 2
    captura = capsys.readouterr()
    assert captura.err.startswith("lgpd-scan: erro: ")
    assert "Traceback" not in captura.err


def test_erro_de_leitura_da_2_sem_conteudo_de_celula(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cpf = gerar_cpf(RNG, formatado=True)
    arquivo = _csv(tmp_path / "a.csv", "cpf", [cpf])
    assert main(["scan", str(arquivo), "--delimiter", "ab"]) == 2
    captura = capsys.readouterr()
    assert captura.err.startswith("lgpd-scan: erro: ")
    assert "delimitador" in captura.err
    assert cpf not in captura.err + captura.out


def test_encoding_invalido_da_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["scan", str(_so_cnpj(tmp_path)), "--encoding", "nao-existe"]) == 2
    assert "codificação não suportada" in capsys.readouterr().err


def test_json_com_output_grava_o_arquivo_e_nao_imprime(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destino = tmp_path / "r.json"
    codigo = main(["scan", str(_com_cpf(tmp_path)), "--format", "json", "--output", str(destino)])
    assert codigo == 1
    assert capsys.readouterr().out == ""
    dados = json.loads(destino.read_text(encoding="utf-8"))
    assert dados["schema_version"] == 1
    assert dados["risco"] == "alto"


def test_json_no_stdout_sem_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["scan", str(_com_cpf(tmp_path)), "--format", "json"]) == 1
    assert json.loads(capsys.readouterr().out)["colunas"][0]["tipo"] == "cpf"


def test_output_sobrescreve_arquivo_existente(tmp_path: Path) -> None:
    destino = tmp_path / "r.txt"
    destino.write_text("velho", encoding="utf-8")
    main(["scan", str(_so_cnpj(tmp_path)), "--output", str(destino)])
    assert "velho" not in destino.read_text(encoding="utf-8")


def test_tabela_com_output_grava_a_amostra_inteira_sem_reticencias(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    email = "a" * 40 + "@exemplo.com"
    arquivo = _csv(tmp_path / "longo.csv", "email_do_cliente", [email, email])
    destino = tmp_path / "r.txt"
    assert main(["scan", str(arquivo), "--output", str(destino)]) == 1
    assert capsys.readouterr().out == ""
    texto = destino.read_text(encoding="utf-8")
    assert "a" + "*" * 39 + "@exemplo.com" in texto
    assert "…" not in texto


def test_output_igual_a_entrada_da_2_e_nao_toca_no_arquivo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    entrada = _com_cpf(tmp_path)
    antes = entrada.read_bytes()
    assert main(["scan", str(entrada), "--output", str(entrada)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("lgpd-scan: erro: ")
    assert "entrada" in err
    assert entrada.read_bytes() == antes


def test_output_com_outra_grafia_do_mesmo_caminho_tambem_da_2(tmp_path: Path) -> None:
    entrada = _com_cpf(tmp_path)
    antes = entrada.read_bytes()
    outra_grafia = tmp_path / ".." / tmp_path.name / entrada.name
    assert main(["scan", str(entrada), "--output", str(outra_grafia)]) == 2
    assert entrada.read_bytes() == antes
    if os.name == "nt":  # o Windows ignora maiúsculas e minúsculas no caminho
        assert main(["scan", str(entrada), "--output", str(entrada).upper()]) == 2
        assert entrada.read_bytes() == antes


def test_output_em_pasta_inexistente_da_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destino = tmp_path / "nao_existe" / "r.txt"
    assert main(["scan", str(_so_cnpj(tmp_path)), "--output", str(destino)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("lgpd-scan: erro: ")
    assert "Traceback" not in err


def test_colunas_com_o_mesmo_nome_aparecem_separadas_no_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    linhas = [
        f"{gerar_cpf(RNG, formatado=True)},{gerar_cpf(RNG, formatado=True)}" for _ in range(3)
    ]
    arquivo = _csv(tmp_path / "dup.csv", "cpf,cpf", linhas)
    assert main(["scan", str(arquivo), "--format", "json"]) == 1
    colunas = json.loads(capsys.readouterr().out)["colunas"]
    assert [(c["coluna"], c["indice_coluna"]) for c in colunas] == [("cpf", 0), ("cpf", 1)]


def _rodar(arquivo: Path) -> subprocess.CompletedProcess[str]:
    ambiente = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    return subprocess.run(
        [sys.executable, "-m", "lgpd_scan", "scan", str(arquivo)],
        capture_output=True,
        text=True,
        env=ambiente,
        check=False,
    )


def test_cabecalho_com_emoji_em_saida_cp1252_nao_derruba_o_programa(tmp_path: Path) -> None:
    cpf = gerar_cpf(RNG, formatado=True)
    arquivo = _csv(tmp_path / "emoji.csv", "nome,cpf 😀", [f"ana,{cpf}", f"bia,{cpf}"])
    resultado = _rodar(arquivo)
    assert resultado.returncode == 1  # risco, não queda
    assert "Traceback" not in resultado.stderr
    assert "UnicodeEncodeError" not in resultado.stderr
    assert "risco ALTO" in resultado.stdout


def test_so_cnpj_em_saida_cp1252_sai_com_0(tmp_path: Path) -> None:
    resultado = _rodar(_so_cnpj(tmp_path))
    assert resultado.returncode == 0
    assert "Traceback" not in resultado.stderr
