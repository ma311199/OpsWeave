from opsweave.api.routes import knowledge
from opsweave.auth.permissions import Role


def test_collection_list_returns_mock_collection(
    client, milvus, mock_data, monkeypatch
):
    monkeypatch.setattr(knowledge, "get_config", lambda key: '{"ws":"测试知识库"}')
    response = client.get("/api/knowledge/collections")
    assert response.status_code == 200
    item = response.json()["collections"][0]
    assert item["name"] == mock_data["collections"][0]["name"]
    assert item["description"] == "测试知识库"
    assert item["row_count"] == mock_data["collections"][0]["row_count"]


def test_upload_binds_selected_collection_and_owner(client, milvus, mock_data):
    document = mock_data["documents"][0]
    response = client.post(
        f"/api/knowledge/upload?collection_name={mock_data['collections'][0]['name']}",
        files={"file": (document["filename"], document["content"], "text/plain")},
    )
    assert response.status_code == 200
    uploaded = response.json()
    assert uploaded["collection_name"] == "ws"
    row = knowledge._document_row(uploaded["id"], "alice", Role.VIEWER)
    assert row["owner"] == "alice"
    assert row["collection_name"] == "ws"


def test_apply_accepts_all_chunking_strategies_and_rejects_invalid_parameters(
    client, milvus, mock_data, monkeypatch
):
    document = seed_mock_document(client, mock_data)
    monkeypatch.setattr(knowledge, "_build_approved_document", lambda document_id: None)
    monkeypatch.setattr("opsweave.api.routes.config._connect_milvus", lambda: None)
    import pymilvus

    monkeypatch.setattr(pymilvus.utility, "list_collections", lambda: ["ws"])
    client.app.dependency_overrides[knowledge.current_user] = lambda: (
        "admin",
        Role.ADMIN,
    )
    payload = {"chunk_size": 512, "overlap": 64}
    for strategy in (
        "fixed",
        "sentence",
        "paragraph",
        "recursive",
        "sliding",
        "structure",
        "semantic",
        "summary",
    ):
        response = client.post(
            f"/api/knowledge/documents/{document['id']}/apply",
            json={**payload, "strategy": strategy},
        )
        assert response.status_code == 200, (strategy, response.text)
        with knowledge._get_conn() as conn:
            conn.execute(
                "UPDATE knowledge_documents SET status = 'uploaded' WHERE id = ?",
                (document["id"],),
            )

    assert (
        client.post(
            f"/api/knowledge/documents/{document['id']}/apply",
            json={"strategy": "unknown", **payload},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/knowledge/documents/{document['id']}/apply",
            json={"strategy": "sliding", "chunk_size": 64, "overlap": 64},
        ).status_code
        == 422
    )


