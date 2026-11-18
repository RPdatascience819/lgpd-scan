# ADR-0004 — Build backend `uv_build`, sem `hatchling`

- **Status:** aceito
- **Data:** 2026-11-18

## Contexto

- A Fase 1 torna `lgpd_scan` um pacote instalável (`lgpd-scan --version`), o que exige
  declarar um `[build-system]` no `pyproject.toml`.
- O projeto já usa `uv` para ambiente e lock (ADR-0001), e o caminho local tem acento
  ("Portifólios"), então a instalação editável precisa funcionar nele.
- O layout é `src/lgpd_scan`, que o `uv_build` encontra por padrão a partir do nome do
  projeto, sem configuração extra.
- A documentação do `uv` recomenda limitar a versão do `uv_build` com teto
  (`>=0.13.9,<0.14`), porque o backend ainda muda entre versões menores.

## Decisão

Usar `uv_build` como build backend, com a faixa `uv_build>=0.13.9,<0.14`.

## Alternativas consideradas

| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| `hatchling` | Maduro, muito usado, muitos plugins | Dependência extra de build, de outro fornecedor | Não precisamos de plugins; mais uma peça na cadeia de supply chain |
| `setuptools` | Onipresente | Configuração mais pesada; legado para projetos novos | Sem vantagem para um pacote simples em `src/` |
| `uv_build` | Mesmo fornecedor do `uv`; sem dependência extra; descobre `src/lgpd_scan` sozinho | Backend mais novo; exige teto de versão | **Escolhida** |

## Consequências

- **Positivas:** menos fornecedores no build; configuração mínima; coerente com o `uv`
  já adotado.
- **Negativas / custos aceitos:** o teto `<0.14` precisa ser revisado a cada versão
  menor do `uv_build`; menos plugins que o `hatchling`.
- **O que revisitar e quando:** se surgir necessidade de plugin de build (por exemplo,
  versão derivada de tag do git) ou se o `uv_build` quebrar a instalação editável no
  caminho com acento, reavaliar o `hatchling`.
