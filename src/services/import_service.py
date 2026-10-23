"""导入链路：预览 → 确认（方案三-14）。

★ 报错精确到**文件里的真实行号**并给原因，一句"格式错误"不得分（题目 S4）。
★ 错题引用了不存在的知识点 → **先解决缺失**：列清单 + 一颗「顺手一起建了」的勾，
  勾了就在同一个事务里先建知识点再建题（知识点本来就是"提交即入池、事后审"）。
★ 两种格式各走各的通道：CSV 给人（可带简写），JSONL 给机器与 AI（原样 JSON）。
"""

import json
import sqlite3

from config import csv_spec, prompts
from src.data.importers import registry, sanitize
from src.data.repository.import_session_repo import ImportSessionRepo
from src.data.repository.knowledge_repo import KnowledgeRepo
from src.data.repository.question_repo import QuestionRepo
from src.data.repository.subject_repo import SubjectRepo
from src.domain import normalize
from src.domain.errors import NotFoundError
from src.domain.question_types import registry as types_registry


# ---------------------------------------------------------------- 预览

def preview(conn, target: str, fmt: str, text: str) -> dict:
    spec = _spec(target)
    cleaned, fixes = _sanitize_for(fmt, text)
    rows = registry.get(fmt).parse(cleaned, spec["columns"])
    seen: dict[str, int] = {}
    for row in rows:
        validate_row(conn, target, row)
        _mark_duplicate(row, seen)
    return {"target": target, "format": fmt, "rows": rows,
            "ok": [row for row in rows if row.ok],
            "blocked": [row for row in rows if not row.ok],
            "missing": missing_points(conn, rows) if target == "question" else [],
            "fixes": fixes}


def _sanitize_for(fmt: str, text: str):
    """JSONL 与 AI 那条路先洗排版毛病；CSV 不动引号（引号在 CSV 里有语义）。"""
    if fmt == "csv":
        return text, 0
    text, fixes = sanitize.fix_common_issues(text)
    text, marks = sanitize.strip_code_fences(text)
    return text, fixes + marks


def _spec(target: str) -> dict:
    if target not in csv_spec.SPECS:
        raise ValueError(f"未知的导入目标：{target}")
    return csv_spec.SPECS[target]


# ---------------------------------------------------------------- 逐行校验

def validate_row(conn, target: str, row) -> None:
    if row.errors:
        return          # 解析阶段就坏了的行（列数不符、不是 JSON），不再叠加"必填为空"
    spec = _spec(target)
    data = {key: (row.data.get(key) or "").strip() for key in spec["columns"]}
    for column in spec["required"]:
        if not data.get(column):
            row.errors.append(f"列「{column}」{prompts.FIELD_REQUIRED}")
    for column, limit in spec["maxlen"].items():
        if len(data.get(column, "")) > limit:
            row.errors.append(f"{column} 超过 {limit} 字")
    if row.errors:
        return
    if target == "question":
        _validate_question_row(conn, data, row)
    else:
        row.payload = dict(data)


def _validate_question_row(conn, data: dict, row) -> None:
    if data["type"] not in types_registry.known():
        supported = "、".join(types_registry.known())
        row.errors.append(f"题型 {data['type']} 还不支持（现有：{supported}）")
    subject_id = _subject_id(conn, data["subject"])
    if subject_id is None:
        row.errors.append(prompts.SUBJECT_UNUSABLE)
    if row.errors:
        return
    handler = types_registry.get(data["type"])
    options_json, answer_json = handler.parse(
        {"options": data.get("options", ""), "answer": data["answer"]})
    # 校验拿的是**整行**（选择题要看 options），与录题表单同一个入参形状，
    # 免得"录题能过、导入不能过"这种两套规则漂移
    row.errors.extend(handler.validate(data))
    row.payload = dict(data, subject_id=subject_id, options_json=options_json,
                       answer_json=answer_json, points=_split_points(data.get("knowledge_points", "")))


def _subject_id(conn, name: str):
    """按名字找科目。借 `name_map()`（只装当前可用的）反着查，与下拉框同一个口径。"""
    return {value: key for key, value in SubjectRepo(conn).name_map().items()}.get(name)


def _split_points(raw: str) -> list:
    """CSV 一格里用分号隔开；JSONL 里人和 AI 都习惯直接给数组，两种都要认。

    ★ 只把分号当分隔符，逗号斜杠竖线都不算——`1/2` 这种答案不能被劈坏。
    """
    value = raw.strip()
    if value.startswith("["):
        try:
            return [str(piece).strip() for piece in json.loads(value) if str(piece).strip()]
        except ValueError:
            return [value] if value else []
    return [piece.strip() for piece in value.split(csv_spec.MULTI_VALUE_SEPARATOR) if piece.strip()]


