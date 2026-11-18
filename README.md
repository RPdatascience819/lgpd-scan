# LGPD-Scan

> Encontre dados pessoais brasileiros escondidos em planilhas e bancos, avalie o risco e gere uma versão anonimizada, tudo pela linha de comando.

**Status:** Fase 0, fundação do projeto (qualidade, CI, processo). **Ainda não há
funcionalidade utilizável**: os detectores chegam na Fase 1. Acompanhe pelo
[board](https://github.com/RPdatascience819/lgpd-scan/milestone/1).

## O que ele vai fazer

Planejado, nada disso existe ainda:

- **Detectar** CPF, CNPJ, RG, CEP, telefone, placa de veículo e e-mail;
- **ler** CSV, Excel, Parquet e SQLite;
- **avaliar** a confiança de cada detecção e o nível de risco do arquivo;
- **relatar** no terminal, em JSON ou em HTML;
- **anonimizar** nos modos `mask`, `hash`, `redact` e `drop`.

## Arquitetura (planejada)

```text
arquivo ──► readers/ ──► detectors/ ──► scoring.py ──┬──► report.py     (terminal, JSON, HTML)
                                                    └──► anonymize.py  (mask, hash, redact, drop)
```

Cada módulo está descrito na docstring de [`src/lgpd_scan/__init__.py`](src/lgpd_scan/__init__.py).

## Pré-requisitos

- [git](https://git-scm.com/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/), que instala sozinho o
  Python certo (3.14, fixado em `.python-version`). Versão mínima suportada: **3.11**.

## Rodar localmente

```bash
git clone https://github.com/RPdatascience819/lgpd-scan.git
cd lgpd-scan
uv sync                             # cria .venv com as dependências do uv.lock
uv run pre-commit install           # ativa os hooks de commit e de mensagem
uv run pre-commit run --all-files   # todos os hooks devem terminar em "Passed"
```

Na Fase 0, isso é tudo o que existe para rodar: o projeto ainda não tem código de
aplicação.

## Estrutura

```text
src/lgpd_scan/   código do pacote (a partir da Fase 1)
tests/           testes com pytest
examples/        os ÚNICOS dados versionados, e só sintéticos
docs/adr/        decisões de arquitetura
.github/         CI, Dependabot e template de PR
```

## Dados pessoais

Este é um projeto sobre LGPD num repositório público: **nenhum dado pessoal real**
entra aqui, nem "mascarado". Testes e exemplos usam só valores gerados por código.
Regras completas em [CONTRIBUTING](CONTRIBUTING.md#dados-pessoais-regra-inegociável).

## Processo

- [CONTRIBUTING](CONTRIBUTING.md): fluxo de branches, commits, DoR e DoD
- [Decisões de arquitetura (ADRs)](docs/adr/)
- [Contas e serviços](docs/contas-e-servicos.md)
- [Board da Fase 0](https://github.com/RPdatascience819/lgpd-scan/milestone/1)

## Licença

MIT. Veja [LICENSE](LICENSE).
