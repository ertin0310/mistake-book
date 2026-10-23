"""步 13 演示：导出再原样导回，逐字节一致（round-trip）。

这条用例值"数据持久化 + 校验"那一半：只有导出与导入**共用同一套序列化**，
两边才可能咬得上。所以这里比的不是"内容差不多"，是一个字节都不差。
"""

import csv
import io

from config import csv_spec
from src.data.repository.knowledge_repo import KnowledgeRepo
from src.data.repository.question_repo import QuestionRepo
from src.services import export_service, import_service
from tests.conftest import add_user

# 题干：竖线 + 换行 + 中文逗号；答案：`1/2` 与成对引号；解析：三个竖线连着写
NASTY = (
    {"stem": "下列 |x| 在 x=0 处连续吗？\n第二行还带个逗号，",
     "answer": '{"text":"连续但不可导；公比 1/2，他说\\"对\\""}',
     "explanation": "竖线 ||| 与分号 ; 都不许被当成分隔符劈坏。",
     "points": ["牛顿第二定律"]},
    {"stem": "把下面这段默写完整。", "answer": '{"text":"第一行\\n第二行\\n第三行"}',
     "explanation": "", "points": []},
    {"stem": "牛顿第二定律的表达式？", "answer": '{"text":"F=ma"}',
     "explanation": "合力等于质量乘以加速度。", "points": ["牛顿第二定律"]},
)
# ★ `options` 这一列现在恒为 `[]`（只登记了简答题一个题型）。步 21 上选择题之后再
#   补"选项文字带引号与逗号"的用例——那时才真写得出非空选项。


def seed_questions(conn, uid):
    questions = QuestionRepo(conn, uid)
    knowledge = KnowledgeRepo(conn, uid)
    for row in NASTY:
        question_id = questions.add(subject_id=1, type_name="essay", stem=row["stem"],
                                    options_json="[]", answer_json=row["answer"],
                                    explanation=row["explanation"])
        for name in row["points"]:
            point_id = knowledge.find_usable(1, name) or knowledge.submit(uid, 1, name)
            conn.execute("INSERT OR IGNORE INTO question_knowledge_point"
                         " (question_id, knowledge_point_id, user_id, created_at)"
                         " VALUES (?, ?, ?, '2026-10-21 10:00:00')",
                         (question_id, point_id, uid))
    conn.commit()


def export(conn, uid):
    return export_service.build(conn, uid, "questions")


def rows_of(text):
    return list(csv.DictReader(io.StringIO(text.lstrip(export_service.BOM))))


# ---------------------------------------------------------------- BOM 与表头

def test_export_starts_with_bom_so_excel_opens_it(db):
    """UTF-8 无 BOM 时 Excel 双击会按本地编码猜，中文全成乱码——它二十年没改的毛病。"""
    add_user(db, 7, "stu13")
    seed_questions(db, 7)
    text = export(db, 7)
    assert text.startswith(export_service.BOM)
    assert export_service.BOM not in text[1:]          # 只在文件头出现一次


def test_export_header_equals_the_import_spec(db):
    add_user(db, 7, "stu13")
    seed_questions(db, 7)
    assert list(rows_of(export(db, 7))[0]) == list(csv_spec.SPECS["question"]["columns"])


# ---------------------------------------------------------------- 逐字节一致

def test_export_then_import_is_byte_identical(db):
    """A 导出 → 原样导给 B → B 再导出，两份文件必须一模一样。"""
    add_user(db, 7, "alice")
    add_user(db, 8, "bob")
    seed_questions(db, 7)
    first = export(db, 7)

    result = import_service.preview(db, "question", "csv", first)
    assert [row.errors for row in result["blocked"]] == []
    import_service.commit(db, 8, import_service.stage(
        db, 8, "question", "csv", "roundtrip.csv", result))

    assert export(db, 8) == first                      # ★ 一个字节都不差
    assert len(result["ok"]) == len(NASTY)


def test_nasty_cells_survive_the_round_trip_field_by_field(db):
    """整份比对之外再逐格比一次：题干里的换行、答案里的 1/2 与引号都要原封不动。"""
    add_user(db, 7, "alice")
    add_user(db, 8, "bob")
    seed_questions(db, 7)
    cells = {row["stem"]: row for row in rows_of(export(db, 7))}
    assert set(cells) == {row["stem"] for row in NASTY}     # 换行与逗号没把一行劈成两行
    for expected in NASTY:
        stored = cells[expected["stem"]]
        assert stored["answer"] == expected["answer"]
        assert stored["explanation"] == expected["explanation"]
        assert stored["subject"] == "数学"
    assert cells[NASTY[0]["stem"]]["knowledge_points"] == "牛顿第二定律"

    result = import_service.preview(db, "question", "csv", export(db, 7))
    import_service.commit(db, 8, import_service.stage(
        db, 8, "question", "csv", "t.csv", result))
    linked = db.execute("SELECT COUNT(*) AS n FROM question_knowledge_point WHERE user_id=8"
                        ).fetchone()["n"]
    assert linked == 2                                      # 两处挂了「牛顿第二定律」


def test_two_exports_of_the_same_data_are_identical(db):
    """导出必须是确定的：同一份数据导两次逐字节一致，不带时间戳也不带随机序。"""
    add_user(db, 7, "alice")
    seed_questions(db, 7)
    assert export(db, 7) == export(db, 7)
