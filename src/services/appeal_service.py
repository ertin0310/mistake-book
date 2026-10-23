"""申诉与反馈（方案三-25）。

★ **不建站内信**：用户下次打开这个页面就看到状态与回复——一次查询，零状态（二-7）。
★ 同一对象只允许一条 `open`；处理完之后允许再提，所以判重在服务层，不上唯一索引。
★ 被处置的作者永远看不到是谁提的：它是申诉通道，不是对骂场。
"""

from config import appeal, prompts
from src.data.repository.appeal_repo import AppealRepo
from src.domain.errors import ValidationError

MAX_REASON = 500


def categories() -> list:
    """表单下拉：`[(键, 中文名), ...]`。加一类只改 `config/appeal.py`。"""
    return list(appeal.LABELS.items())


def submit(conn, user_id: int, form: dict) -> int:
    category = (form.get("category") or "").strip()
    if category not in appeal.LABELS:
        raise ValidationError(prompts.APPEAL_BAD_CATEGORY)
    reason = (form.get("reason") or "").strip()
    if not reason:
        raise ValidationError(prompts.APPEAL_REASON_REQUIRED)
    if len(reason) > MAX_REASON:
        raise ValidationError(prompts.APPEAL_TOO_LONG.format(limit=MAX_REASON))
    target_type = appeal.TARGET_OF[category]
    target_id = _target_id(form, target_type)
    repo = AppealRepo(conn, user_id)
    if repo.open_on(target_type, target_id):
        raise ValidationError(prompts.APPEAL_ALREADY_OPEN)
    return repo.submit(category, target_type, target_id, reason)


def mine(conn, user_id: int) -> list:
    return _describe(AppealRepo(conn, user_id).mine())


def queue(conn, status: str = "open") -> list:
    return _describe(AppealRepo(conn).queue(status))


def resolve(conn, admin_id: int, appeal_id: int, reply: str) -> bool:
    reply = (reply or "").strip()
    if not reply:
        raise ValidationError(prompts.APPEAL_REPLY_REQUIRED)
    return AppealRepo(conn, admin_id).resolve(appeal_id, admin_id, reply) > 0


def _target_id(form, target_type):
    if target_type == "none":
        return None
    raw = form.get("target_id")
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValidationError(prompts.APPEAL_TARGET_REQUIRED) from None


def _describe(rows) -> list:
    """列表页要显示中文类型名与对象描述，模板里不查库、也不判 `category`。"""
    out = []
    for row in rows:
        item = dict(row)
        item["category_label"] = appeal.LABELS.get(row["category"], row["category"])
        item["status_label"] = prompts.APPEAL_STATUS_LABELS[row["status"]]
        item["target"] = _target_text(row["target_type"], row["target_id"])
        out.append(item)
    return out


def _target_text(target_type, target_id):
    if target_type == "question":
        return prompts.APPEAL_TARGET_QUESTION.format(id=target_id)
    if target_type == "knowledge_point":
        return prompts.APPEAL_TARGET_POINT.format(id=target_id)
    return prompts.APPEAL_TARGET_NONE