def _mark_duplicate(row, seen: dict) -> None:
    key = json.dumps(row.data, ensure_ascii=False, sort_keys=True)
    if key in seen:
        row.errors.append(f"与第 {seen[key]} 行内容完全相同")
    else:
        seen[key] = row.line


# ---------------------------------------------------------------- 缺失知识点预检

def missing_points(conn, rows) -> list:
    """按"科目 + 归一化名"比对，只算 `is_visible()` 通过的行（三-14 ★）。"""
    known = KnowledgeRepo(conn, None).usable_names()
    missing, seen = [], set()
    for row in rows:
        subject_id = row.payload.get("subject_id")
        for name in row.payload.get("points", []):
            key = (subject_id, normalize.normalize_name(name))
            if key not in known and key not in seen:
                seen.add(key)
                missing.append({"subject_id": subject_id, "name": name})
    return missing


# ---------------------------------------------------------------- 确认入库

def stage(conn, user_id: int, target: str, fmt: str, filename: str, result: dict) -> int:
    """把一次预览落成草稿批次：中途走掉不丢，回来一键重跑。"""
    repo = ImportSessionRepo(conn, user_id)
    session_id = repo.start(target, fmt, filename)
    repo.add_rows(session_id, result["rows"])
    return session_id


def commit(conn, user_id: int, session_id: int, create_missing: bool = False) -> dict:
    """只写预览时通过的那些行；建知识点与建题在**同一个事务**里。

    ★ 批次号是别人的 = 不存在（七-1 的 404）。这个 id 从表单里来，是可以被人改的，
      不判就等于把\确认导入\按钮开给了全仓库。
    """
    repo = ImportSessionRepo(conn, user_id)
    if repo.get_session(session_id) is None:
        raise NotFoundError(prompts.NOT_FOUND)
    counts = {"questions": 0, "knowledge_points": 0, "subjects": 0}
    questions = QuestionRepo(conn, user_id)
    for stored in repo.rows_of(session_id):
        if stored["status"] != "ok":
            continue
        payload = json.loads(stored["payload_json"])
        if payload.get("type"):
            _import_question(conn, user_id, questions, payload, create_missing, counts)
            counts["questions"] += 1
        elif payload.get("subject"):
            _import_point(conn, user_id, payload, counts)
        elif payload.get("name"):
            _import_subject(conn, payload["name"], counts)
    repo.finish(session_id, "committed")
    return counts


def _import_question(conn, user_id, questions, payload, create_missing, counts) -> None:
    question_id = questions.add(subject_id=payload["subject_id"], type_name=payload["type"],
                               stem=payload["stem"], options_json=payload["options_json"],
                               answer_json=payload["answer_json"],
                               explanation=payload.get("explanation", ""))
    for name in payload.get("points", []):
        point_id = _point_id(conn, user_id, payload["subject_id"], name, create_missing, counts)
        if point_id:
            conn.execute(
                "INSERT OR IGNORE INTO question_knowledge_point"
                " (question_id, knowledge_point_id, user_id, created_at)"
                " VALUES (?, ?, ?, datetime('now','localtime'))",
                (question_id, point_id, user_id))


def _point_id(conn, user_id, subject_id, name, create_missing, counts):
    repo = KnowledgeRepo(conn, user_id)
    found = repo.find_usable(subject_id, name)
    if found is not None:
        return found
    if not create_missing:
        return None
    new_id = repo.submit(user_id, subject_id, name)
    counts["knowledge_points"] += 1
    return new_id


def _import_point(conn, user_id, payload, counts) -> None:
    subject_id = _subject_id(conn, payload["subject"])
    if subject_id is None:
        return
    KnowledgeRepo(conn, user_id).submit(user_id, subject_id, payload["name"])
    counts["knowledge_points"] += 1


def _import_subject(conn, name, counts) -> None:
    """科目导入是管理员那条链（`/admin/import`）才会用到，撞名直接跳过不报错。"""
    try:
        conn.execute("INSERT INTO subject (name, status, created_at, updated_at)"
                     " VALUES (?, 'active', datetime('now','localtime'),"
                     " datetime('now','localtime'))", (name,))
        counts["subjects"] += 1
    except sqlite3.IntegrityError:
        pass
