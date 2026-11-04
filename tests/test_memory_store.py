from opsweave.api.memory_store import append_long_term_memory, append_turn, get_history, get_long_term_memory
from opsweave.config.database import _get_conn


def test_short_term_history_is_isolated_and_limited(client):
    with _get_conn() as conn:
        conn.execute("DELETE FROM chat_messages")
    append_turn("alice", "conversation-a", "你好", "你好！")
    append_turn("alice", "conversation-b", "另一个会话", "回复")

    assert get_history("alice", "conversation-a") == [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！"},
    ]
    assert get_history("bob", "conversation-a") == []


def test_long_term_memory_is_saved_as_user_markdown(client):
    append_long_term_memory("alice", "用户偏好中文回答")

    memory = get_long_term_memory("alice")
    assert memory.startswith("# 长期记忆")
    assert "用户偏好中文回答" in memory
