from opsweave.api.memory_store import append_turn
from opsweave.api.routes import conversations


def test_conversation_crud_and_history_pagination(client):
    client.app.dependency_overrides[conversations.current_user] = lambda: (
        "alice",
        "viewer",
    )
    created = client.post("/api/conversations", json={"title": "巡检"})
    assert created.status_code == 200
    conversation_id = created.json()["conversation_id"]

    append_turn("alice", conversation_id, "问题一", "回答一")
    append_turn("alice", conversation_id, "问题二", "回答二")

    page = client.get(f"/api/conversations/{conversation_id}/messages?limit=2&offset=1")
    assert page.status_code == 200
    assert [item["content"] for item in page.json()["items"]] == ["回答一", "问题二"]

    renamed = client.patch(
        f"/api/conversations/{conversation_id}", json={"title": "生产巡检"}
    )
    assert renamed.json()["title"] == "生产巡检"
    assert client.get("/api/conversations").json()["items"][0]["title"] == "生产巡检"

    assert client.delete(f"/api/conversations/{conversation_id}").status_code == 200
    assert (
        client.get(f"/api/conversations/{conversation_id}/messages").status_code == 404
    )


def test_conversations_are_isolated_by_user(client):
    client.app.dependency_overrides[conversations.current_user] = lambda: (
        "alice",
        "viewer",
    )
    conversation_id = client.post("/api/conversations", json={}).json()[
        "conversation_id"
    ]

    client.app.dependency_overrides[conversations.current_user] = lambda: (
        "bob",
        "viewer",
    )
    assert (
        client.get(f"/api/conversations/{conversation_id}/messages").status_code == 404
    )
    assert (
        client.patch(
            f"/api/conversations/{conversation_id}", json={"title": "窥探"}
        ).status_code
        == 404
    )
    assert client.delete(f"/api/conversations/{conversation_id}").status_code == 404
