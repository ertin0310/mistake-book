# 步 24 演示：申诉与反馈四类一个入口，不建站内信。
#
# 三条口径要钉住：同一对象只允许一条未处理（防灌，但处理完要能再提）、
# 收尾必须写回复、被处置的作者永远看不到是谁提的。

from config import appeal, prompts
from tests.conftest import csrf_token, sign_up


def submit(client, category="other", reason="这道题的答案我认为有问题", target_id=""):
    return client.post("/appeal/", data={"category": category, "reason": reason,
                                         "target_id": target_id,
                                         "csrf_token": csrf_token(client, "/appeal/")})


def test_appeal_page_requires_login(client):
    assert client.get("/appeal/").status_code == 302


def test_all_four_categories_can_be_submitted(client, db):
    sign_up(client, username="stu")
    for index, (key, label) in enumerate(appeal.LABELS.items()):
        # 同一对象只允许一条未处理，所以四类各挂一个不同编号（other 不挂对象）
        target = str(100 + index) if appeal.TARGET_OF[key] != "none" else ""
        response = submit(client, key, f"{label}的说明第 {index} 条", target)
        assert response.status_code == 302, key
    body = client.get("/appeal/").get_data(as_text=True)
    for label in appeal.LABELS.values():
        assert label in body
    assert body.count("待处理") == len(appeal.LABELS)


def test_empty_reason_and_unknown_category_are_rejected(client):
    sign_up(client, username="stu")
    assert "请写一句具体的说明" in submit(client, "other", "   ").get_data(as_text=True)
    assert prompts.APPEAL_BAD_CATEGORY in submit(client, "不存在的类", "有内容").get_data(as_text=True)


def test_one_open_appeal_per_target_then_allows_a_second_round(client, db):
    """防灌：同一对象只允许一条未处理；处理完之后允许再提（所以不上唯一索引）。"""
    sign_up(client, username="stu")
    submit(client, "content", "第一次反馈", "7")
    second = submit(client, "content", "同一件事再提一次", "7")
    assert prompts.APPEAL_ALREADY_OPEN in second.get_data(as_text=True)
    assert second.status_code == 400

    admin = _admin_client(client, db)
    row = db.execute("SELECT id FROM appeal WHERE status='open'").fetchone()
    admin.post("/admin/appeal", data={"appeal_id": str(row["id"]), "reply": "已核对，答案没错",
                                      "csrf_token": csrf_token(admin, "/admin/appeal")})
    assert submit(client, "content", "处理完之后还能再提", "7").status_code == 302


def test_the_user_sees_the_reply_without_any_message_center(client, db):
    """★ 不建站内信：结果就显示在这个页面上。"""
    sign_up(client, username="stu")
    submit(client, "other", "想问一句为什么不能批量改科目")
    admin = _admin_client(client, db)
    row = db.execute("SELECT id FROM appeal").fetchone()
    admin.post("/admin/appeal", data={"appeal_id": str(row["id"]), "reply": "第二期做批量编辑",
                                      "csrf_token": csrf_token(admin, "/admin/appeal")})
    body = client.get("/appeal/").get_data(as_text=True)
    assert "第二期做批量编辑" in body and "已处理" in body


def test_closing_requires_a_reply(client, db):
    sign_up(client, username="stu")
    submit(client, "other", "没有回复就不许关掉")
    admin = _admin_client(client, db)
    row = db.execute("SELECT id FROM appeal").fetchone()
    body = admin.post("/admin/appeal", data={"appeal_id": str(row["id"]), "reply": "  ",
                                             "csrf_token": csrf_token(admin, "/admin/appeal")},
                      follow_redirects=True).get_data(as_text=True)
    assert prompts.APPEAL_REPLY_REQUIRED in body
    assert db.execute("SELECT status FROM appeal WHERE id=?", (row["id"],)).fetchone()[0] == "open"


def _admin_client(client, db, username="boss"):
    """另开一个会话：注册成普通成员 → 库里提权 → 重新登录把角色读进会话。

    ★ 提权只能由后台那一条路做（这里直接改库当测试夹具），角色是登录时写进会话的，
      所以改完必须重新登录一次，否则会话里还是 member。
    """
    admin = client.application.test_client()
    sign_up(admin, username=username, password="bosspass123")
    db.execute("UPDATE user SET role='admin' WHERE username=?", (username,))
    db.commit()
    admin.post("/logout", data={"csrf_token": csrf_token(admin, "/appeal/")})
    admin.post("/login", data={"username": username, "password": "bosspass123",
                               "csrf_token": csrf_token(admin, "/login")})
    assert db.execute("SELECT role FROM user WHERE username=?", (username,)).fetchone()[0] == "admin"
    return admin
