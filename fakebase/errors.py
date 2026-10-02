"""FakeBase exceptions.

They all inherit from :class:`FakeBaseError`, which lets the CLI catch any
expected failure and show it without a stack trace.
"""


class FakeBaseError(Exception):
    """Base FakeBase error."""


class ConfigError(FakeBaseError):
    """Configuration file missing, empty or malformed."""


class SchemaError(FakeBaseError):
    """Invalid schematic (unknown field, dependency cycle, ...)."""


class GeneratorError(FakeBaseError):
    """Error while running a value generator."""


class TransformError(FakeBaseError):
    """Error while running a pipe/transform."""


class LinkError(FakeBaseError):
    """Invalid or circular reference between databases."""


class StorageError(FakeBaseError):
    """Persistence layer failure."""


class NotFoundError(FakeBaseError):
    """Collection or document does not exist."""


class QueryError(FakeBaseError):
    """Invalid query parameters."""
