# `src/lgpd_scan/`: pacote principal

Código do LGPD-Scan. Preenchido a partir da **Fase 1**.

Módulos planejados (veja a arquitetura no README da raiz):

| Módulo | Responsabilidade |
|---|---|
| `cli.py` | Interface de linha de comando (`lgpd-scan scan`, `lgpd-scan anonymize`) |
| `readers/` | Leitura de CSV, Excel, Parquet e SQLite |
| `detectors/` | Um detector por tipo de dado pessoal |
| `scoring.py` | Confiança da detecção e nível de risco |
| `report.py` | Saída em terminal, JSON e HTML |
| `anonymize.py` | Modos `mask`, `hash`, `redact`, `drop` |

> Este README é provisório: sai na Fase 1, quando a docstring do
> `__init__.py` assumir a documentação do pacote.
