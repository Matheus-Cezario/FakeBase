"""FakeBase persistence layer."""

from .base import Document, Sort, Storage
from .monty import MEMORY, STORAGE_BACKENDS, MontyStorage

__all__ = ["Document", "Sort", "Storage", "MontyStorage", "MEMORY", "STORAGE_BACKENDS"]


def open_storage(settings) -> MontyStorage:
    """Open the database described by :class:`~fakebase.config.Settings`."""
    return MontyStorage(
        settings.storagePath,
        database=settings.database,
        backend=settings.storage,
    )
