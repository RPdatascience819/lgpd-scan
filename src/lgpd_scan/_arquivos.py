"""Verificações de caminho compartilhadas pelos comandos que gravam arquivos (módulo privado)."""

import os
from pathlib import Path


def e_o_mesmo_arquivo(a: Path, b: Path) -> bool:
    """Se `a` e `b` são o mesmo arquivo, mesmo por grafias diferentes do caminho."""
    if a.resolve() == b.resolve():
        return True
    try:
        # `samefile` exige que os dois existam; cobre hardlinks e diferenças de maiúsculas.
        return os.path.samefile(a, b)
    except OSError:
        return False
