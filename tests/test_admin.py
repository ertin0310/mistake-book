# 步 23 演示：管理后台。
#
# 三条最要紧：普通用户进不去（菜单只是导航，拦人的是装饰器）、科目没有"删除"这个
# 动作、管理员读不到任何人的私有数据。

from config import prompts
from src.data.repository.knowledge_repo import KnowledgeRepo
from tests.conftest import add_user, csrf_token, sign_up, uid_of

PAGES = ("/admin/", "/admin/subject", "/admin/knowledge", "/admin/appeal",
         "/admin/diagnostics")


def admin_client(client, db, username="boss"):
    admin = client.application.test_client()
    sign_up(admin, username=username, password="bosspass123")
    db.execute("UPDATE user SET role='admin' WHERE username=?", (username,))
    db.commit()
    admin.post("/logout", data={"csrf_token": csrf_token(admin, "/appeal/")})
    admin.post("/login", data={"username": username, "password": "bosspass123",
                               "csrf_token": csrf_token(admin, "/login")})
    return admin


def test_admin_pages_are_closed_to_members(client):
    sign_up(client, username="stu")
    for path in PAGES:
        assert client.get(path).status_code == 403, path


def test_admin_pages_need_login(client):
    for path in PAGES:
        assert client.get(path).status_code == 302, path


def test_admin_can_open_every_page(client, db):
    admin = admin_client(client, db)
    for path in PAGES:
        assert admin.get(path).status_code == 200, path


def test_sidebar_shows_the_admin_entry_only_to_admins(client, db):
    sign_up(client, username="stu")
    assert prompts.ADMIN_ENTRY not in client.get("/").get_data(as_text=True).split("管理")[0]
    admin = admin_client(client, db)
    assert "/admin/" in admin.get("/").get_data(as_text=True)


def test_subject_can_be_created_renamed_and_hidden_but_never_deleted(client, db):
    admin = admin_client(client, db)
    token = csrf_token(admin, "/admin/subject")
    admin.post("/admin/subject", data={"action": "create", "name": "天文学",
                                       "csrf_token": token})
    row = db.execute("SELECT id, status FROM subject WHERE name='天文学'").fetchone()
    assert row is not None and row["status"] == "active"

    admin.post("/admin/subject", data={"action": "rename", "subject_id": str(row["id"]),
                                       "name": "天体物理", "csrf_token": token})
    assert db.execute("SELECT name FROM subject WHERE id=?", (row["id"],)).fetchone()[0] == "天体物理"

    admin.post("/admin/subject", data={"action": "toggle", "subject_id": str(row["id"]),
                                       "csrf_token": token})
    assert db.execute("SELECT status FROM subject WHERE id=?", (row["id"],)).fetchone()[0] == "hidden"
    # 停用不是删除：行还在库里，被它引用的题也不会跟着消失
    assert db.execute("SELECT COUNT(*) AS n FROM subject WHERE id=?",
                      (row["id"],)).fetchone()["n"] == 1
    body = admin.get("/admin/subject").get_data(as_text=True)
    assert prompts.ADMIN_NO_DELETE in body


def test_duplicate_subject_name_gives_a_chinese_hint(client, db):
    admin = admin_client(client, db)
    token = csrf_token(admin, "/admin/subject")
    admin.post("/admin/subject", data={"action": "create", "name": "数学", "csrf_token": token})
    body = admin.get("/admin/subject").get_data(as_text=True)
    assert prompts.ADMIN_NAME_CLASH in body


def test_approving_removes_a_point_from_the_queue_and_rejecting_tells_the_author(client, db):
    sign_up(client, username="stu")
    alice = uid_of(db, "stu")
    point_id = KnowledgeRepo(db, alice).submit(alice, 1, "张衡地动仪")   # 夹具里的数学科目
    admin = admin_client(client, db)
    assert point_id in {row["id"] for row in KnowledgeRepo(db).pending()}

    token = csrf_token(admin, "/admin/knowledge")
    admin.post("/admin/knowledge", data={"action": "reject", "point_id": str(point_id),
                                         "note": "教材里叫候风地动仪", "csrf_token": token})
    assert point_id not in {row["id"] for row in KnowledgeRepo(db).pending()}
    # 驳回带原因：作者在自己的页面上看得到，别人连这一条都看不见
    body = client.get("/knowledge/mine").get_data(as_text=True)
    assert "教材里叫候风地动仪" in body
    bob = client.application.test_client()
    sign_up(bob, username="bob")
    assert "张衡地动仪" not in bob.get("/knowledge/").get_data(as_text=True)

    admin.post("/admin/knowledge", data={"action": "approve", "point_id": str(point_id),
                                         "csrf_token": token})
    assert db.execute("SELECT reviewed_by FROM knowledge_point WHERE id=?",
                      (point_id,)).fetchone()[0] == uid_of(db, "boss")


def test_admin_never_sees_anyone_elses_private_rows(client, db):
    """★ 后台四页里不该出现任何人的错题题干（七-1、三-23 第四条禁令）。"""
    add_user(db, 88, "member88")
    db.execute("INSERT INTO question_bank (id, user_id, subject_id, type, stem, options_json,"
               " answer_json, explanation, source, visibility, created_at, updated_at)"
               " VALUES (900, 88, 1, 'essay', '只有我自己看得见的题干', '[]',"
               " '{\"text\":\"答\"}', '', 'manual', 'private',"
               " '2026-10-21 10:00:00', '2026-10-21 10:00:00')")
    db.execute("INSERT INTO mistake (user_id, question_id, entry_reason, step_index,"
               " interval_days, due_date, review_count, lapse_count, created_at, updated_at)"
               " VALUES (88, 900, 'marked_wrong', 0, 0, '2026-10-21', 0, 0,"
               " '2026-10-21 10:00:00', '2026-10-21 10:00:00')")
    db.commit()
    admin = admin_client(client, db)
    for path in PAGES:
        assert "只有我自己看得见的题干" not in admin.get(path).get_data(as_text=True), path


def test_diagnostics_lists_tables_and_db_path(client, db):
    """建库自检搬到后台后照样能用：一张命令看得见的表数 + 库文件路径（他 2026-10-23 要求）。"""
    body = admin_client(client, db).get("/admin/diagnostics").get_data(as_text=True)
    assert prompts.ADMIN_DIAGNOSTICS_TITLE in body and prompts.ADMIN_DIAGNOSTICS_OK in body
    for table in ("question_bank", "mistake", "review_log"):
        assert table in body


def test_selfcheck_no_longer_shows_on_the_home_page(client):
    """★ 普通用户首页不再铺表名与库路径——那本来就是给开发者看的东西。"""
    sign_up(client, username="stu")
    body = client.get("/").get_data(as_text=True)
    assert "user_setting" not in body and "mistake_book.db" not in body
    assert prompts.ADMIN_DIAGNOSTICS_TITLE not in body
    assert prompts.HOME_QUICK_TITLE in body and prompts.HOME_FIG_DUE in body
