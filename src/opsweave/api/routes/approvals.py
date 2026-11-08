from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...auth.permissions import Role
from ...tools.mcp_client import call_tool
from ..approvals import finish_approval, list_approvals, resolve_approval
from ..auth import current_user

router = APIRouter()


class ApprovalDecision(BaseModel):
    approve: bool


@router.get("")
def get_approvals(principal: tuple[str, Role] = Depends(current_user)) -> dict:
    username, role = principal
    return {"approvals": list_approvals(username, role is Role.ADMIN)}


@router.post("/{approval_id}/decision")
def decide_approval(
    approval_id: str,
    req: ApprovalDecision,
    principal: tuple[str, Role] = Depends(current_user),
) -> dict:
    username, role = principal
    approval = resolve_approval(approval_id, username, role is Role.ADMIN, req.approve)
    if approval is None:
        raise HTTPException(status_code=404, detail="审批不存在、已处理或无权处理")
    if not req.approve:
        return {"status": "rejected", "approval_id": approval_id}

    try:
        result = call_tool(
            approval["server_id"],
            approval["tool_name"],
            approval["arguments"],
            role,
            approval["username"],
        )
    except Exception as exc:
        finish_approval(approval_id, "failed")
        raise HTTPException(
            status_code=502, detail=f"审批已通过，但工具执行失败：{exc}"
        ) from exc
    finish_approval(approval_id, "completed")
    return {"status": "completed", "approval_id": approval_id, "result": result}
