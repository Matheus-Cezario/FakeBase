"""Registro de geradores de valores do FakeBase.

Importar este pacote registra todos os geradores embutidos. Para adicionar
um gerador próprio basta decorar uma função com :func:`generator`.
"""

from .base import (  # noqa: F401
    REGISTRY,
    GenContext,
    GeneratorSpec,
    available,
    exists,
    generator,
    get,
    load_data,
    read_lines,
    resolve_path,
)

# Importar estes módulos registra os geradores embutidos no REGISTRY.
from . import people, primitives, sequences, temporal, text

BUILTIN_MODULES = (primitives, sequences, temporal, people, text)

__all__ = [
    "BUILTIN_MODULES",
    "REGISTRY",
    "GenContext",
    "GeneratorSpec",
    "available",
    "exists",
    "generator",
    "get",
    "load_data",
    "read_lines",
    "resolve_path",
]
