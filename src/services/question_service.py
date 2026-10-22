"""录题与"我的题目"列表（方案三-13）。

路由只调这里的三个函数：`new_errors()` 拿校验结果贴回表单、`create()` 落库、
`mine()` / `shared_pool()` 取列表。SQL 一律不在这一层出现。
"""

from config import prompts
from src.data.repository.question_repo import QuestionRepo
from src.domain.question_types import registry
from src.services import subject_service


def available_types() -> list[tuple[str, str]]:
    """录题页可选的题型。本期只有简答，选择/填空留到步 21。"""
    return [(name, registry.get(name).label) for name in registry.known()]


def new_errors(conn, form: dict) -> list[str]:
    """把"能不能录"的判定集中在这儿：科目 → 题型 → 题型自己的字段。"""
    errors = []
    try:
        subject_service.require_usable(conn, form.get("subject_id"))
    except Exception:
        errors.append(prompts.SUBJECT_UNUSABLE)
    type_name = (form.get("type") or "").strip()
    if type_name not in registry.known():
        errors.append("这个题型还没做，请先用现有的题型。")
        return errors
    return errors + registry.get(type_name).validate(form)


def create(conn, user_id: int, form: dict) -> int:
    """录一道题。调用前必须先过 `new_errors()`——这里不重复校验，避免两处规则漂移。"""
    handler = registry.get(form["type"])
    options_json, answer_json = handler.parse(form)
    return QuestionRepo(conn, user_id).add(
        subject_id=int(form["subject_id"]), type_name=handler.type,
        stem=(form.get("stem") or "").strip(), options_json=options_json,
        answer_json=answer_json, explanation=(form.get("explanation") or "").strip())


def widget(type_name: str, place: str) -> str:
    """答案控件的 HTML。`place` 取 'form'（录题）或 'answer'（复习作答）——
    两个页面拿的是同一份，所以改一处两处一起变。"""
    return registry.get(type_name).render_widget(place)


def mine(conn, user_id: int, page: int = 1, subject_id=None):
    return QuestionRepo(conn, user_id).mine(page=page, subject_id=subject_id)


def shared_pool(conn, user_id: int, page: int = 1, subject_id=None):
    return QuestionRepo(conn, user_id).shared_pool(page=page, subject_id=subject_id)
