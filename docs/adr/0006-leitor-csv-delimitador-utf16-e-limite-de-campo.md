# ADR-0006 — Leitor CSV: delimitador, UTF-16 e limite de campo

- **Status:** aceito
- **Data:** 2026-11-23

## Contexto

- O plano dizia "recuo para `,` se o sniff falhar" e o design tentava só `utf-8-sig` e
  `cp1252`. Medições com o leitor da Task 8 mostraram que isso não basta. Todas foram feitas
  com CSVs sintéticos gerados por script, que não está no repositório.
- Delimitador: em 300 CSVs com `;` e CRLF (estilo Excel), o `csv.Sniffer` levantou
  `csv.Error` em 3 arquivos com 2% das células entre aspas, 84 com 10% e 265 com 30%.
  Com LF, 0 falhas. Nos 2.000 arquivos medidos, sempre que o Sniffer não levantou erro, o
  delimitador estava certo. O recuo para `,` transformava a planilha numa coluna só.
- Codificação: um arquivo UTF-16 ("Texto Unicode" do Excel) decodifica em `cp1252` sem
  erro e o cabeçalho sai como `['\xff\xfea\x00', ...]`; o scan diria "nada encontrado".
- Tamanho de campo: sem limite, uma aspa aberta e nunca fechada engole o arquivo inteiro
  num campo. Um arquivo de 21 MB com aspa aberta na linha 2 virou 1 linha só, com pico de
  155 MB. O Excel limita uma célula a 32.767 caracteres (Microsoft, "Excel specifications
  and limits").
- Do `Sniffer` só se usa o delimitador: o dialeto inferido troca o caractere de aspas e pula
  espaços, e apóstrofos e espaços do dado somem (ver o docstring de `csv_reader.py`).

## Decisão

- Quando o Sniffer levantar `csv.Error`, conta-se cada candidato (`,;\t|`) na primeira
  linha não vazia da amostra (o cabeçalho) e usa-se o mais frequente; sem nenhum, `,`.
  Medido: 0 falhas nos casos acima.
- Sem `encoding` informado, se os 2 primeiros bytes forem `FF FE` ou `FE FF`, usa-se
  `utf-16`, sem tentar `utf-8-sig` nem `cp1252`.
- O limite de campo é de 16 Mi caracteres (512 vezes o do Excel), no lugar de `2**31 - 1`.
  Medido com o `csv` puro: o arquivo de 21 MB com aspa aberta dá `csv.Error` na linha
  159.785 com pico de 67 MB, e um campo de 200 mil caracteres continua lido.

O ADR de confiança e risco da Tarefa 9, previsto no plano como 0006, passa a ser o 0007.

## Alternativas consideradas

| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Manter o recuo para `,` | Já implementado | Planilha vira uma coluna; falha silenciosa | 265 de 300 falhas com 30% de aspas |
| Exigir `--delimiter` do usuário | Sem adivinhação | Atrito; o usuário nem sempre sabe | Piora o uso comum |
| Usar o dialeto completo do Sniffer | Uma chamada só | Some com apóstrofos e espaços do dado | `anonymize` reescreve o arquivo |
| Contar candidatos no cabeçalho, BOM para UTF-16, limite de 16 Mi | Simples, medido | Heurística | **Escolhida** |

## Consequências

- **Positivas:** planilhas do Excel com CRLF e aspas são lidas com o delimitador certo; UTF-16
  deixa de ser lido como lixo; aspa aberta falha com erro claro em vez de consumir memória.
- **Negativas / custos aceitos:** se um nome de coluna contiver um delimitador, o cabeçalho
  pode apontar o candidato errado. UTF-32 fica de fora (a BOM `FF FE 00 00` também começa
  com `FF FE` e seria lida como UTF-16). Linha vazia antes do cabeçalho é ignorada. O erro de
  campo grande demais aponta a linha do estouro, não a da aspa. Um campo legítimo acima de
  16 Mi caracteres falha de propósito. O limite do módulo `csv` é global ao processo, mas o
  leitor o eleva só durante a leitura e o restaura depois.
- **O que revisitar e quando:** se aparecer arquivo real que quebre a heurística, ou quando
  UTF-32 for pedido.
