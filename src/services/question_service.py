"""录题与"我的题目"列表（方案三-13）。

路由只调这里的三个函数：`new_errors()` 拿校验结果贴回表单、`create()` 落库、
`mine()` / `shared_pool()` 取列表。SQL 一律不在这一层出现。
"""

import json

from config import prompts
from src.data.repository.question_repo import MINE, QuestionRepo
from src.domain.errors import NotFoundError, ValidationError
from src.domain.question_types import registry
from src.services import review_service, subject_service


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


def widget(type_name: str, place: str, value: str = "") -> str:
    """答案控件的 HTML。`place` 取 'form'（录题）或 'answer'（复习作答）——
    两个页面拿的是同一份，所以改一处两处一起变。"""
    return registry.get(type_name).render_widget(place, value)


def answer_text(answer_json: str) -> str:
    """库里的标准 JSON 还原给人看的文本。读不懂就原样返回，绝不崩。"""
    try:
        data = json.loads(answer_json)
    except ValueError:
        return answer_json
    if isinstance(data, dict):
        return data.get("text") or data.get("letters") or answer_json
    if isinstance(data, list):
        return " ／ ".join("、".join(x) if isinstance(x, list) else str(x) for x in data)
    return str(data)


def next_to_practice(conn, user_id: int):
    """学习模式取下一道练习题（自己的，按录入顺序）。"""
    page = QuestionRepo(conn, user_id).mine(page=1, size=1)
    return page.items[0] if page.items else None


def practice_row(conn, user_id: int, question_id: int):
    page = QuestionRepo(conn, user_id).read_named(
        "mine", f"({MINE}) AND id = :only", {"only": question_id})
    return page.items[0] if page.items else None


def record_practice(conn, user_id: int, row, result: str, submitted: str = "") -> None:
    """记一笔做题结果；`result='wrong'` 由复习服务负责把题排进今日队列（闭环那一环）。"""
    if result not in ("right", "wrong"):
        raise ValidationError(prompts.FIELD_REQUIRED)
    review_service.record_attempt(conn, user_id, row["id"], row["subject_id"], result, submitted)


def mine(conn, user_id: int, page: int = 1, subject_id=None):
    return QuestionRepo(conn, user_id).mine(page=page, subject_id=subject_id)


def shared_pool(conn, user_id: int, page: int = 1, subject_id=None):
    return QuestionRepo(conn, user_id).shared_pool(page=page, subject_id=subject_id)


def save_edit(conn, user_id: int, question_id: int, form: dict) -> None:
    """改题面。校验走和录题同一套规则，不另写一份。

    ★ 先确认"这道题是我的"再动笔：`UPDATE ... WHERE user_id` 打空时改动行数是 0，
      路由却照样会 flash"改好了"——那不是提示，是撒谎（步 14 的越权用例盯这个）。
    """
    require_mine(conn, user_id, question_id)
    handler = registry.get(form["type"])
    options_json, answer_json = handler.parse(form)
    QuestionRepo(conn, user_id).save_edit(question_id, (form.get("stem") or "").strip(),
                                          options_json, answer_json,
                                          (form.get("explanation") or "").strip())


def remove(conn, user_id: int, question_id: int) -> None:
    require_mine(conn, user_id, question_id)
    QuestionRepo(conn, user_id).soft_delete(question_id)


def require_mine(conn, user_id: int, question_id: int):
    """不是自己的、或者根本不存在 → 404，不给 403（方案七-1：说"它存在但不是你的"就是泄露）。"""
    row = QuestionRepo(conn, user_id).mine_one(question_id)
    if row is None:
        raise NotFoundError(prompts.NOT_FOUND)
    return row
