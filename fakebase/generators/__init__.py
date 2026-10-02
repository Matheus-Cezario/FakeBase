"""Registry of FakeBase value generators.

Importing this package registers every built-in generator. To add your own
generator, decorate a function with :func:`generator`.
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

# Importing these modules registers the built-in generators in REGISTRY.
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
