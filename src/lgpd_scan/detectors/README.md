# `detectors/`: detectores de dados pessoais

Um módulo por tipo (`cpf.py`, `cnpj.py`, `phone.py`, ...). Cada detector combina
formato (regex) e validação (ex.: dígitos verificadores do CPF/CNPJ) para reduzir
falsos positivos. Preenchido na **Fase 1**.

Regra do projeto: todo detector entra com testes de casos válidos, inválidos e
de borda, usando apenas valores **gerados pelo algoritmo**, nunca copiados de
pessoas ou empresas reais.

> Provisório: sai quando o `__init__.py` deste subpacote existir.
