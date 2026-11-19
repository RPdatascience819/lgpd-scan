# ADR-0005 — CNPJ alfanumérico: só maiúsculas, `A–Z` inteiro

- **Status:** aceito
- **Data:** 2026-11-19

## Contexto

- A IN RFB nº 2.229/2024 introduz o CNPJ alfanumérico: as 12 primeiras posições
  (8 da raiz e 4 da ordem) passam a aceitar letras e dígitos; os 2 dígitos verificadores
  seguem numéricos. O exemplo oficial usado nos testes é `12.ABC.345/01DE-35`.
- Não havia fonte aberta disponível nesta tarefa para conferir o texto da norma, então
  este ADR não traz URL: a referência é só o nome da norma.
- Não está confirmado se a Receita exclui alguma letra do alfabeto (por exemplo,
  letras que se confundem com dígitos).
- O design da Fase 1 dizia "rejeitar 14 caracteres iguais". Medido: o único CNPJ de
  14 caracteres iguais com DV válido é `00000000000000`; já `AAAAAAAAAAAA` tem DV `45`,
  ou seja, uma base repetida pode ter DV diferente dos caracteres da base.

## Decisão

- O detector aceita **somente letras maiúsculas** (`A–Z` inteiro) e dígitos nas 12
  primeiras posições; o DV é sempre numérico.
- Minúsculas não casam: o formato oficial é em maiúsculas, e aceitar minúsculas
  aumentaria falsos positivos em texto livre.
- O detector rejeita o CNPJ quando os **12 caracteres da base** são todos iguais
  (`len(set(base)) == 1`), a mesma regra de `gerar_cnpj`. A frase "14 caracteres
  iguais" do design deve ser lida assim.
- Máscara parcial é aceita (separadores opcionais um a um); `formatado=True` só quando
  o trecho casa a máscara completa.

## Alternativas consideradas

| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Excluir letras supostamente ambíguas (`I`, `O`, `Q`...) | Menos falsos positivos | Sem confirmação da Receita; pode perder CNPJs reais | Regra inventada sem fonte |
| Aceitar minúsculas | Pega dados digitados sem padrão | Mais falsos positivos; fora do formato oficial | Formato oficial é maiúsculo |
| Rejeitar só 14 caracteres iguais | Fiel ao texto do design | Deixa passar `AAAAAAAAAAAA45`; assimétrico com o gerador | Simetria com `gerar_cnpj` |
| Só maiúsculas, `A–Z` inteiro, base repetida rejeitada | Simples; simétrico com o gerador | Pode aceitar letra que a Receita venha a excluir | **Escolhida** |

## Consequências

- **Positivas:** detector e gerador compartilham a mesma regra; testes sem literais
  além do exemplo oficial.
- **Negativas / custos aceitos:** um trecho com letra que a Receita nunca emitirá pode
  passar se o DV bater por acaso (probabilidade baixa, e o falso positivo é o lado
  seguro numa ferramenta de privacidade).
- **O que revisitar e quando:** quando a Receita confirmar letras excluídas do
  alfabeto, ajustar o detector e `gerar_cnpj` juntos.
