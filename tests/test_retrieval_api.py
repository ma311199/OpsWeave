from typing import ClassVar

from opsweave.agents import retrieval_pipeline
from opsweave.api.routes import retrieval
from opsweave.auth.permissions import Role


def test_search_passes_authenticated_user_to_pipeline(client, monkeypatch, mock_data):
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
        "/api/retrieval/search",
        json={
            "query": "question",
            "top_k": 3,
            "collection_name": "ws",
            "options": {"decompose": False},
        },
    )
    assert response.status_code == 200
    assert response.json()["results"][0]["text"] == mock_data["chunks"][0]["text"]
    assert calls["user_id"] == mock_data["users"][0]["username"]
    assert calls["top_k"] == 3
    assert calls["collection_name"] == "ws"
    assert calls["role"] is Role.VIEWER


def test_direct_index_build_requires_admin(client):
    response = client.post("/api/retrieval/build")
    assert response.status_code == 403


class _FakeRetriever:
    """记录 build_index / retrieve 调用的假检索器。"""

    instances: ClassVar[list["_FakeRetriever"]] = []
    results: ClassVar[list[tuple[str, float, str]]] = []

    def __init__(self):
        self.built_collections: list[str] = []
        self.retrieve_calls: list[dict] = []
        _FakeRetriever.instances.append(self)

    def build_index(
        self, collection_name: str = "opsweave", documents_path: str | None = None
    ) -> None:
        self.built_collections.append(collection_name)

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        role: Role = Role.ADMIN,
        user_id: str | None = None,
    ):
        self.retrieve_calls.append(
            {"query": query, "top_k": top_k, "role": role, "user_id": user_id}
        )
        return [
            type("Result", (), {"text": text, "score": score, "source": source})()
            for text, score, source in _FakeRetriever.results
        ]


def _reset(monkeypatch):
    retrieval_pipeline.clear_retrieval_index_cache()
    _FakeRetriever.instances.clear()
    _FakeRetriever.results = []
    monkeypatch.setattr(retrieval_pipeline, "Retriever", _FakeRetriever)


def test_pipeline_builds_index_before_search_and_caches(monkeypatch):
    _reset(monkeypatch)
    _FakeRetriever.results = [("chunk a", 0.9, "doc.txt"), ("chunk b", 0.5, "doc.txt")]

    state = retrieval_pipeline.run_retrieval_pipeline(
        query="问题", role=Role.VIEWER, user_id="alice", top_k=2, collection_name="c1"
    )
    # 索引在检索前构建（回归验证：直连检索不再因未建索引而 503）
    assert _FakeRetriever.instances[0].built_collections == ["c1"]
    assert _FakeRetriever.instances[0].retrieve_calls[0]["user_id"] == "alice"
    assert [item["text"] for item in state["results"]] == ["chunk a", "chunk b"]

    # 第二次调用复用缓存的索引，不再重新构建
    retrieval_pipeline.run_retrieval_pipeline(
        query="again", role=Role.VIEWER, user_id="alice", top_k=2, collection_name="c1"
    )
    assert len(_FakeRetriever.instances) == 1

    # 按 collection 清空缓存后会重建
    retrieval_pipeline.clear_retrieval_index_cache("c1")
    retrieval_pipeline.run_retrieval_pipeline(
        query="again", role=Role.VIEWER, user_id="alice", top_k=2, collection_name="c1"
    )
    assert len(_FakeRetriever.instances) == 2


def test_pipeline_dedupes_and_truncates(monkeypatch):
    _reset(monkeypatch)
    _FakeRetriever.results = [
        ("dup", 0.5, "a.txt"),
        ("dup", 0.9, "a.txt"),
        ("other", 0.7, "b.txt"),
        ("overflow", 0.1, "c.txt"),
    ]

    state = retrieval_pipeline.run_retrieval_pipeline(
        query="问题", role=Role.VIEWER, user_id="alice", top_k=2, collection_name="c2"
    )
    # 相同 (source, text) 保留最高分，并按相似度截取 top_k
    assert [item["text"] for item in state["results"]] == ["dup", "other"]
    assert state["results"][0]["score"] == 0.9


def test_pipeline_option_stubs_are_passthrough(monkeypatch):
    _reset(monkeypatch)
    _FakeRetriever.results = [("a", 0.4, "s"), ("b", 0.8, "s")]

    state = retrieval_pipeline.run_retrieval_pipeline(
        query="问题",
        role=Role.VIEWER,
        user_id="alice",
        top_k=2,
        collection_name="c3",
        options={"decompose": True, "rerank": True},
    )
    # 分解与重排占位节点透传：仍单次检索、按相似度排序返回
    assert len(_FakeRetriever.instances[0].retrieve_calls) == 1
    assert [item["text"] for item in state["results"]] == ["b", "a"]
