# ADR-0006 — Leitor CSV: delimitador pelo cabeçalho quando o Sniffer falha, e UTF-16 pela BOM

- **Status:** aceito
- **Data:** 2026-11-23

## Contexto

- O plano dizia "recuo para `,` se o sniff falhar" e o design tentava só `utf-8-sig` e
  `cp1252`. Duas medições com o leitor da Task 8 mostraram que isso não basta.
- Delimitador: em 300 CSVs com `;` e CRLF (estilo Excel), o `csv.Sniffer` levantou
  `csv.Error` em 3 arquivos com 2% das células entre aspas, 84 com 10% e 265 com 30%.
  Com LF, 0 falhas. Nos 2.000 arquivos medidos, sempre que o Sniffer não levantou erro, o
  delimitador estava certo. O recuo para `,` transformava a planilha numa coluna só.
- Codificação: um arquivo UTF-16 ("Texto Unicode" do Excel) decodifica em `cp1252` sem
  erro e o cabeçalho sai como `['\xff\xfea\x00', ...]`; o scan diria "nada encontrado".

## Decisão

- Quando o Sniffer levantar `csv.Error`, conta-se cada candidato (`,;\t|`) na primeira
  linha da amostra (o cabeçalho) e usa-se o mais frequente; sem nenhum, `,`. Medido: 0
  falhas nos casos acima. Do Sniffer continua valendo só o delimitador.
- Sem `encoding` informado, se os 2 primeiros bytes forem `FF FE` ou `FE FF`, usa-se
  `utf-16`, sem tentar `utf-8-sig` nem `cp1252`.

O ADR de confiança e risco da Tarefa 9, previsto no plano como 0006, passa a ser o 0007.

## Alternativas consideradas

| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Manter o recuo para `,` | Já implementado | Planilha vira uma coluna; falha silenciosa | 265 de 300 falhas com 30% de aspas |
| Exigir `--delimiter` do usuário | Sem adivinhação | Atrito; o usuário nem sempre sabe | Piora o uso comum |
| Usar o dialeto completo do Sniffer | Uma chamada só | Some com apóstrofos e espaços do dado (R-8a) | `anonymize` reescreve o arquivo |
| Contar candidatos no cabeçalho, BOM para UTF-16 | Simples, medido | Heurística | **Escolhida** |

## Consequências

- **Positivas:** planilhas do Excel com CRLF e aspas são lidas com o delimitador certo; UTF-16
  deixa de ser lido como lixo.
- **Negativas / custos aceitos:** se um nome de coluna contiver um delimitador, o cabeçalho
  pode apontar o candidato errado. UTF-32 fica de fora (a BOM `FF FE 00 00` também começa
  com `FF FE` e seria lida como UTF-16).
- **O que revisitar e quando:** se aparecer arquivo real que quebre a heurística, ou quando
  UTF-32 for pedido.
