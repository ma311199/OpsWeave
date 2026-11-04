from opsweave.api.approvals import create_approval, list_approvals, resolve_approval


def test_approval_is_visible_to_requester_and_admin(client):
    from opsweave.api.approvals import _init_approvals
    from opsweave.api.approvals import _get_conn

    _init_approvals()
    with _get_conn() as conn:
        conn.execute("DELETE FROM tool_approvals")
    approval_id = create_approval("alice", "conv-1", "remote", "restart", {"service": "api"})

    assert list_approvals("alice", False)[0]["id"] == approval_id
    assert list_approvals("admin", True)[0]["arguments"] == {"service": "api"}
    assert list_approvals("bob", False) == []


def test_requester_or_admin_can_resolve_once(client):
    approval_id = create_approval("alice", "conv-1", "remote", "restart", {})

    assert resolve_approval(approval_id, "bob", False, True) is None
    assert resolve_approval(approval_id, "alice", False, False)["status"] == "rejected"
    assert resolve_approval(approval_id, "admin", True, True) is None
