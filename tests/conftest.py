import json
from pathlib import Path

import pytest

from fakebase.config import Config
from fakebase.manager import FakeBase

BASE_CONFIG = {
    "Settings": {"locale": "pt_BR", "seed": 123, "storage": "memory"},
    "Schematics": {
        "user": {
            "name": {"method": "humanName", "gender": "__gender"},
            "gender": {"method": "choice", "data": ["male", "female"]},
            "email": {"method": "email", "name": "__name", "unique": True},
            "age": {"method": "integer", "start": 18, "stop": 80},
            "active": {"method": "boolean", "chance": 0.7},
            "seq": {"method": "autoIncrement", "start": 1},
            "cart": {
                "method": "chooseSeveral",
                "data": "@products:[name,price]:price<50@",
                "repeat": False,
                "maxValue": 2,
            },
        },
        "product": {
            "name": {"method": "words", "count": 2, "transform": "title"},
            "price": {"method": "number", "start": 10, "stop": 90, "precision": 2},
            "stock": {"method": "integer", "start": 0, "stop": 50},
        },
    },
    "DataBase": {
        "users": {"schema": "user", "size": 6},
        "products": {"schema": "product", "size": 10},
    },
}


def build_config(tmp_path: Path, **overrides) -> Config:
    raw = json.loads(json.dumps(BASE_CONFIG))
    return Config.from_dict(raw, path=tmp_path / "config.fakebase.json", **overrides)


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return build_config(tmp_path)


@pytest.fixture
def fakebase(config) -> FakeBase:
    instance = FakeBase(config)
    instance.generate()
    yield instance
    instance.close()


@pytest.fixture
def client(fakebase):
    from fastapi.testclient import TestClient

    from fakebase.api import create_app

    with TestClient(create_app(fakebase)) as test_client:
        yield test_client