def test_upload_rejects_unknown_collection(client, milvus, mock_data):
    response = client.post(
        "/api/knowledge/upload?collection_name=not-configured",
        files={"file": ("guide.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400


def seed_mock_document(client, mock_data, owner="alice", status="uploaded"):
    document = next(item for item in mock_data["documents"] if item["owner"] == owner)
    knowledge._init_knowledge()
    path = knowledge._document_dir(owner) / f"{document['id']}_{document['filename']}"
    path.write_bytes(document["content"])
    with knowledge._get_conn() as conn:
        conn.execute(
            "INSERT INTO knowledge_documents (id, owner, filename, path, size, strategy, status, collection_name) VALUES (?, ?, ?, ?, ?, '', ?, 'ws')",
            (
                document["id"],
                owner,
                document["filename"],
                str(path),
                len(document["content"]),
                status,
            ),
        )
    return document


def test_user_application_waits_for_admin_approval(
    client, milvus, mock_data, monkeypatch
):
    document = seed_mock_document(client, mock_data)
    processed = []
    monkeypatch.setattr(
        knowledge,
        "_process_document",
        lambda document_id: processed.append(document_id),
    )

    response = client.post(
        f"/api/knowledge/documents/{document['id']}/apply",
        json={"strategy": "sentence", "chunk_size": 512, "overlap": 64},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert processed == []

    client.app.dependency_overrides[knowledge.current_user] = lambda: (
        "admin",
        Role.ADMIN,
    )
    response = client.post(
        f"/api/knowledge/applications/{document['id']}/review", json={"approve": True}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "processing"
    assert processed == [document["id"]]
    assert (
        client.get("/api/knowledge/documents").json()["documents"][0]["status"]
        == "processing"
    )


def test_user_can_cancel_pending_application(client, mock_data):
    document = seed_mock_document(client, mock_data, status="pending")
    response = client.post(
        f"/api/knowledge/documents/{document['id']}/cancel-application"
    )
    assert response.status_code == 200
    assert response.json()["status"] == "uploaded"
    assert (
        client.get("/api/knowledge/documents").json()["documents"][0]["status"]
        == "uploaded"
    )


def test_user_cannot_cancel_processing_application(client, mock_data):
    document = seed_mock_document(client, mock_data, status="processing")
    response = client.post(
        f"/api/knowledge/documents/{document['id']}/cancel-application"
    )
    assert response.status_code == 409


def test_user_cannot_access_other_users_document(client, mock_data):
    document = seed_mock_document(client, mock_data, owner="bob")
    assert (
        client.get(f"/api/knowledge/documents/{document['id']}/chunks").status_code
        == 404
    )
    assert (
        client.delete(f"/api/knowledge/documents/{document['id']}").status_code == 404
    )


def test_non_admin_cannot_approve(client, mock_data):
    document = seed_mock_document(client, mock_data)
    response = client.post(
        f"/api/knowledge/applications/{document['id']}/review", json={"approve": True}
    )
    assert response.status_code == 403


def test_knowledge_status_reports_milvus_and_selected_collection(
    client, milvus, monkeypatch
):
    from pymilvus import DataType

    monkeypatch.setattr("opsweave.api.routes.config._connect_milvus", lambda: None)
    monkeypatch.setattr(
        knowledge,
        "get_settings",
        lambda: type("Settings", (), {"embedding_dimension": 2048})(),
    )
    monkeypatch.setattr(
        knowledge,
        "get_config",
        lambda key: "2048" if key == "embedding_dimension" else None,
    )

    class Field:
        def __init__(self, name, dtype, params=None, is_primary=False):
            self.name = name
            self.dtype = dtype
            self.params = params or {}
            self.is_primary = is_primary
            self.auto_id = False

    class Collection:
        def __init__(self, name):
            self.schema = type(
                "Schema",
                (),
                {
                    "fields": [
                        Field("id", DataType.VARCHAR, is_primary=True),
                        Field("document_id", DataType.VARCHAR),
                        Field("text", DataType.VARCHAR),
                        Field("vector", DataType.FLOAT_VECTOR, {"dim": 2048}),
                        Field("user_id", DataType.VARCHAR),
                        Field("filename", DataType.VARCHAR),
                    ]
                },
            )()

    monkeypatch.setattr("pymilvus.Collection", Collection)
    response = client.get("/api/knowledge/status?collection_name=ws")

    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["milvus_connected"] is True
    assert response.json()["collection_ready"] is True
    assert response.json()["schema_valid"] is True
    assert response.json()["vector_dimension"] == 2048
    assert response.json()["collections"] == milvus


def test_knowledge_status_reports_vector_dimension_mismatch(
    client, milvus, monkeypatch
):
    from pymilvus import DataType

    monkeypatch.setattr("opsweave.api.routes.config._connect_milvus", lambda: None)
    monkeypatch.setattr(
        knowledge,
        "get_settings",
        lambda: type("Settings", (), {"embedding_dimension": 2048})(),
    )

    class Field:
        def __init__(self, name, dtype, params=None, is_primary=False):
            self.name = name
            self.dtype = dtype
            self.params = params or {}
            self.is_primary = is_primary
            self.auto_id = False

    class Collection:
        def __init__(self, name):
            self.schema = type(
                "Schema",
                (),
                {
                    "fields": [
                        Field("id", DataType.VARCHAR, is_primary=True),
                        Field("document_id", DataType.VARCHAR),
                        Field("text", DataType.VARCHAR),
                        Field("vector", DataType.FLOAT_VECTOR, {"dim": 1024}),
                        Field("user_id", DataType.VARCHAR),
                        Field("filename", DataType.VARCHAR),
                    ]
                },
            )()

    monkeypatch.setattr("pymilvus.Collection", Collection)
    response = client.get("/api/knowledge/status?collection_name=ws")

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert response.json()["schema_valid"] is False
    assert response.json()["vector_dimension"] == 1024
    assert "维度不匹配" in response.json()["schema_errors"][0]


def test_knowledge_status_without_collection_uses_compatible_collection(
    client, milvus, monkeypatch
):
    from pymilvus import DataType

    monkeypatch.setattr("opsweave.api.routes.config._connect_milvus", lambda: None)
    monkeypatch.setattr(
        knowledge,
        "get_settings",
        lambda: type("Settings", (), {"embedding_dimension": 2048})(),
    )

    class Field:
        def __init__(self, name, dtype, params=None, is_primary=False):
            self.name, self.dtype, self.params = name, dtype, params or {}
            self.is_primary, self.auto_id = is_primary, False

    class Collection:
        def __init__(self, name):
            self.schema = type(
                "Schema",
                (),
                {
                    "fields": [
                        Field("id", DataType.VARCHAR, is_primary=True),
                        Field("document_id", DataType.VARCHAR),
                        Field("text", DataType.VARCHAR),
                        Field("vector", DataType.FLOAT_VECTOR, {"dim": 2048}),
                        Field("user_id", DataType.VARCHAR),
                        Field("filename", DataType.VARCHAR),
                    ]
                },
            )()

    monkeypatch.setattr("pymilvus.Collection", Collection)
    response = client.get("/api/knowledge/status")

    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["collection"] in milvus


def test_knowledge_status_reports_missing_collection(client, milvus, monkeypatch):
    monkeypatch.setattr("opsweave.api.routes.config._connect_milvus", lambda: None)

    response = client.get("/api/knowledge/status?collection_name=missing")

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert response.json()["milvus_connected"] is True
    assert response.json()["collection_ready"] is False


def test_knowledge_status_reports_milvus_connection_failure(client, monkeypatch):
    def fail_connect():
        raise RuntimeError("Milvus unavailable")

    monkeypatch.setattr("opsweave.api.routes.config._connect_milvus", fail_connect)

    response = client.get("/api/knowledge/status")

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert response.json()["milvus_connected"] is False
    assert response.json()["error"] == "Milvus unavailable"
