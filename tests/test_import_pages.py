"""步 12 演示（页面层）：上传 → 预览报到行号 → 确认入库，全程走真路由。

和 `test_import_validation.py` 的分工：那边验"校验算得对不对"，
这边验"用户点得通"——防冒名签、multipart 上传、确认按钮真的写库、跳回列表页。
"""

import io
import re

from src.data.repository.knowledge_repo import KnowledgeRepo
from src.data.repository.question_repo import QuestionRepo
from tests.conftest import csrf_token, sign_up, uid_of

COLUMNS = "type,subject,stem,options,answer,explanation,knowledge_points"


def upload(client, text, *, target="question", fmt="csv", filename="错题.csv"):
    response = client.post("/import/", data={
        "target": target, "format": fmt,
        "file": (io.BytesIO(text.encode("utf-8")), filename),
        "csrf_token": csrf_token(client, "/import/")},
        content_type="multipart/form-data")
    return response.get_data(as_text=True)


def confirm(client, body, *, create_missing=False):
    """把预览页那张隐藏批次号原样交回去——用户眼里只是点了一个按钮。"""
    session_id = re.search(r'name="session_id" value="(\d+)"', body)
    assert session_id, "预览页没带批次号，确认按钮点了也没用"
    data = {"session_id": session_id.group(1), "csrf_token": csrf_token(client, "/import/")}
    if create_missing:
        data["create_missing"] = "1"
    return client.post("/import/confirm", data=data)


def essay_row(n, points="牛顿定律"):
    return ",".join(["essay", "数学", f"题干 {n}", "[]", f'{{"text":"答案 {n}"}}', "", points])


def plain(html_body):
    """把标签去掉，只留用户真正看到的字——断言写在"看到的句子"上，不跟着标签结构改。"""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_body))


def csv_text(rows):
    return COLUMNS + "\n" + "\n".join(rows)


def count_questions(db, uid):
    return db.execute("SELECT COUNT(*) AS n FROM question_bank WHERE user_id=?",
                      (uid,)).fetchone()["n"]


# ---------------------------------------------------------------- 进得去、拦得住

def test_import_page_requires_login(client):
    assert client.get("/import/").status_code == 302


def test_sidebar_opens_the_page(client):
    sign_up(client, username="stu")
    body = client.get("/import/").get_data(as_text=True)
    assert "批量导入" in body and "上传并预览" in body and "/import/" in body


def test_no_file_is_reported_not_crashed(client):
    sign_up(client, username="stu")
    response = client.post("/import/", data={"target": "question", "format": "csv",
                                             "csrf_token": csrf_token(client, "/import/")})
    assert "请先选择一个文件" in response.get_data(as_text=True)


def test_post_without_token_is_refused(client):
    sign_up(client, username="stu")
    assert client.post("/import/", data={"target": "question", "format": "csv"}).status_code == 400


# ---------------------------------------------------------------- 预览：报错到行号

def test_preview_counts_and_points_at_the_line(client):
    sign_up(client, username="stu")
    body = upload(client, csv_text([essay_row(1), essay_row(2),
                                    'essay,数学,,[],{"text":"答案"},,']))
    assert "共 3 行" in plain(body) and "可以通过 2 行" in plain(body)
    assert "被拦下 1 行" in plain(body) and "必填项不能空着" in plain(body)
    assert '<td class="n">4</td>' in body        # 表头占第 1 行，所以坏题在第 4 行


def test_confirm_writes_only_the_good_rows(client, db):
    sign_up(client, username="stu")
    body = upload(client, csv_text([essay_row(1), essay_row(2), "essay,数学,只有两列"]))
    assert confirm(client, body).status_code == 302
    assert count_questions(db, uid_of(db, "stu")) == 2
    list_body = client.get("/study/").get_data(as_text=True)
    assert "题干 1" in list_body and "题干 2" in list_body


# ---------------------------------------------------------------- 缺失知识点

