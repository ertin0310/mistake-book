"""知识点业务层（方案三-6）：提交即入池、查重只认"能用"的行、编辑后回到待审。

★ 三条规矩都在这层，路由与模板不各自判：
  1. **提交即 `approved`**，所有人立刻可用；审核队列只是 `reviewed_by IS NULL`，
     不是另一种状态——少一个状态就少一类"它到底能不能用"的争论（二-7 零状态优先）。
  2. **查重按归一化名，且只算能用的行**：被驳回/下架的绝不占名字，否则会出
     "叫乙去选用一条只有甲看得见的记录"那种死局（三-6 ★，步 14 把它钉成了用例）。
  3. **不做近似匹配**：「牛顿第二定律」与「牛顿第二定律的应用」是两条，有意为之。
     模糊匹配会把不同的人理解的东西糊成一坨，后期拆不开。
"""

import sqlite3

from config import prompts
from src.data.repository.knowledge_repo import KnowledgeRepo
from src.data.repository.subject_repo import SubjectRepo
from src.domain import normalize
from src.domain.errors import NotFoundError, ValidationError


def pool(conn, subject_id, page: int = 1):
    """当前能用的知识点：选了科目就只看那一科，没选就列全部（浏览页就是这一份）。"""
    return KnowledgeRepo(conn).browse(subject_id, page)


def mine(conn, user_id: int) -> list:
    """我提交过的，含被驳回与下架的——那两档只有我看得见（policy 口径已经管好）。"""
    return KnowledgeRepo(conn, user_id).submitted_by(user_id)


def pending(conn) -> list:
    """待审队列（步 23 后台页面读的就是它）。"""
    return KnowledgeRepo(conn).pending()


def check(conn, subject_id: int, name: str) -> list:
    """同名下"能用"的那些行。空列表 = 这个名字没被占。"""
    if not (name or "").strip():
        return []
    return KnowledgeRepo(conn).same_name(subject_id, name)


def create(conn, user_id: int, form: dict) -> dict:
    """提交一条知识点。

    返回 `{"id": ..., "duplicates": [...]}`：调用方先看 `duplicates`——
    有同名且用户没勾「这不是同一个知识点」时，这里不落库，只把可选项交回表单页。
    """
    subject_id = _require_subject(conn, form.get("subject_id"))
    name = (form.get("name") or "").strip()
    if not name:
        raise ValidationError(prompts.KP_NAME_REQUIRED)
    if len(name) > prompts.KP_NAME_LIMIT:
        raise ValidationError(prompts.KP_NAME_TOO_LONG.format(limit=prompts.KP_NAME_LIMIT))
    duplicates = check(conn, subject_id, name)
    if duplicates and not form.get("not_same"):
        return {"id": None, "duplicates": duplicates}
    try:
        new_id = KnowledgeRepo(conn, user_id).submit(user_id, subject_id, name)
    except sqlite3.IntegrityError:
        # 勾了「这不是同一个知识点」也救不了这一种情况：同一科目下同名只能有一条 approved，
        # 那是 `uq_kp_approved` 定的事实。两条一模一样的名字对别人毫无意义，
        # 所以这里不偷偷改名硬塞，只把话说清楚。
        raise ValidationError(prompts.KP_SAME_SUBJECT_CLASH) from None
    return {"id": new_id, "duplicates": []}


def rename(conn, user_id: int, point_id: int, name: str) -> int:
    """作者改名重提：内容更新 + 回到待审。改不到就是这条不是他提交的 → 404（七-1）。"""
    name = (name or "").strip()
    if not name:
        raise ValidationError(prompts.KP_NAME_REQUIRED)
    if not KnowledgeRepo(conn, user_id).resubmit(point_id, user_id, name):
        raise NotFoundError(prompts.NOT_FOUND)
    return point_id


def describe(conn, rows) -> list:
    """列表页要的 `(id, 名称, 科目名, 状态文案)`，模板里不查库（二-14）。"""
    subjects = SubjectRepo(conn).name_map()
    return [{"id": row["id"], "name": row["name"], "subject": subjects.get(row["subject_id"], ""),
             "status": row["status"], "label": prompts.KP_STATUS_LABELS[row["status"]],
             "pending": row["reviewed_by"] is None,      # 队列 = reviewed_by IS NULL，不是另一种状态
             "note": row["review_note"] or ""} for row in rows]


def is_same_name(a: str, b: str) -> bool:
    """归一化后是否同名——测试与提示都拿它判，别在模板里比字符串。"""
    return normalize.normalize_name(a) == normalize.normalize_name(b)


def _require_subject(conn, subject_id) -> int:
    try:
        key = int(subject_id)
    except (TypeError, ValueError):
        raise ValidationError(prompts.SUBJECT_UNUSABLE) from None
    if not SubjectRepo(conn).is_usable(key):
        raise ValidationError(prompts.SUBJECT_UNUSABLE)
    return key
