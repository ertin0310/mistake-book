"""步 13 演示（页面层）：页面上那两个链接真的能下载，中文文件名不乱。

下载这件事全靠响应头，写错一个字浏览器就当网页打开、或者文件名变成一串问号，
所以这里连 `Content-Disposition` 一起验。
"""

import re

from config import prompts
from src.data.repository.mistake_repo import MistakeRepo
from src.data.repository.question_repo import QuestionRepo
from src.services import export_service, question_service, review_service
from tests.conftest import add_user, sign_up, uid_of

CSV_HEADERS = ("Content-Type", "Content-Disposition")


def one_question(db, uid):
    return question_service.create(db, uid, {
        "subject_id": "1", "type": "essay", "stem": "导出页测的题",
        "answer": "答案里有 1/2 与 |x|", "explanation": "解析 ||| 不该被劈"})


# ---------------------------------------------------------------- 链接真的在页面上

def test_study_page_offers_the_question_export(client, db):
    sign_up(client, username="stu")
    body = client.get("/study/").get_data(as_text=True)
    assert "/export/questions.csv" in body
    assert prompts.EXPORT_BUTTON in body


def test_review_page_offers_the_log_export(client, db):
    sign_up(client, username="stu")
    assert "/export/review_log.csv" in client.get("/review/today").get_data(as_text=True)


def test_shared_pool_page_does_not_offer_export(client, db):
    """共享池那一屏看的是别人的题，导出自己那一份的按钮不该出现在这儿。"""
    sign_up(client, username="stu")
    assert "/export/questions.csv" not in client.get("/study/drill").get_data(as_text=True)


# ---------------------------------------------------------------- 下载下来的内容

def test_download_headers_are_excel_and_browser_friendly(client, db):
    sign_up(client, username="stu")
    uid = uid_of(db, "stu")
    one_question(db, uid)
    response = client.get("/export/questions.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["Content-Type"]
    disposition = response.headers["Content-Disposition"]
    assert "attachment" in disposition
    assert "filename=\"questions.csv\"" in disposition              # 老浏览器的 ASCII 兜底名
    assert "filename*=UTF-8''" in disposition                       # 中文名走 RFC 5987 转义
    text = response.get_data(as_text=True)
    assert text.startswith(export_service.BOM)
    assert "导出页测的题" in text and "1/2" in text and "|||" in text


def test_review_log_export_lists_every_rating_with_the_stem(client, db):
    sign_up(client, username="stu")
    uid = uid_of(db, "stu")
    question_id = one_question(db, uid)
    review_service.record_attempt(db, uid, question_id, subject_id=1, result="wrong",
                                  submitted="")
    mistake = MistakeRepo(db, uid).active_for(question_id)
    review_service.rate(db, uid, mistake["id"], rating=2, duration_seconds=42)

    body = client.get("/export/review_log.csv").get_data(as_text=True)
    lines = body.lstrip(export_service.BOM).strip().split("\n")
    assert len(lines) == 2                                   # 表头 + 那一笔流水
    assert "导出页测的题" in lines[1] and "42" in lines[1]
    assert "mistake_id" not in lines[0]                       # 人看的表头用名字，不摆内部 id
    assert lines[0].startswith("reviewed_on,reviewed_at,stem")


def test_export_never_lists_another_users_questions(client, db):
    """两个账号各导各的：B 的文件里不该有 A 的题干（越权在数据层就拦住了）。"""
    sign_up(client, username="alice")
    add_user(db, 42, "bob", role="member")
    QuestionRepo(db, 42).add(subject_id=1, type_name="essay", stem="鲍勃的私有题",
                             options_json="[]", answer_json='{"text":"答"}', explanation="")
    body = client.get("/export/questions.csv").get_data(as_text=True)
    assert "鲍勃的私有题" not in body


def test_export_page_does_not_dump_the_whole_library(client, db):
    """seed 之外新注册的账号导出应该是空表头——不是"库里有点东西就全给你"。"""
    sign_up(client, username="clean")
    body = client.get("/export/questions.csv").get_data(as_text=True)
    assert len(body.lstrip(export_service.BOM).strip().split("\n")) == 1
    assert re.match(r"^\ufefftype,subject,stem,", body)
