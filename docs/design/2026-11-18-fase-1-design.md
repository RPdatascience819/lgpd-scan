# Fase 1: fatia vertical publicada (design)

- **Data:** 2026-11-18
- **Status:** revisado (builder check), com as decisões do usuário incorporadas; aguardando
  aprovação final
- **Épico:** #22 · **Milestone:** Fase 1

## 1. Intenção

O LGPD-Scan é projeto de portfólio público, mas precisa ser um **produto útil de
verdade**, e a Fase 1 termina com um **post no LinkedIn** para recrutadores, empresas e
freelancers. Os três objetivos pedem a mesma coisa: um caminho que funcione de ponta a
ponta e que qualquer pessoa consiga testar com um comando:

```bash
uvx lgpd-scan scan clientes.csv
uvx lgpd-scan anonymize clientes.csv --output clientes_anon.csv
```

O post precisa de algo para mostrar (um GIF do terminal) e de algo para testar (o pacote
no PyPI). Um produto largo e pela metade não entrega nenhum dos dois.

## 2. Metas, não metas e antimetas

**Metas**
1. Ler CSV, incluindo o CSV "brasileiro" exportado do Excel (`;` e cp1252).
2. Detectar **CPF, CNPJ (numérico e alfanumérico), e-mail e telefone brasileiro**, com
   validação por dígito verificador onde ela existe.
3. Comando `scan`: relatório no terminal e em JSON, com confiança por coluna e um nível de
   risco do arquivo.
4. Comando `anonymize` no modo `mask`.
5. Publicar a v0.1.0 no PyPI, instalável com `uvx`/`pipx`.
6. Ter uma vitrine: dados sintéticos em `examples/`, um GIF no README e o rascunho do post.

**Não metas (Fase 2 em diante):** Excel, Parquet e SQLite; RG, CEP e placa; relatório
HTML; modos `hash`, `redact` e `drop`; desempenho com arquivos de vários GB; integração
como hook de CI de terceiros.

**Antimetas** (o que seria fracasso mesmo que "funcione"):
- o relatório ou o JSON **mostrar um valor pessoal completo**: a ferramenta passaria a
  vazar o que deveria proteger;
- qualquer **acesso à rede** durante `scan`/`anonymize`;
- **falso positivo em massa** (todo número de 11 dígitos virar CPF), que destrói a
  confiança no produto;
- algum dado pessoal real no repositório, nos testes ou no GIF;
- uma fase que não termina porque o escopo cresceu.

## 3. Restrições

- Python `>=3.11` (ADR-0001), desenvolvimento em 3.14 com `uv`, `mypy --strict`, Ruff e o
  pre-commit atual. O projeto mora num caminho com acento e espaço.
- Repositório público: dados só sintéticos, gerados por código (CONTRIBUTING).
- Protocolo do `CLAUDE.md`: um passo por vez, branch curta → PR → squash feito pelo
  usuário, versões conferidas na documentação, desvios registrados em ADR.
- O usuário cria contas e credenciais (PyPI). O agente nunca lida com token.

## 4. Abordagens consideradas

| Abordagem | O que entrega | Troca |
|---|---|---|
| **A. Fatia vertical publicada (escolhida)** | CSV, 4 detectores, `scan` + `anonymize mask`, v0.1.0 no PyPI | Formatos e detectores restantes ficam para a Fase 2 |
| B. Todos os detectores, sem CLI | Os 7 detectores como biblioteca | Nada para mostrar nem para usar, o que contraria 2 dos 3 objetivos |
| C. A v1 completa | Tudo o que o README promete | Meses até o primeiro post; risco de não terminar |

O usuário escolheu **A** em 2026-11-18.

## 5. Decisões de produto

### 5.1 Interface

```text
lgpd-scan scan ARQUIVO.csv [--format table|json] [--output CAMINHO]
                           [--encoding ENC] [--delimiter CHAR]
lgpd-scan anonymize ARQUIVO.csv --output SAIDA.csv [--mode mask] [--force]
                                [--incluir-suspeitas]
                                [--encoding ENC] [--delimiter CHAR]
lgpd-scan --version
```

