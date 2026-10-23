"""步 12 演示：100 行含 3 行脏数据，报错报到行号；缺失知识点能"顺手一起建了"。"""

import pytest

from config import csv_spec, prompts, settings
from src.data.importers import registry, sanitize
from src.data.repository.import_session_repo import ImportSessionRepo
from src.data.repository.question_repo import QuestionRepo
from src.services import import_service
from tests.conftest import add_subject

COLUMNS = "type,subject,stem,options,answer,explanation,knowledge_points"


def csv_text(rows) -> str:
    return COLUMNS + "\n" + "\n".join(rows)


def good_row(n: int) -> str:
    answer = '{"text":"答案 %d"}' % n
    return ",".join(["essay", "数学", f"题干 {n}", "[]", answer, "", "牛顿定律"])


# ---------------------------------------------------------------- 行号

def test_hundred_rows_with_three_dirty_ones_report_line_numbers(db):
    rows = [good_row(n) for n in range(1, 101)]
    rows[6] = "essay,数学,,[],{\"text\":\"答案\"},,"                  # 第 8 行：题干空
    rows[41] = "essay,数学,只有两列"                                   # 第 43 行：列数不符
    rows[87] = "choice,数学,题干,[],{\"letters\":\"A\"},,摩擦力做功"    # 第 89 行：题型未实现
    result = import_service.preview(db, "question", "csv", csv_text(rows))

    assert len(result["rows"]) == 100
    assert [row.line for row in result["blocked"]] == [8, 43, 89]
    assert prompts.FIELD_REQUIRED in result["blocked"][0].errors
    assert "列" in result["blocked"][1].errors[0]
    assert "还不支持" in result["blocked"][2].errors[0]
    assert len(result["ok"]) == 97


def test_duplicate_row_points_at_the_first_one(db):
    text = csv_text([good_row(1), good_row(2), good_row(1)])
    blocked = import_service.preview(db, "question", "csv", text)["blocked"]
    assert blocked[0].line == 4 and "第 2 行" in blocked[0].errors[0]


def test_missing_subject_is_reported(db):
    text = csv_text(["essay,体育,题干,[],{\"text\":\"答案\"},,"])
    blocked = import_service.preview(db, "question", "csv", text)["blocked"]
    assert blocked[0].errors == [prompts.SUBJECT_UNUSABLE]


# ---------------------------------------------------------------- 两种格式各走各的通道

def test_csv_multiline_cell_stays_one_row(db):
    """CSV 引号里的换行不劈行；essay 的答案整段收进标准 JSON。"""
    text = COLUMNS + "\n" + 'essay,数学,填三个空,[],"光滑|无摩擦\n水",,摩擦力做功'
    ok = import_service.preview(db, "question", "csv", text)["ok"]
    assert len(ok) == 1 and ok[0].line == 2
    assert "光滑|无摩擦" in ok[0].payload["answer_json"]      # 竖线在简答里是普通文字


@pytest.mark.parametrize("kind", ["blank", "choice"])
def test_unimplemented_types_are_rejected_line_by_line(db, kind):
    """填空与选择要到步 21，导入这儿先明确报"还不支持"，不悄悄收下。"""
    text = COLUMNS + "\n" + f'{kind},数学,题干,[],{{"text":"答案"}},,牛顿定律'
    blocked = import_service.preview(db, "question", "csv", text)["blocked"]
    assert blocked[0].line == 2 and "还不支持" in blocked[0].errors[0]


def test_jsonl_keeps_the_answer_verbatim(db):
    """JSONL 是给机器与 AI 用的：原样收下，不做简写转换。"""
    line = ('{"type":"essay","subject":"数学","stem":"填两空",'
            '"options":[],"answer":"光滑|无摩擦 1/2","explanation":"",'
            '"knowledge_points":"摩擦力做功"}')
    ok = import_service.preview(db, "question", "jsonl", line)["ok"]
    assert ok[0].payload["answer_json"] == '{"text":"光滑|无摩擦 1/2"}'
    assert "1/2" in ok[0].payload["answer_json"]          # ★ 斜杠没被当分隔符劈开


def test_empty_file_and_bad_json_are_reported_not_raised(db):
    assert import_service.preview(db, "question", "csv", "")["blocked"][0].errors == ["这个文件是空的。"]
    blocked = import_service.preview(db, "question", "jsonl", "这行不是 JSON")["blocked"]
    assert "合法 JSON" in blocked[0].errors[0]


# ---------------------------------------------------------------- 清洗

def test_decode_sniffs_gbk_and_strips_bom():
    text, encoding = sanitize.decode("题干,答案\n牛顿,牛一\n".encode("gbk"))
    assert encoding == "gb18030" and "牛顿" in text
    text, _ = sanitize.decode("﻿type,stem\nessay,a\n".encode("utf-8"))
    assert text.startswith("type")


