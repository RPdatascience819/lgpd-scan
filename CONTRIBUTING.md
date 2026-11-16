# Contribuindo com o LGPD-Scan

Obrigado pelo interesse. Este guia descreve como preparar o ambiente, o fluxo de
trabalho e as regras que todo PR segue. Decisões por trás dessas regras estão em
[`docs/adr/`](docs/adr/).

## Antes de começar

Abra uma *issue* para discutir a ideia antes de enviar um PR. Uma tarefa está
**pronta para começar (DoR)** quando:

- o objetivo cabe em uma ou duas frases;
- o critério de aceite é verificável (um comando, um teste, uma saída esperada);
- dependências de outras tarefas estão resolvidas.

## Ambiente

Pré-requisitos: [git](https://git-scm.com/) e [uv](https://docs.astral.sh/uv/).
O `uv` instala o Python certo sozinho (versão em `.python-version`).

```bash
git clone https://github.com/RPdatascience819/lgpd-scan.git
cd lgpd-scan
uv sync                       # cria .venv com as dependências travadas no uv.lock
uv run pre-commit install     # ativa os hooks de commit e de mensagem
```

## Fluxo de trabalho

1. Crie uma branch curta a partir da `main` atualizada, com prefixo do tipo:
   `feat/`, `fix/`, `docs/`, `chore/`, `ci/`, `test/`, `refactor/`.
2. Faça commits pequenos. Os hooks rodam a cada commit; se um falhar, corrija e
   commite de novo (não use `--no-verify`).
3. Abra o PR para a `main` preenchendo o template, inclusive o checklist.
4. O CI precisa ficar verde (`pre-commit (lint e higiene)` e `gitleaks (segredos)`).
5. O merge é sempre **squash**: o título do PR vira a mensagem do commit na `main`,
   então ele deve seguir Conventional Commits.

## Mensagens de commit

Seguimos [Conventional Commits](https://www.conventionalcommits.org/), validado
por hook. Formato: `tipo(escopo opcional): descrição no imperativo`, em português.

| Tipo | Quando usar |
|---|---|
| `feat` | Nova funcionalidade |
| `fix` | Correção de bug |
| `docs` | Só documentação |
| `test` | Só testes |
| `refactor` | Mudança de código sem alterar comportamento |
| `perf` | Melhoria de desempenho |
| `build` | Dependências e empacotamento |
| `ci` | Pipeline de CI |
| `chore` | Manutenção que não se encaixa acima |
| `revert` | Desfaz um commit anterior |

Exemplo: `feat(detectors): valida dígitos verificadores do CPF`.

## Dados pessoais: regra inegociável

Este é um projeto sobre LGPD, e o repositório é público.

- **Nunca** versione dados pessoais reais, nem "mascarados" à mão.
- Arquivos de dados (`.csv`, `.xlsx`, `.parquet`, `.db`...) só em `examples/` e
  só **sintéticos, gerados por código** versionado no projeto. O `.gitignore`
  bloqueia esses formatos fora de `examples/`; não contorne com `git add -f`.
- Testes usam CPFs/CNPJs **gerados pelo algoritmo**, nunca copiados de pessoas ou
  empresas reais.

## Qualidade

```bash
uv run pre-commit run --all-files   # tudo o que o CI verifica, localmente
uv run ruff check .                 # lint
uv run mypy                         # tipos (modo strict)
uv run pytest                       # testes
```

> Na Fase 0 ainda não há código: mypy e pytest não têm o que verificar.

Novos detectores entram com testes de casos válidos, inválidos e de borda.

## Uma tarefa está pronta (DoD) quando

- o critério de aceite foi verificado e a evidência está no PR;
- o CI está verde;
- testes cobrem o comportamento novo (a partir da Fase 1);
- documentação atualizada, se o comportamento mudou;
- decisão estrutural nova registrada em ADR.
