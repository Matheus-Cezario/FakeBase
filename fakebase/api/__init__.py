"""API HTTP do FakeBase."""

from .app import create_app

__all__ = ["create_app", "serve"]


def serve(fakebase, host: str = None, port: int = None) -> None:
    """Sobe o servidor com uvicorn."""
    import uvicorn

    settings = fakebase.settings
    uvicorn.run(
        create_app(fakebase),
        host=host or settings.host,
        port=port or settings.port,
        log_level="info",
    )