- `anonymize` **nunca** sobrescreve o arquivo de entrada. Sobrescrever uma saída que já
  existe exige `--force`.
- **Códigos de saída: contrato público, congelado a partir da v0.1.0** (decidido pelo
  usuário em 2026-11-18):

  | Comando | `0` | `1` | `2` |
  |---|---|---|---|
  | `scan` | nada que conte (5.4), **ou só CNPJ** | algum CPF, e-mail ou telefone que conta | erro de uso ou de leitura |
  | `anonymize` | sucesso, mesmo sem nada a mascarar (grava a cópia) | — | erro de uso, leitura ou escrita |

  É a semântica do `grep`: permite usar o `scan` em CI ("falhe se houver CPF") sem flag
  extra. CNPJ sozinho dá `0` porque é dado de empresa; senão, um CI travaria em qualquer
  planilha de fornecedores. "Suspeitas" (5.4) nunca disparam o `1`.
- **Idioma:** as mensagens e a ajuda escritas pelo projeto (descrições de comandos e
  opções, erros, resumo) ficam em português. Os textos embutidos do Click/Typer (`Usage:`,
  `Show this message and exit.`) ficam em inglês. *Decisão do agente:* traduzi-los exigiria
  sobrescrever o Click, um custo alto para pouco ganho.

### 5.2 Leitura de CSV

- Biblioteca padrão (`csv`), **em streaming**, linha a linha. Não traz dependência e não
  tem limite de memória.
- **Codificação:** tenta `utf-8-sig` e, se falhar na decodificação, cai para `cp1252`
  (exportação típica do Excel brasileiro). `--encoding` força o valor.
- **Delimitador:** `csv.Sniffer` sobre as primeiras linhas, restrito a `,` `;` `\t` `|`.
  `--delimiter` força o valor.
- A primeira linha é sempre o cabeçalho. CSV sem cabeçalho fica fora da Fase 1, e as
  colunas viram `coluna_1..n` só se o builder achar trivial.
- Interface de leitor: um `Protocol` que produz `(numero_linha, nome_coluna, valor)`, para
  a Fase 2 plugar Excel, Parquet e SQLite sem tocar em detectores nem em relatório.

### 5.3 Detectores

Cada detector é uma função pura: recebe o texto de uma célula e devolve as ocorrências
(tipo, posição, valor normalizado, se passou na validação). Ele **procura dentro do texto**,
não só na célula inteira (`"cliente 674.172.244-07 ligou"` conta).

| Tipo | Aceita | Validação | Rejeita |
|---|---|---|---|
| **CPF** | `000.000.000-00` e 11 dígitos seguidos | DV módulo 11 | 11 dígitos iguais; DV inválido |
| **CNPJ** | `00.000.000/0000-00` e 14 caracteres seguidos; as 12 primeiras posições `[0-9A-Z]`, as 2 últimas dígitos | DV módulo 11 com pesos 2–9 e caractere → `ord(c) - 48` (IN RFB 2.229/2024; A=17) | 14 caracteres iguais; DV inválido; letras minúsculas |
| **E-mail** | regex pragmática `local@dominio.tld` | nenhuma (sem DNS: seria rede) | sem TLD |
| **Telefone** | com ou sem `+55`, com DDD; celular 9 dígitos começando com 9; fixo 8 dígitos começando com 2–5 | DDD numa lista de DDDs válidos do Brasil | DDD inexistente |

- **CNPJ alfanumérico:** aceito só em maiúsculas, que é o padrão oficial. Uma nota
  técnica menciona a possível exclusão de algumas letras, ainda não confirmada; a Fase 1
  aceita `A–Z` inteiro e registra isso em ADR para revisitar. O exemplo oficial
  `12.ABC.345/01DE-35` entra como teste.
- **Fronteiras:** um número só casa se não estiver colado a outros dígitos ou letras
  (`\b`/lookarounds), para que um trecho de um número maior não vire CPF.
