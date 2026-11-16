# ADR-0001 — Ambiente Python com uv, 3.14 no desenvolvimento e 3.11 como mínimo

- **Status:** aceito
- **Data:** 2026-11-16

## Contexto

- O projeto é uma CLI em Python; precisa de ambiente reproduzível para quem clona
  e para o CI.
- A máquina de desenvolvimento tem Python 3.11 no PATH e o projeto mora num
  caminho com acento (`F:\GitHub - Portifólios\...`). Python ≤ 3.12 lê o `.pth`
  da instalação editável em cp1252 no Windows, o que corrompe o caminho e quebra
  o `import` do pacote.
- Python 3.10 chegou ao fim de vida em 2026-10-01; 3.11 vai até 2027-10-31
  (endoflife.date, consultado em 2026-11-16). O README original prometia "3.10+".
- A Fase 0 não tem código de aplicação: não há pacote para instalar.

## Decisão

Desenvolver com Python 3.14 (`.python-version`) e `uv` (lock em `uv.lock`),
declarar `requires-python = ">=3.11"`, e manter o `pyproject.toml` sem
`[build-system]` até a Fase 1. O passo 5 da Fase 0 (ambiente) foi incorporado
ao passo 4 (qualidade), porque as ferramentas do passo 4 já precisam do ambiente.

## Alternativas consideradas

| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| `pip` + `venv` | Familiar a qualquer contribuidor | Sem lock nativo; ambiente não reproduzível | Reprodutibilidade é requisito do CI |
| Poetry | Lock e grupos de dependência | Mais lento; instalação própria | uv já instalado, mais rápido, suportado pelo Dependabot |
| Mínimo 3.10 | Alcança mais usuários | Versão sem correções de segurança | Prometer suporte a versão morta |
| Desenvolver no 3.11 | Testa o mínimo localmente | Quebra a instalação editável no caminho com acento | O CI testa o mínimo; local fica no 3.14 |
| Desenvolver no 3.15 | Mais novo (3.15.2 disponível) | Ecossistema de wheels ainda amadurecendo | Entra na matriz do CI quando houver código |
| Manter o passo 5 separado | Segue o plano original | Ferramentas instaladas duas vezes; a prova do `import` exige código, que a Fase 0 não tem | Trabalho duplicado sem verificação possível |

## Consequências

- **Positivas:** `uv sync --locked` reproduz o ambiente exato no CI e em clones;
  versões das ferramentas fixadas em um só lugar.
- **Negativas / custos aceitos:** quem contribui precisa instalar o `uv`; o
  `python` do PATH (3.11) não deve ser usado neste projeto.
- **O que revisitar e quando:**
  - **DoR da Fase 1:** ao criar o pacote, provar a instalação editável no caminho
    com acento (`uv sync` + `uv run python -c "import lgpd_scan"`), e adicionar
    matriz 3.11 / 3.14 / 3.15 no CI.
  - **Outubro de 2027:** fim de vida do 3.11 → nova ADR subindo o mínimo.