def test_missing_point_is_listed_then_created_with_the_checkbox(client, db):
    sign_up(client, username="stu")
    uid = uid_of(db, "stu")
    body = upload(client, csv_text([essay_row(1, points="冲量定理")]))
    assert "冲量定理" in body and "系统中尚无" in body
    assert 'name="create_missing"' in body      # 勾确实摆在页面上
    confirm(client, body, create_missing=True)
    assert KnowledgeRepo(db, uid).find_usable(1, "冲量定理") is not None
    assert count_questions(db, uid) == 1


def test_without_the_checkbox_the_question_still_lands(client, db):
    sign_up(client, username="stu")
    uid = uid_of(db, "stu")
    confirm(client, upload(client, csv_text([essay_row(1, points="冲量定理")])))
    assert count_questions(db, uid) == 1
    assert KnowledgeRepo(db, uid).find_usable(1, "冲量定理") is None


# ---------------------------------------------------------------- 两种格式、多类目标

def test_jsonl_goes_through_the_same_page(client, db):
    sign_up(client, username="stu")
    line = ('{"type":"essay","subject":"数学","stem":"JSONL 直接进的题","options":[],'
            '"answer":{"text":"原样保存 1/2"},"explanation":"","knowledge_points":"牛顿定律"}')
    body = upload(client, line, fmt="jsonl")
    assert "可以通过 1 行" in plain(body)
    confirm(client, body)
    stored = QuestionRepo(db, uid_of(db, "stu")).mine_one(
        db.execute("SELECT MAX(id) AS i FROM question_bank").fetchone()["i"])
    assert "1/2" in stored["answer_json"]


def test_knowledge_point_target_imports_names(client, db):
    sign_up(client, username="stu")
    body = upload(client, "subject,name\n数学,泰勒公式\n数学,", target="knowledge_point")
    assert "被拦下 1 行" in plain(body)
    confirm(client, body)
    assert KnowledgeRepo(db, uid_of(db, "stu")).find_usable(1, "泰勒公式") is not None


def test_the_page_carries_the_column_docs_and_examples(client):
    """★ 用户看不见仓库，所以列说明、示例、AI 提示词必须摆在页面上。"""
    sign_up(client, username="stu")
    body = client.get("/import/").get_data(as_text=True)
    assert "每一列写什么" in body and "<code>knowledge_points</code>" in body
    assert "type,subject,stem,options,answer,explanation,knowledge_points" in body   # 可复制表头
    assert "让 AI 帮你把图片变成题目" in body and "粘贴文本" in body
    assert "图片类题目暂不支持批量导入" in body


def test_template_download_is_gated(client):
    assert client.get("/import/template/csv").status_code == 302      # 没登录不给下
    sign_up(client, username="stu")
    response = client.get("/import/template/csv")
    assert response.status_code == 200
    assert "attachment" in response.headers["Content-Disposition"]
    assert client.get("/import/template/不存在").status_code == 404


def test_pasted_text_goes_through_the_same_validation(client):
    """粘贴通道与上传文件同等待遇：坏行照样报行号，好行才进得了库。"""
    sign_up(client, username="stu")
    good = ('{"type":"essay","subject":"数学","stem":"粘贴进来的题","options":[],'
            '"answer":{"text":"答"},"explanation":"","knowledge_points":""}')
    body = client.post("/import/paste", data={"text": good + chr(10) + "这行不是 JSON",
                                              "csrf_token": csrf_token(client, "/import/")}
                       ).get_data(as_text=True)
    assert "可以通过 1 行" in plain(body) and "被拦下 1 行" in plain(body)
    assert "不是合法 JSON" in body
    assert client.post("/import/paste", data={"text": "",
                                              "csrf_token": csrf_token(client, "/import/")}
                       ).status_code == 200


def test_undecodable_bytes_get_a_chinese_hint(client):
    sign_up(client, username="stu")
    response = client.post("/import/", data={
        "target": "question", "format": "csv",
        "file": (io.BytesIO(b"\xff\xff\xff\xff"), "坏文件.csv"),
        "csrf_token": csrf_token(client, "/import/")},
        content_type="multipart/form-data")
    assert "编码认不出来" in response.get_data(as_text=True)
