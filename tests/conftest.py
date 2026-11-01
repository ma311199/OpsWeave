import sqlite3

import pytest
from fastapi.testclient import TestClient

from opsweave.api import user_store
from opsweave.api.main import create_app
from opsweave.api.routes import knowledge
from opsweave.auth.permissions import Role


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    def get_conn():
        conn = sqlite3.connect(tmp_path / "opsweave.db")
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(user_store, "_get_conn", get_conn)
    monkeypatch.setattr(knowledge, "_get_conn", get_conn)
    monkeypatch.setattr("opsweave.config.database._get_conn", get_conn)

    class Settings:
        data_dir = str(tmp_path)
        embedding_dimension = 2048

    monkeypatch.setattr(knowledge, "get_settings", lambda: Settings())
    app = create_app()
    app.dependency_overrides[knowledge.current_user] = lambda: ("alice", Role.VIEWER)
    from opsweave.api.auth import require_role
    app.dependency_overrides[require_role] = lambda: Role.VIEWER
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def mock_data(tmp_path):
    return {
        "users": [
            {"username": "alice", "role": "viewer"},
            {"username": "bob", "role": "viewer"},
            {"username": "admin", "role": "admin"},
        ],
        "collections": [{"name": "ws", "description": "测试知识库", "row_count": 2}],
        "documents": [
            {"id": "doc-alice", "owner": "alice", "filename": "alice.txt", "content": b"Alice test document"},
            {"id": "doc-bob", "owner": "bob", "filename": "bob.txt", "content": b"Bob private document"},
        ],
        "chunks": [
            {"id": "chunk-alice-1", "document_id": "doc-alice", "owner": "alice", "ordinal": 0, "text": "Alice test chunk", "embedding_text": "Alice summary"},
            {"id": "chunk-bob-1", "document_id": "doc-bob", "owner": "bob", "ordinal": 0, "text": "Bob private chunk", "embedding_text": "Bob summary"},
        ],
    }


@pytest.fixture
def milvus(monkeypatch, mock_data):
    names = [item["name"] for item in mock_data["collections"]]
    monkeypatch.setattr("opsweave.api.routes.config._connect_milvus", lambda: None)

    class Utility:
        @staticmethod
        def list_collections():
            return names

    class Collection:
        def __init__(self, name):
            self.name = name
            self.num_entities = next(item["row_count"] for item in mock_data["collections"] if item["name"] == name)

    import pymilvus
    monkeypatch.setattr(pymilvus, "utility", Utility)
    monkeypatch.setattr(pymilvus, "Collection", Collection)
    return names
