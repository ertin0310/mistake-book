# 步 19 演示：共享开关 + 《共享须知》三态（方案三-10、三-16a）。
#
# 三颗按钮的后果各不相同，必须逐条钉住：仅本次不记长期授权、长期授权绑版本号、
# 升版必重弹、取消什么都不做。默认私有这条更要紧——它是"用户主动才公开"的承诺。

from config import agreement
from src.data.repository.question_repo import QuestionRepo
from src.services import question_service
from tests.conftest import csrf_token, sign_up, uid_of


def new_client(client):
    # 第二个登录者：同一个应用，另开一个会话，模拟"另一个人"
    other = client.application.test_client()
    return other


def make_question(client, db, username, stem):
    token = csrf_token(client, "/study/new")
    client.post("/study/new", data={"subject_id": "1", "type": "essay", "stem": stem,
                                    "answer": "参考答案", "explanation": "解析",
                                    "csrf_token": token})
    uid = uid_of(db, username)
    row = QuestionRepo(db, uid).mine_all()[-1]
    return row["id"], uid


def share(client, question_id):
    return client.post(f"/study/share/{question_id}",
                       data={"csrf_token": csrf_token(client, "/study/")})


def decide(client, question_id, decision):
    return client.post(f"/study/share/{question_id}/decide",
                       data={"decision": decision, "csrf_token": csrf_token(client, "/study/")})


def agreed_versions(db, uid):
    return [row["version"] for row in db.execute(
        "SELECT version FROM user_agreement WHERE user_id=?", (uid,))]


def test_a_new_question_is_private_and_invisible_to_others(client, db):
    sign_up(client, username="alice")
    question_id, _uid = make_question(client, db, "alice", "爱丽丝的题")
    bob = new_client(client)
    sign_up(bob, username="bob")
    assert "爱丽丝的题" not in bob.get("/study/drill").get_data(as_text=True)
    assert db.execute("SELECT visibility FROM question_bank WHERE id=?",
                      (question_id,)).fetchone()[0] == "private"


def test_the_first_share_click_shows_the_terms_instead_of_publishing(client, db):
    sign_up(client, username="alice")
    question_id, uid = make_question(client, db, "alice", "要点共享的题")
    page = share(client, question_id)
    body = page.get_data(as_text=True)
    assert "仅本次同意并共享" in body and "同意并授予长期授权" in body
    assert "取消，暂不共享" in body
    assert db.execute("SELECT visibility FROM question_bank WHERE id=?",
                      (question_id,)).fetchone()[0] == "private"   # 还没共享出去
    # 弹一次须知不等于同意：登录时签的是 SITE-1，这里 SHARE 版本不该出现在记录里
    assert agreement.CURRENT["share"] not in agreed_versions(db, uid)


def test_once_does_not_grant_long_term_consent(client, db):
    sign_up(client, username="alice")
    question_id, uid = make_question(client, db, "alice", "只同意这一次的题")
    assert decide(client, question_id, "once").status_code == 302
    assert db.execute("SELECT visibility, shared_at FROM question_bank WHERE id=?",
                      (question_id,)).fetchone()[0] == "shared"
    assert agreement.CURRENT["share"] not in agreed_versions(db, uid)   # 仅本次：不记长期授权
    assert "仅本次同意并共享" in share(client, question_id).get_data(as_text=True)  # 下次还弹


def test_long_term_consent_stops_the_popup_and_is_version_bound(client, db):
    sign_up(client, username="alice")
    q1, uid = make_question(client, db, "alice", "长期授权第一题")
    q2, _ = make_question(client, db, "alice", "长期授权第二题")
    decide(client, q1, "always")
    assert agreed_versions(db, uid) == ["SITE-1", agreement.CURRENT["share"]]
    # 签过当前版本 → 第二题直接共享出去，不再弹
    assert share(client, q2).status_code == 302
    assert db.execute("SELECT visibility FROM question_bank WHERE id=?",
                      (q2,)).fetchone()[0] == "shared"


def test_a_new_terms_version_prompts_again(client, db):
    """须知正文升版：签过旧版的人必须再确认一次（三-16a ★）。"""
    sign_up(client, username="alice")
    question_id, uid = make_question(client, db, "alice", "升版还要再弹")
    decide(client, question_id, "always")
    db.execute("INSERT INTO agreement (version, seq, title, content, effective_from, created_at)"
               " VALUES ('SHARE-2', 99, '共享须知', '新版正文', '2026-11-01',"
               " '2026-11-01 10:00:00')")
    db.commit()
    original = agreement.CURRENT["share"]
    agreement.CURRENT["share"] = "SHARE-2"
    try:
        body = share(client, question_id).get_data(as_text=True)
        assert "新版正文" in body
    finally:
        agreement.CURRENT["share"] = original


def test_cancel_publishes_nothing(client, db):
    sign_up(client, username="alice")
    question_id, _uid = make_question(client, db, "alice", "点了取消的题")
    decide(client, question_id, "cancel")
    assert db.execute("SELECT visibility FROM question_bank WHERE id=?",
                      (question_id,)).fetchone()[0] == "private"


def test_a_shared_question_reaches_the_other_side_and_unshare_pulls_it_back(client, db):
    sign_up(client, username="alice")
    question_id, _uid = make_question(client, db, "alice", "共享给别人看的题")
    decide(client, question_id, "once")
    bob = new_client(client)
    sign_up(bob, username="bob")
    assert "共享给别人看的题" in bob.get("/study/drill").get_data(as_text=True)

    client.post(f"/study/unshare/{question_id}",
                data={"csrf_token": csrf_token(client, "/study/")})
    assert "共享给别人看的题" not in bob.get("/study/drill").get_data(as_text=True)
    # 撤销只收回 visibility，shared_at 留着当线索
    assert db.execute("SELECT shared_at FROM question_bank WHERE id=?",
                      (question_id,)).fetchone()[0] is not None


def test_you_cannot_share_someone_elses_question(client, db):
    sign_up(client, username="alice")
    question_id, _uid = make_question(client, db, "alice", "爱丽丝的私有题")
    bob = new_client(client)
    sign_up(bob, username="bob")
    assert bob.post(f"/study/share/{question_id}",
                    data={"csrf_token": csrf_token(bob, "/study/")}).status_code == 404
    assert bob.post(f"/study/unshare/{question_id}",
                    data={"csrf_token": csrf_token(bob, "/study/")}).status_code == 404


def test_the_terms_text_comes_from_the_database(client, db):
    sign_up(client, username="alice")
    db.execute("UPDATE agreement SET content=? WHERE version=?",
               ("共享须知正文第九条", agreement.CURRENT["share"]))
    db.commit()
    question_id, _uid = make_question(client, db, "alice", "要看须知的题")
    assert "共享须知正文第九条" in share(client, question_id).get_data(as_text=True)