- **Colisão CPF × telefone:** um celular com DDD tem 11 dígitos e passa no DV do CPF por
  acaso em ~1 a cada 100 casos (simulado: 0,99% de 200 mil celulares). Quem resolve é a confiança por contexto (5.4), não o
  detector.

### 5.4 Confiança e risco

**Confiança de cada ocorrência:**
- **alta:** formatado com máscara e válido, **ou** válido numa coluna cujo nome indica o
  tipo (`cpf`, `cnpj`, `email`, `e_mail`, `telefone`, `celular`, `fone`...; comparação
  sem acento e sem maiúsculas);
- **média:** válido, sem máscara e sem contexto de coluna;
- e-mail é sempre **alta** (o formato já é específico).

**Conflito:** um mesmo trecho que casa CPF e telefone vira o tipo sugerido pelo nome da
coluna. Sem contexto, vira CPF com confiança **média** e o relatório marca a ambiguidade.

**Regra da maioria** (decidida pelo usuário em 2026-11-18; protege a antimeta "falso
positivo em massa"):
- uma ocorrência **média** só **conta** se o mesmo tipo aparecer em **≥ 50% das células
  preenchidas** da coluna. Células vazias ou só com espaços ficam fora do denominador;
- abaixo disso, ela vira **suspeita**: aparece no relatório, marcada, mas **não entra** no
  risco nem no código de saída, e o `anonymize` só a mascara com `--incluir-suspeitas`;
- ocorrências **alta** contam sempre, em qualquer proporção;
- exemplo: uma coluna `codigo_pedido` com 1.000 números de 11 dígitos tem ~1% passando no
  DV do CPF. São 10 suspeitas, risco inalterado e nenhum código de pedido alterado. Uma
  coluna `col7` com 95% de CPFs sem máscara passa da maioria e conta;
- custo aceito: um CPF solto, sem máscara e sem contexto, no meio de uma coluna de outra
  coisa não altera o risco (continua visível como suspeita);
- o limiar de 50% é uma constante nomeada, documentada no ADR de confiança e risco.

**Agregação: uma linha por par (coluna, tipo)** e não por coluna. *Decisão do agente:* a
coluna `observacoes` pode ter CPF, e-mail e telefone ao mesmo tempo, e uma linha por coluna
esconderia tipos que o `anonymize` mascara. Cada linha traz o número de ocorrências que
contam, o número de suspeitas, a % de células preenchidas com ocorrência e a confiança
predominante. O JSON (`schema_version: 1`) segue a mesma granularidade.

**Risco do arquivo** (regra simples e documentada, registrada em ADR; só ocorrências que
contam):
- **alto:** algum CPF com confiança alta;
- **médio:** e-mail ou telefone, ou CPF que conta só com confiança média;
- **baixo:** só CNPJ. CNPJ é dado de **empresa**, que a LGPD não protege, mas o relatório
  avisa que um CNPJ de MEI pode identificar uma pessoa;
- **nenhum:** nada encontrado.

### 5.5 Relatório

**Terminal (Rich):**

```text
LGPD-Scan · clientes.csv · 1.000 linhas · risco ALTO

 Coluna        Tipo      Contam  Suspeitas  % preench.  Confiança  Amostra
 cpf           CPF          998          0        99,8  alta       ***.172.244-**
 contato       Telefone     950          0        95,0  alta       (11) 9****-4321
 email         E-mail      1000          0       100,0  alta       j***@exemplo.com
 observacoes   CPF            4          8         1,2  alta       ***.456.789-**
 observacoes   E-mail         6          0         0,6  alta       m***@exemplo.org
 codigo_pedido CPF            0         10         1,0  média      ***.903.115-**  (suspeita)

 Suspeitas não entram no risco. Use --incluir-suspeitas no anonymize para mascará-las.
```

(Em `observacoes`, as 4 que contam estão formatadas, portanto são alta. As 8 suspeitas são
números sem máscara e minoria na coluna.)

**JSON:** o mesmo conteúdo, com `"schema_version": 1` para ser estável em CI. As amostras
saem **mascaradas também no JSON**. Nenhuma saída contém valor completo.

### 5.6 Mascaramento (`anonymize --mode mask`)

- Mascara **apenas o trecho detectado** dentro da célula, preservando o resto do texto e o
  formato (pontuação e comprimento):
  - CPF `674.172.244-07` → `***.172.244-**`;
  - CNPJ `12.ABC.345/01DE-35` → `12.***.***/01DE-**`;
  - e-mail `joana@exemplo.com` → `j****@exemplo.com`;
  - telefone `(11) 98765-4321` → `(11) 9****-4321`.
- Mascara tudo o que **conta** no `scan` (5.4), e também as suspeitas se receber
  `--incluir-suspeitas`. O mesmo núcleo serve os dois comandos, então o `anonymize` nunca
  discorda do `scan`.
- O CSV de saída mantém cabeçalho, delimitador, codificação e ordem das colunas.
- Ao final imprime um resumo (quantas células alteradas, por tipo), sem valores.

### 5.7 Privacidade como propriedade testada

- Nenhum módulo do pacote importa nada de rede. Um teste roda `scan` e `anonymize` com
  `socket.socket` substituído por algo que lança erro.
- Nenhum log, mensagem de erro ou traceback do pacote inclui o conteúdo de uma célula.
  Erros de leitura citam linha e coluna, nunca o valor.

## 6. Arquitetura

```text
cli.py (argparse) ──► readers/csv_reader.py ──► detectors/{cpf,cnpj,email,telefone}.py
                                              │
                          scoring.py ◄────────┘
                          ├──► report.py      (tabela Rich, JSON)
                          └──► anonymize.py   (mask; reescreve o CSV pelo mesmo leitor)
```

Segue a tabela de `src/lgpd_scan/README.md`, que sai na Fase 1 em favor da docstring do
`__init__.py`, como ele próprio anuncia.

- **Dependências de execução:** `argparse` (biblioteca padrão) e Rich (ADR-0003). Versões
  conferidas na documentação no momento do plano. A escolha da CLI está no ADR-0003.
- **Build backend:** item do DoR. A escolha (ex.: `uv_build` × `hatchling`) vai para ADR,
  com a prova `uv sync` + `uv run python -c "import lgpd_scan"` no caminho com acento.

## 7. Testes e dados sintéticos

- **Gerador** (`tests/` + `examples/gerar_exemplos.py`): gera CPF e CNPJ (numérico e
  alfanumérico) válidos pelo algoritmo, telefones com DDD válido e e-mails em
  `exemplo.com`/`example.org`. Usa semente fixa, então o resultado é reprodutível.
  **Vem antes do primeiro detector** (DoR).
- **Casos por detector:** válidos formatados e sem máscara; DV inválido; dígitos
  repetidos; colado em outros dígitos; embutido em texto; o exemplo oficial do CNPJ
  alfanumérico; minúsculas rejeitadas.
- **Testes de ponta a ponta da CLI:** CSV com `;` em cp1252, CSV com `,` em UTF-8 com
  BOM, códigos de saída, `--format json` válido contra o `schema_version`, o `anonymize`
  sem sobrescrever a entrada, e a saída do `anonymize` sem detecção de confiança alta ao
  rodar `scan` de novo.
- **Teste de "sem rede"** e teste de "nenhum valor completo em nenhuma saída" (procura os
  valores do CSV de entrada no stdout, no stderr e no JSON).

## 8. CI e publicação

- **CI:** os jobs atuais mais `pytest` e `mypy`, na matriz 3.11 / 3.14 / 3.15. Conferir na
  documentação se o 3.15 já está disponível no `setup-uv` antes de incluí-lo (ADR-0001).
- **Checks obrigatórios:** os novos jobs (`pytest`, `mypy`, por versão da matriz) entram
  no ruleset `proteger-main` como checks obrigatórios. **Manual (usuário)**, no M0, com os
  nomes exatos dos jobs fornecidos pelo agente. Renomear um job sem atualizar o ruleset
  trava os merges; por isso os nomes ficam fixos depois do M0.
- **Publicação** (decidida pelo usuário em 2026-11-18). Uma versão publicada no PyPI
  **não pode ser republicada**, então o fluxo tem ensaio e trava humana:
  - a tag `v0.1.0rc1` (qualquer `v*rc*`) publica **só no TestPyPI**. É o ensaio: o
    usuário instala de lá e confere;
  - a tag `v0.1.0` publica no **PyPI** por um job no *environment* `pypi` do GitHub, que
    exige **aprovação manual do usuário**;
  - as duas usam **Trusted Publishing** (OIDC, sem token guardado), com os *environments*
    `testpypi` e `pypi`;
  - o agente cria uma tag **só com o ok explícito do usuário**, como foi feito com
    `fase-0-concluida`;
  - **Manual (usuário):** contas PyPI e TestPyPI com 2FA, os dois *pending publishers*
    (repositório, workflow e *environment* informados pelo agente) e a regra de aprovação
    no *environment* `pypi`. O nome `lgpd-scan` estava livre em 2026-11-18.
- **Versão:** `0.1.0`. Atualizar `docs/contas-e-servicos.md`.

## 9. Vitrine

- `examples/clientes_ficticios.csv` (gerado, ~1.000 linhas, `;`, cp1252, com uma coluna
  `observacoes` de texto livre para mostrar a detecção embutida e a ambiguidade).
- Um GIF do terminal no README com `scan` e depois `anonymize`. A ferramenta de gravação
  fica a cargo do builder, desde que funcione no Windows e seja reproduzível por script.
- O rascunho do post do LinkedIn em `docs/` ou entregue na conversa. **Quem publica é o
  usuário.**

## 10. Ordem de entrega (marcos)

| Marco | Conteúdo |
|---|---|
| M0, DoR | `CLAUDE.md` com escopo Fase 1; `[build-system]` + ADR + prova do import; matriz no CI + checks obrigatórios no ruleset (manual); #21 (`default_stages`: cada hook aparece uma vez por commit e o hook de mensagem continua barrando mensagem fora do padrão) |
| M1 | Gerador sintético; detectores de CPF e CNPJ (com alfanumérico) |
| M2 | Detectores de e-mail e telefone |
| M3 | Leitor CSV, confiança/risco, `scan` (tabela + JSON) |
| M4 | `anonymize --mode mask` |
| M5 | Exemplos, README final, GIF |
| M6 | `v0.1.0rc1` → TestPyPI (ensaio) → `v0.1.0` → PyPI com aprovação; tag `fase-1-concluida`; rascunho do post |

Cada marco vira uma ou mais issues na milestone Fase 1, com objetivo e critério de aceite
verificável.

## 11. Definition of Done da Fase 1

- `uvx lgpd-scan scan examples/clientes_ficticios.csv` funciona numa máquina limpa, a
  partir do PyPI;
- os 4 detectores com testes de válidos, inválidos e borda; CI verde na matriz;
- testes de "sem rede" e de "nenhum valor completo nas saídas" passando;
- teste da regra da maioria (o caso `codigo_pedido` não altera o risco nem é mascarado sem
  `--incluir-suspeitas`) e testes dos códigos de saída da tabela 5.1;
- README com GIF, instalação via `uvx`/`pipx` e limitações honestas;
- ADRs: CLI, build backend, regra de confiança/risco, CNPJ alfanumérico;
- tag `fase-1-concluida`; rascunho do post entregue.

## 12. Deixado ao construtor

Nomes internos de funções e tipos; a regex exata de e-mail; o formato da lista de DDDs
(constante no código, com a fonte citada); a ferramenta do GIF; o layout fino da tabela;
o tratamento de CSV sem cabeçalho (só se for trivial); a cobertura mínima de testes, se
ele quiser fixar uma.
