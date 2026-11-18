"""Configuração compartilhada da suíte: nenhum teste pode abrir conexão de rede."""

import socket
from typing import Any, NoReturn

import pytest


def _socket_bloqueado(*_args: Any, **_kwargs: Any) -> NoReturn:
    raise RuntimeError("rede bloqueada nos testes")


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch: pytest.MonkeyPatch) -> None:
    """Troca `socket.socket` por um substituto que falha, em todo teste."""
    monkeypatch.setattr(socket, "socket", _socket_bloqueado)
