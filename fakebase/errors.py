"""Exceções do FakeBase.

Todas herdam de :class:`FakeBaseError`, o que permite ao CLI capturar
qualquer falha esperada e apresentá-la sem stack trace.
"""


class FakeBaseError(Exception):
    """Erro base do FakeBase."""


class ConfigError(FakeBaseError):
    """Arquivo de configuração ausente, vazio ou malformado."""


class SchemaError(FakeBaseError):
    """Schematic inválido (campo desconhecido, ciclo de dependência, ...)."""


class GeneratorError(FakeBaseError):
    """Erro ao executar um gerador de valores."""


class TransformError(FakeBaseError):
    """Erro ao executar um pipe/transform."""


class LinkError(FakeBaseError):
    """Referência entre bancos inválida ou cíclica."""


class StorageError(FakeBaseError):
    """Falha na camada de persistência."""


class NotFoundError(FakeBaseError):
    """Coleção ou documento inexistente."""


class QueryError(FakeBaseError):
    """Parâmetros de consulta inválidos."""
