"""步 14 演示（其一）：越权一律 404，别人的东西连"它存在"都不告诉你（方案七-1）。

这一份是把页面层能碰到的越权口子一次堵完：改 id、串链接、别人给的链接过期了，
得到的都是同一句中文提示，而不是半页别人的数据、也不是一个 500 白屏。
"""

import io

from src.data.repository.import_session_repo import ImportSessionRepo
from src.data.repository.mistake_repo import MistakeRepo
from src.data.repository.question_repo import QuestionRepo
from src.data.repository.study_attempt_repo import ReviewLogRepo, StudyAttemptRepo
from src.services import import_service
from tests.conftest import (add_mistake, add_review_log, add_user, csrf_token,
                          sign_up)

OTHER = 42                       # 另一个人：只在库里出现，从不登录


def other_question(db):
    return QuestionRepo(db, OTHER).add(subject_id=1, type_name="essay", stem="鲍勃的私有题",
                                       options_json="[]", answer_json='{"text":"他的答案"}',
                                       explanation="")


# ---------------------------------------------------------------- 题目：改、删、看

def test_cannot_open_edit_page_of_another_question(client, db):
    add_user(db, OTHER, "bob")
    qid = other_question(db)
    sign_up(client, username="alice")
    assert client.get(f"/study/edit/{qid}").status_code == 404


def test_cannot_delete_another_question_and_nothing_is_written(client, db):
    """最阴的一种：路由改了 0 行却照样 flash"删好了"。这里连数据一起验。"""
    add_user(db, OTHER, "bob")
    qid = other_question(db)
    sign_up(client, username="alice")
    response = client.post(f"/study/delete/{qid}", data={"csrf_token": csrf_token(client, "/study/")})
    assert response.status_code == 404
    assert db.execute("SELECT deleted_at FROM question_bank WHERE id=?", (qid,)).fetchone()[0] is None


def test_cannot_edit_another_question_through_the_form(client, db):
    add_user(db, OTHER, "bob")
    qid = other_question(db)
    sign_up(client, username="alice")
    response = client.post(f"/study/edit/{qid}", data={
        "subject_id": "1", "type": "essay", "stem": "被我改掉了", "answer": "随便",
        "explanation": "", "csrf_token": csrf_token(client, "/study/")})
    assert response.status_code == 404
    assert db.execute("SELECT stem FROM question_bank WHERE id=?", (qid,)).fetchone()[0] == "鲍勃的私有题"


# ---------------------------------------------------------------- 复习：卡片、回收站

def test_cannot_open_another_users_review_card(client, db):
    add_user(db, OTHER, "bob")
    mistake_id = add_mistake(db, OTHER, other_question(db))
    sign_up(client, username="alice")
    assert client.get(f"/review/card/{mistake_id}").status_code == 404


def test_cannot_rate_another_users_mistake(client, db):
    add_user(db, OTHER, "bob")
    mistake_id = add_mistake(db, OTHER, other_question(db))
    sign_up(client, username="alice")
    response = client.post(f"/review/card/{mistake_id}/rate", data={
        "rating": "1", "started": "0", "csrf_token": csrf_token(client, "/review/today")})
    assert response.status_code == 404
    assert db.execute("SELECT COUNT(*) AS n FROM review_log").fetchone()["n"] == 0


def test_cannot_restore_from_another_users_trash(client, db):
    add_user(db, OTHER, "bob")
    qid = other_question(db)
    db.execute("UPDATE question_bank SET deleted_at='2026-10-20 10:00:00', deleted_by=?"
               " WHERE id=?", (OTHER, qid))
    db.commit()
    sign_up(client, username="alice")
    response = client.post("/review/trash/restore", data={
        "entity": "question", "row_id": str(qid), "csrf_token": csrf_token(client, "/review/trash")})
    assert response.status_code == 404
    assert db.execute("SELECT deleted_at FROM question_bank WHERE id=?", (qid,)).fetchone()[0] is not None


# ---------------------------------------------------------------- 导入批次号

def test_cannot_confirm_another_users_import_session(client, db):
    """批次号是表单字段，想改就改。不判归属 = 把"确认导入"按钮开给全仓库。"""
    sign_up(client, username="alice")
    add_user(db, OTHER, "bob")
    text = ("type,subject,stem,options,answer,explanation,knowledge_points\n"
            'essay,数学,鲍勃的批次,[],{"text":"答"},,\n')
    result = import_service.preview(db, "question", "csv", text)
    bob_session = import_service.stage(db, OTHER, "question", "csv", "bob.csv", result)

    alice_body = client.post("/import/", data={
        "target": "question", "format": "csv",
        "file": (io.BytesIO(text.encode("utf-8")), "alice.csv"),
        "csrf_token": csrf_token(client, "/import/")},
        content_type="multipart/form-data").get_data(as_text=True)
    mine = int(alice_body.split('name="session_id" value="')[1].split('"')[0])

    response = client.post("/import/confirm", data={
        "session_id": str(bob_session), "csrf_token": csrf_token(client, "/import/")})
    assert response.status_code == 404
    assert ImportSessionRepo(db, OTHER).get_session(bob_session)["status"] == "pending"
    assert client.post("/import/confirm", data={
        "session_id": str(mine), "csrf_token": csrf_token(client, "/import/")}
    ).status_code == 302


# ---------------------------------------------------------------- 私有数据根本不出现

def test_private_counters_do_not_see_others(db):
    add_user(db, OTHER, "bob")
    add_user(db, 43, "alice2")
    qid = other_question(db)
    mistake_id = add_mistake(db, OTHER, qid)
    StudyAttemptRepo(db, OTHER).record(qid, subject_id=1, result="wrong", submitted="他的作答")
    add_review_log(db, OTHER, mistake_id)
    for repo, label in ((MistakeRepo, "mistake"), (StudyAttemptRepo, "study_attempt"),
                        (ReviewLogRepo, "review_log")):
        assert repo(db, 43).rows() == [], label          # 换个人来读，一行都没有
        assert repo(db, OTHER).rows() != [], label       # 主人自己读得到，证明不是空库假绿


def test_export_never_lists_another_question(client, db):
    add_user(db, OTHER, "bob")
    other_question(db)
    sign_up(client, username="alice")
    assert "鲍勃的私有题" not in client.get("/export/questions.csv").get_data(as_text=True)
