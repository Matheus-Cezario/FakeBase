"""FakeBase HTTP API."""

from .app import create_app

__all__ = ["create_app", "serve"]


def serve(fakebase, host: str = None, port: int = None) -> None:
    """Start the server with uvicorn."""
    import uvicorn

    settings = fakebase.settings
    uvicorn.run(
        create_app(fakebase),
        host=host or settings.host,
        port=port or settings.port,
        log_level="info",
    )
