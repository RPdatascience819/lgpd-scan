# Contas e serviços

Inventário **sem nenhum segredo**: aqui não entram senhas, tokens, chaves,
códigos de recuperação nem e-mails de login. Credenciais ficam no gerenciador
de senhas do responsável; chaves de API são geradas só na fase que as usa.

| Serviço | Para que serve | Fase que usa | Conta criada | 2FA | Plano |
|---|---|---|---|---|---|
| GitHub | Código, PRs, CI (Actions), Dependabot, ruleset da `main` | Fase 0 em diante | sim | sim | Free |
| PyPI | Publicar o pacote `lgpd-scan` | Publicação | não | obrigatório pelo PyPI | Gratuito |
| TestPyPI | Ensaiar a publicação sem afetar o PyPI real | Publicação | não | obrigatório pelo PyPI | Gratuito |

## Publicação sem token (Trusted Publishing)

O pacote será publicado pelo GitHub Actions via **Trusted Publishing** (OIDC):
o PyPI confia num workflow específico deste repositório e não existe token de
API para guardar ou vazar. Configuração na fase de publicação, não antes.

## Regras

- 2FA ativo em toda conta que tenha acesso de escrita ao projeto.
- Códigos de recuperação no gerenciador de senhas, nunca no repositório nem em
  nota solta.
- Nenhum segredo é colado em chat, issue, PR ou log de CI.
- Token só quando não houver alternativa sem token, com o menor escopo e a
  menor validade possíveis.
