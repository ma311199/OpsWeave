from opsweave.api.routes import retrieval


def test_search_passes_authenticated_user_to_retriever(client, monkeypatch, mock_data):
    calls = {}

    class FakeRetriever:
        def retrieve(self, **kwargs):
            calls.update(kwargs)
            return [
                type(
                    "Result",
                    (),
                    {
                        "text": mock_data["chunks"][0]["text"],
                        "score": 0.9,
                        "source": "alice.txt",
                    },
                )()
            ]

    monkeypatch.setattr(retrieval, "Retriever", FakeRetriever)
    response = client.post(
        "/api/retrieval/search", json={"query": "question", "top_k": 3}
    )
    assert response.status_code == 200
    assert response.json()["results"][0]["text"] == mock_data["chunks"][0]["text"]
    assert calls["user_id"] == mock_data["users"][0]["username"]
    assert calls["top_k"] == 3


def test_direct_index_build_requires_admin(client):
    response = client.post("/api/retrieval/build")
    assert response.status_code == 403
