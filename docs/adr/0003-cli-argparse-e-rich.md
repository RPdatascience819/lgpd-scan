# ADR-0003 — CLI com `argparse` e Rich, sem Typer

- **Status:** aceito
- **Data:** 2026-11-18

## Contexto

- A Fase 1 entrega uma CLI com os comandos `scan` e `anonymize`. O design
  (`docs/design/2026-11-18-fase-1-design.md`) previa Typer.
- O Typer a partir da 0.29 passou a exigir `pydantic` (a 0.29.0 foi a primeira a
  pedir `pydantic>=2.5.3`), o que traz também `pydantic-core`.
- Árvore de dependências medida em 2026-11-18 com
  `uv pip compile --python-version 3.11`:
  - Typer 0.29.2: 13 pacotes, incluindo `pydantic` e `pydantic-core`;
  - Typer 0.28.0: 8 pacotes;
  - só `rich==15.0.0`: 4 pacotes (`rich`, `markdown-it-py`, `mdurl`, `pygments`).
- Quatro versões do Typer em 12 dias: 0.28.0 (2026-11-06), 0.29.0 (2026-11-09),
  0.29.1 (2026-11-11) e 0.29.2 (2026-11-18). A superfície de dependência mudou
  dentro de uma semana.
- O projeto é uma ferramenta de privacidade: cada dependência de execução é
  superfície de supply chain a justificar.

## Decisão

Usar `argparse` da biblioteca padrão para a CLI e Rich apenas para a saída
formatada. Alternativa escolhida pelo usuário (opção A).

## Alternativas consideradas

| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Typer 0.29.x | Ergonomia: type hints viram opções; ajuda pronta | 13 pacotes, com `pydantic` e `pydantic-core`; ritmo de releases alto | Custo de dependência desproporcional para dois comandos |
| Typer 0.28.0 (fixado) | 8 pacotes, sem `pydantic` | Versão já superada; o Dependabot proporá subir para a 0.29 | Fixar versão antiga só adia o problema |
| `argparse` + Rich | 4 pacotes, todos vindos do Rich; CLI sem dependência | Mais código de interface escrito à mão; subcomandos mais verbosos | **Escolhida** |

## Consequências

- **Positivas:** menor árvore de dependências de execução; `--help` e `Usage:` do
  `argparse` são da biblioteca padrão, sem os textos do Click.
- **Negativas / custos aceitos:** mais código de CLI para escrever e testar; sem
  autocompletar de shell pronto; a ajuda é menos rica que a do Typer.
- **O que revisitar e quando:** se a CLI passar de uns cinco subcomandos ou
  ganhar autocompletar como requisito, reavaliar o Typer com a árvore medida de novo.