def test_common_ai_issues_are_fixed_and_counted():
    dirty = "```json\n{\"a\":“b”}\n```"
    cleaned, fixes = import_service._sanitize_for("jsonl", dirty)
    assert "```" not in cleaned and "“" not in cleaned and fixes >= 3


# ---------------------------------------------------------------- 缺失知识点

def test_missing_points_are_listed_then_created_in_one_go(db):
    text = csv_text([
        "essay,数学,题一,[],{\"text\":\"答\"},,牛顿定律;全新知识点甲",
        "essay,数学,题二,[],{\"text\":\"答\"},,全新知识点乙"])
    result = import_service.preview(db, "question", "csv", text)
    missing = {(item["subject_id"], item["name"]) for item in result["missing"]}
    assert "牛顿定律" not in [n for _, n in missing]                 # 已存在的不算缺失
    assert {n for _, n in missing} == {"全新知识点甲", "全新知识点乙"}

    session_id = import_service.stage(db, 1, "question", "csv", "题.csv", result)
    counts = import_service.commit(db, 1, session_id, create_missing=True)
    assert counts["questions"] == 2 and counts["knowledge_points"] == 2
    linked = db.execute("SELECT COUNT(*) FROM question_knowledge_point WHERE user_id=1").fetchone()[0]
    assert linked == 3     # 题一两条关联（已有的牛顿定律 + 新建甲）+ 题二一条（新建乙）


def test_without_the_checkbox_questions_still_import(db):
    text = csv_text(["essay,数学,题三,[],{\"text\":\"答\"},,又一个新知识点"])
    result = import_service.preview(db, "question", "csv", text)
    session_id = import_service.stage(db, 1, "question", "csv", "t.csv", result)
    counts = import_service.commit(db, 1, session_id, create_missing=False)
    assert counts["questions"] == 1 and counts["knowledge_points"] == 0
    assert len(QuestionRepo(db, 1).mine().items) >= 1


def test_blocked_rows_are_never_written(db):
    text = csv_text([good_row(1), "essay,数学,,[],{\"text\":\"空题干\"},,"])
    result = import_service.preview(db, "question", "csv", text)
    session_id = import_service.stage(db, 1, "question", "csv", "t.csv", result)
    before = len(QuestionRepo(db, 1).mine().items)
    import_service.commit(db, 1, session_id)
    assert len(QuestionRepo(db, 1).mine().items) == before + 1


def test_session_is_marked_committed(db):
    text = csv_text([good_row(1)])
    result = import_service.preview(db, "question", "csv", text)
    session_id = import_service.stage(db, 1, "question", "csv", "t.csv", result)
    assert ImportSessionRepo(db, 1).pending_for("question")          # 先挂着，回来能接着确认
    import_service.commit(db, 1, session_id)
    assert ImportSessionRepo(db, 1).pending_for("question") == []


# ---------------------------------------------------------------- 仓库里那份样例

def test_shipped_samples_import_cleanly(mem_db):
    """`import-templates/` 里那两份样例当场就能导——评审照 README 试的就是它们。

    ★ 这条用例是"样例与规格同步"的保险：以后加列、改分隔符，样例忘了跟着改，
      这里立刻红，而不是等评审上传一份被拦下一半。
    """
    # 样例里用到的科目得和真实 seed 一样都活着，所以这条用例不借用 `db` 那份两科目的夹具
    for name in ("数学", "英语", "政治", "专业课"):
        add_subject(mem_db, len(mem_db.execute("SELECT 1 FROM subject").fetchall()) + 1, name)
    for path, fmt in ((settings.SAMPLE_CSV_PATH, "csv"), (settings.SAMPLE_JSONL_PATH, "jsonl")):
        text, _encoding = sanitize.decode(path.read_bytes())
        result = import_service.preview(mem_db, "question", fmt, text)
        assert [row.errors for row in result["blocked"]] == [], path.name
        assert len(result["ok"]) == 4, path.name


def test_shipped_dirty_sample_reports_every_line_number(db):
    """故意做错的那份样例：拦下的行号必须和文件里数出来的一字不差。"""
    text, _encoding = sanitize.decode(settings.SAMPLE_DIRTY_CSV_PATH.read_bytes())
    blocked = import_service.preview(db, "question", "csv", text)["blocked"]
    assert [row.line for row in blocked] == [5, 6, 7]
    assert "必填项不能空着" in blocked[0].errors[0]
    assert "还不支持" in blocked[1].errors[0]
    assert prompts.SUBJECT_UNUSABLE in blocked[2].errors


def test_jsonl_knowledge_points_may_be_a_real_array(db):
    """AI 与脚本习惯直接给数组，不该被当成一长串名字塞进同一个知识点。"""
    line = ('{"type":"essay","subject":"数学","stem":"数组写法","options":[],'
            '"answer":{"text":"答"},"explanation":"",'
            '"knowledge_points":["牛顿第二定律","受力分析"]}')
    ok = import_service.preview(db, "question", "jsonl", line)["ok"]
    assert ok[0].payload["points"] == ["牛顿第二定律", "受力分析"]
