"""导出（方案三-13、三-19）：题目清单与复习流水导成 CSV。

★ 和导入**共用同一套序列化**：`options` / `answer` 两列写出去的就是库里那份标准
  JSON 文本，所以"导出 → 原样再导回"能逐字节一致（round-trip）。
★ 文件以 UTF-8 BOM 开头：Excel 双击开 UTF-8 的 CSV 会当本地编码读，中文全成乱码，
  这是它二十年没改的毛病，不该让用户为它去学导入向导。
"""

import csv
import io

from config import csv_spec
from src.data.repository.knowledge_repo import KnowledgeRepo
from src.data.repository.mistake_repo import MistakeRepo
from src.data.repository.question_repo import QuestionRepo
from src.data.repository.study_attempt_repo import ReviewLogRepo
from src.data.repository.subject_repo import SubjectRepo

BOM = "\ufeff"          # \u5199\u6210\u8f6c\u4e49\u800c\u4e0d\u662f\u5b57\u9762\u91cf\uff1a\u8089\u773c\u770b\u4e0d\u51fa\u6765\uff0c\u6539\u4ee3\u7801\u7684\u4eba\u5bb9\u6613\u4e00\u5934\u96fe\u6c34
KINDS = ("questions", "review_log")


def build(conn, user_id: int, kind: str) -> str:
    if kind == "questions":
        return _write(csv_spec.SPECS["question"]["columns"], _question_rows(conn, user_id))
    if kind == "review_log":
        return _write(csv_spec.REVIEW_COLUMNS, _review_rows(conn, user_id))
    raise ValueError(f"没有这种导出：{kind}")


def _write(columns, rows) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(column, "") for column in columns])
    return BOM + buffer.getvalue()


# ---------------------------------------------------------------- 题目清单

def _question_rows(conn, user_id: int) -> list:
    """列名与导入规格同源，所以这一份可以直接当导入文件用。

    ★ 库里的列叫 `options_json` / `answer_json`，规格里的列叫 `options` / `answer`，
      这一层就是那唯一的翻译处——写出去的值仍是库里那份标准 JSON，一字不改。
    """
    subjects = SubjectRepo(conn).name_map()
    knowledge = KnowledgeRepo(conn, user_id)
    rows = []
    for question in QuestionRepo(conn, user_id).mine_all():
        rows.append({"type": question["type"], "subject": subjects.get(question["subject_id"], ""),
                     "stem": question["stem"], "options": question["options_json"],
                     "answer": question["answer_json"], "explanation": question["explanation"],
                     "knowledge_points": csv_spec.MULTI_VALUE_SEPARATOR.join(
                         knowledge.names_by_question(question["id"]))})
    return rows


# ---------------------------------------------------------------- 复习流水

def _review_rows(conn, user_id: int) -> list:
    """`review_log` 只追加、永不改，所以这份导出就是它的原样历史。

    题干单独查出来拼进去（流水账上只有 `mistake_id`，评审和人一样看不懂那是什么）。
    """
    questions = QuestionRepo(conn, user_id)
    mistakes = {row["id"]: row["question_id"] for row in MistakeRepo(conn, user_id).rows()}
    stems: dict = {}
    rows = []
    for log in ReviewLogRepo(conn, user_id).rows(order="id"):
        question_id = mistakes.get(log["mistake_id"])
        if question_id not in stems:
            question = questions.any_visible(question_id) if question_id else None
            stems[question_id] = question["stem"] if question else ""
        rows.append(dict(log, stem=stems[question_id]))
    return rows
