from fastapi import HTTPException
from pymilvus.exceptions import MilvusException

from opsweave.api.routes import retrieval


def test_search_routes_through_retrieval_pipeline(client, monkeypatch, mock_data):
    calls = {}

    def fake_pipeline(**kwargs):
        calls.update(kwargs)
        return {
            "results": [
                {
                    "text": mock_data["chunks"][0]["text"],
                    "score": 0.9,
                    "source": "alice.txt",
                }
            ]
        }

    monkeypatch.setattr(retrieval, "run_retrieval_pipeline", fake_pipeline)
    response = client.post(
        "/api/retrieval/search", json={"query": "question", "top_k": 3}
    )
    assert response.status_code == 200
    assert response.json()["results"][0]["text"] == mock_data["chunks"][0]["text"]
    assert calls["user_id"] == mock_data["users"][0]["username"]
    assert calls["top_k"] == 3
    # 直连检索必须走带 build_index 的 LangGraph 管道，不能裸用 Retriever
    assert calls["role"] is not None
    assert calls["collection_name"] == retrieval.DEFAULT_COLLECTION


def test_search_maps_pipeline_error_to_503(client, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("Failed to connect to Milvus")

    monkeypatch.setattr(retrieval, "run_retrieval_pipeline", boom)
    response = client.post("/api/retrieval/search", json={"query": "question"})
    assert response.status_code == 503
    assert "Milvus" in response.json()["detail"]


def test_search_maps_milvus_exception_to_actionable_503(client, monkeypatch):
    def boom(**kwargs):
        raise MilvusException(code=2, message="server unavailable")

    monkeypatch.setattr(retrieval, "run_retrieval_pipeline", boom)
    response = client.post("/api/retrieval/search", json={"query": "question"})
    assert response.status_code == 503
    assert "向量库连接失败" in response.json()["detail"]
    assert "Milvus 已启动" in response.json()["detail"]


def test_direct_index_build_requires_admin(client):
    client.app.dependency_overrides[retrieval.require_admin] = lambda: (
        _ for _ in ()
    ).throw(HTTPException(status_code=403))
    response = client.post("/api/retrieval/build")
    assert response.status_code == 403
