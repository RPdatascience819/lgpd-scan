# ADR-0007 — Confiança, regra da maioria e risco

- **Status:** aceito
- **Data:** 2026-11-23

## Contexto

O `scan` e o `anonymize` precisam concordar sobre o que é dado pessoal e sobre o risco do
arquivo. Um número de 11 dígitos que passa no dígito verificador do CPF é comum (cerca de 1% dos
números aleatórios), então tratar toda ocorrência como certa geraria falso positivo em massa.
O design (seção 5.4) define confiança, regra da maioria e risco; este ADR registra o limiar e
as decisões de implementação que o design deixou em aberto.

## Decisão

Vale a seção 5.4 do design. Em resumo, em `scoring.py`:

- **Confiança:** ALTA se o trecho é formatado, se o tipo está entre os que o nome da coluna
  indica, ou se é e-mail; MEDIA nos demais casos.
- **Regra da maioria:** uma ocorrência MEDIA só conta se o mesmo tipo aparece em pelo menos
  `LIMIAR_MAIORIA = 0.5` das células preenchidas da coluna; senão é suspeita. ALTA conta sempre.
- **Risco** (só o que conta): ALTO com algum CPF ALTA; MEDIO com e-mail, telefone ou CPF que
  conta só como MEDIA; BAIXO só com CNPJ; NENHUM no resto.

Decisões de implementação:

1. **Nome da coluna por palavra, não por substring.** O nome é separado em camelCase,
   normalizado (NFKD, sem marcas, `casefold`) e quebrado em palavras só com letras `a-z`;
   uma palavra, ou a junção de duas vizinhas (`e` + `mail`), precisa estar na tabela
   (`cpf`, `cnpj`, `email`, `telefone`, `tel`, `fone`, `celular`, `cel`, `whatsapp`). Por
   substring, `hotel`, `microfone`, `cancelado` e `celula` virariam telefone.
2. **Coluna com mais de um tipo** (`cpf_cnpj`): `_tipos_sugeridos` devolve o conjunto;
   `tipo_sugerido` devolve o tipo só se for único. A classificação usa o conjunto.
3. **Conflito CPF x telefone** é qualquer sobreposição de intervalos, não só identidade
   (`+55 11987654321`). Só telefone no contexto: fica o telefone, ALTA. Só CPF: fica o CPF,
   ALTA. Nenhum ou os dois: fica o CPF, MEDIA, `ambiguo=True`. A ocorrência descartada some.
4. **Ocorrência contida num e-mail da mesma célula é descartada**: o e-mail já a cobre.
5. **Maioria em aritmética inteira/racional:** o par `(coluna, tipo)` entra em `media_conta`
   quando `celulas_com_o_tipo / preenchidas >= 1/2` (comparação com `Fraction`, sem `float`).
   Conta **células** com o tipo, não ocorrências. Célula preenchida é a de `strip()` não vazio.
6. **`LinhaRelatorio`:** `contam` = ALTA + MEDIA que contam; `suspeitas` = MEDIA que não
   contam; `confianca` = ALTA se as ALTA são pelo menos tantas quanto as MEDIA que contam
   (MEDIA se nada conta); `amostra` = primeira ocorrência do par, já mascarada; só
   `pct_preenchidas` é `float`, para exibição.
7. **`mascarar`** troca por `*` só os alfanuméricos, preserva pontuação e comprimento. E-mail
   com um único alfanumérico na parte local também o mascara, para não mostrar tudo.

## Alternativas consideradas

| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Nome da coluna por substring | Simples | `hotel`, `microfone` viram telefone | Falso contexto vira confiança ALTA |
| Conflito só por trecho idêntico | Simples | Perde `+55` + número | O mesmo número gerava CPF e telefone |
| Maioria com `float` | Direto | Arredondamento na fronteira de 50% | Aritmética racional é exata |
| Limiar de 50% configurável por flag | Flexível | Mais superfície, resultados divergentes | Constante nomeada basta na Fase 1 |

## Consequências

- **Positivas:** `scan` e `anonymize` partilham o mesmo núcleo; a regra da maioria evita
  falso positivo em massa; o limiar é uma constante documentada.
- **Negativas / custos aceitos:** um CPF solto, sem máscara e sem contexto, numa coluna de
  outra coisa não altera o risco (aparece como suspeita). Nomes de coluna fora da tabela
  (`contato`) não dão contexto.
- **O que revisitar e quando:** o limiar de 0.5 e a tabela de palavras, se a validação com
  arquivos sintéticos maiores mostrar falsos negativos ou positivos.
