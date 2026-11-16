# CLAUDE.md — LGPD-Scan

CLI em Python que encontra dados pessoais brasileiros (CPF, CNPJ, RG, CEP,
telefone, placa, e-mail) em CSV/Excel/Parquet/SQLite, avalia o risco e
anonimiza. Projeto de portfólio, público. Desenvolvedor solo; o agente atua
como Tech Lead e mentor. Documento de referência: `README.md` (visão do produto)
e `docs/adr/`.

## Protocolo de trabalho

- Um passo por vez; esperar "próximo" antes de seguir.
- Cada passo: Objetivo · Por quê · Termos novos · Conteúdo completo e comandos
  exatos · Como verificar · Commit sugerido (Conventional Commits, pt-BR).
- Gravar arquivos ou executar comandos só após "pode executar".
- Cada passo termina em commit. Erro → voltar ao último checkpoint, não remendar.
  Comando destrutivo só com explicação e confirmação.
- `main` recebe só o commit inicial; depois, branch curta + PR com checklist.
  O usuário faz o merge.
- Versões: consultar a documentação oficial antes de fixar; fixar por tag ou lock.
- Desvio do plano: avisar, propor, mudar só com ok, registrar em ADR (`docs/adr/`).
- Escopo da fase atual: Fase 0 (fundação, sem código de aplicação).
  Pedido fora dela → lembrar e confirmar.

## Ambiente

- Desenvolvimento em Python 3.14 com `uv`. O caminho local tem acento
  ("Portifólios"): Python ≤ 3.12 quebra a instalação editável. Nunca usar o
  `python` 3.11 do PATH neste projeto.

## Segurança e dados

- Contas, logins, chaves, tokens, senhas e pagamentos são feitos pelo usuário.
- Nunca pedir segredo no chat, nunca exibir `.env`, nunca commitar `.env`.
- Segredo falso para teste só localmente, nunca no remoto.
- **Nenhum dado pessoal real no repositório.** Arquivos de dados só em
  `examples/`, e só sintéticos (gerados por código). O `.gitignore` bloqueia
  `.csv`/`.xlsx`/`.parquet`/`.db` fora de `examples/`; não contornar com `git add -f`.
- Testes de detectores usam CPFs/CNPJs gerados pelo algoritmo, nunca copiados
  de pessoas ou empresas reais.
