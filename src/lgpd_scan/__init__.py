"""LGPD-Scan: encontra dados pessoais brasileiros, avalia o risco e anonimiza.

Módulos planejados (veja a arquitetura no README da raiz):

=================  ================================================================
Módulo             Responsabilidade
=================  ================================================================
``cli.py``         Interface de linha de comando (``lgpd-scan scan``, ``lgpd-scan anonymize``)
``readers/``       Leitura de CSV, Excel, Parquet e SQLite
``detectors/``     Um detector por tipo de dado pessoal
``scoring.py``     Confiança da detecção e nível de risco
``report.py``      Saída em terminal, JSON e HTML
``anonymize.py``   Modos ``mask``, ``hash``, ``redact``, ``drop``
=================  ================================================================
"""

import importlib.metadata

__version__ = importlib.metadata.version("lgpd-scan")
