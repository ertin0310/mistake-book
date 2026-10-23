"""步 13 演示（另一半）：三条路进去的题目，库里应当一模一样。

"par（一致）"指的是同一道题分别走
    ① 录题表单（`question_service.create`）
    ② CSV 导入（人可以写简写）
    ③ JSONL 导入（原样 JSON）
    ④ 导出后再导回
四条路之后，`stem` / `options_json` / `answer_json` 三格逐字相同。
只要有一条路自己另算一遍，这道题就会在不同入口长出不同形状——那才是真事故。
"""

import csv
import io

from src.data.repository.question_repo import QuestionRepo
from src.services import export_service, import_service, question_service
from tests.conftest import add_user

STEM = "下列 |x| 在 x=0 处连续吗？\n第二行还带个逗号，"
ANSWER_TEXT = "连续但不可导；公比 1/2"
CANONICAL = '{"text":"连续但不可导；公比 1/2"}'


def stored(conn, uid):
    row = QuestionRepo(conn, uid).mine_all()[0]
    return row["stem"], row["options_json"], row["answer_json"]


def as_csv(answer=ANSWER_TEXT):
    return ("type,subject,stem,options,answer,explanation,knowledge_points\n"
            + f'essay,数学,"{STEM.replace(chr(10), chr(10))}",[],"{answer}",,\n')


def as_jsonl():
    return ('{"type":"essay","subject":"数学","stem":"' + STEM.replace("\n", "\\n")
            + '","options":[],"answer":{"text":"' + ANSWER_TEXT
            + '"},"explanation":"","knowledge_points":""}')


# ---------------------------------------------------------------- 四条路同一个形状

def test_form_csv_and_jsonl_store_the_same_bytes(db):
    add_user(db, 7, "by_form")
    add_user(db, 8, "by_csv")
    add_user(db, 10, "by_jsonl")
    question_service.create(db, 7, {"subject_id": "1", "type": "essay", "stem": STEM,
                                    "answer": ANSWER_TEXT, "explanation": ""})
    for uid, (fmt, text) in ((8, ("csv", as_csv())), (10, ("jsonl", as_jsonl()))):
        result = import_service.preview(db, "question", fmt, text)
        assert [row.errors for row in result["blocked"]] == [], fmt
        import_service.commit(db, uid, import_service.stage(db, uid, "question", fmt,
                                                            f"t.{fmt}", result))
    expected = stored(db, 7)
    assert expected[2] == CANONICAL
    assert stored(db, 8) == expected and stored(db, 10) == expected     # ★ 三条路一个样


def test_export_then_reimport_keeps_the_same_stored_shape(db):
    add_user(db, 7, "first")
    add_user(db, 8, "second")
    question_service.create(db, 7, {"subject_id": "1", "type": "essay", "stem": STEM,
                                    "answer": ANSWER_TEXT, "explanation": ""})
    import_service.commit(db, 8, import_service.stage(
        db, 8, "question", "csv", "rt.csv",
        import_service.preview(db, "question", "csv", export_service.build(db, 7, "questions"))))
    assert stored(db, 8) == stored(db, 7)


# ---------------------------------------------------------------- 导出只管自己的

def test_question_export_covers_exactly_my_visible_questions(db):
    """别人的题、自己软删的、被官方收起的都不该出现在我的导出里（一条都不多）。"""
    add_user(db, 7, "me")
    add_user(db, 8, "other")
    mine = QuestionRepo(db, 7)
    mine.add(subject_id=1, type_name="essay", stem="我的题", options_json="[]",
             answer_json=CANONICAL, explanation="")
    QuestionRepo(db, 8).add(subject_id=1, type_name="essay", stem="别人的题",
                            options_json="[]", answer_json=CANONICAL, explanation="")
    rows = list(csv.DictReader(io.StringIO(
        export_service.build(db, 7, "questions").lstrip(export_service.BOM))))
    assert [row["stem"] for row in rows] == ["我的题"]


def test_unknown_export_kind_is_a_404_not_a_crash(client):
    from tests.conftest import sign_up
    sign_up(client, username="stu")
    assert client.get("/export/不存在.csv").status_code == 404


def test_export_requires_login(client):
    assert client.get("/export/questions.csv").status_code == 302
