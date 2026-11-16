# ADR-0002 — Integração na `main` só por PR, com CI obrigatório e squash

- **Status:** aceito
- **Data:** 2026-11-16

## Contexto

- Desenvolvedor solo, repositório público de portfólio.
- O pre-commit local pode ser pulado (`--no-verify`, `SKIP=`) ou não estar
  instalado num clone novo; precisa de uma trava que não dependa da máquina.
- Merges por "merge commit" geravam `Merge pull request #N ...`, fora do padrão
  Conventional Commits adotado pelo projeto.
- Rulesets estão disponíveis em repositórios públicos no plano Free (GitHub Docs).
- O hook do gitleaks no pre-commit roda com `--staged`; no CI não há nada staged.
  A `gitleaks-action` varre só os commits do evento em `pull_request`/`push` e o
  histórico inteiro em `workflow_dispatch`/`schedule` (conferido no código-fonte
  da action v3.0.0).

## Decisão

A `main` só recebe mudanças por PR com os checks `pre-commit (lint e higiene)` e
`gitleaks (segredos)` verdes, sem force push, sem exclusão e sem lista de bypass
(ruleset `proteger-main`). O único método de merge é **squash**, com o título da
PR como mensagem. Branches são apagadas automaticamente após o merge. O gitleaks
roda a cada PR e push (incremental) e toda segunda-feira sobre o histórico inteiro.

## Alternativas consideradas

| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Sem proteção da `main` | Zero atrito | Nada impede push direto ou merge com CI vermelho | O CI viraria opcional |
| Exigir 1 aprovação | Revisão obrigatória | O autor não pode aprovar a própria PR | Travaria o desenvolvedor solo |
| Merge commit | Preserva commits da branch na `main` | Commit de merge fora do padrão; histórico ruidoso | Cada PR já é uma unidade de trabalho |
| Rebase merge | Histórico linear com todos os commits | Commits intermediários ("corrige", "revert") vão para a `main` | Polui a `main` com o rascunho |
| Gitleaks só no pre-commit | Simples | Pulável; no CI não examina nada | Precisa de trava independente da máquina |

## Consequências

- **Positivas:** a `main` tem um commit por PR, todos no padrão; nada entra sem CI
  verde; segredo que escape do hook local é pego na PR.
- **Negativas / custos aceitos:** commits intermediários só ficam visíveis na PR;
  renomear um job do CI exige atualizar o ruleset, senão os merges travam
  esperando um check que não existe mais.
- **O que revisitar e quando:** se o projeto ganhar colaboradores, exigir 1
  aprovação e CODEOWNERS.
