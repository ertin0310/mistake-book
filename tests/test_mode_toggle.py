"""步 5 演示：切模式 → 侧边栏两组跟着换；⚠️ 但模式不是权限（方案二-12、三-18）。

断言里刻意包含"复习模式下直敲首页网址照样 200"——这条是防止将来有人把模式
当成权限来实现。
"""

from config import prompts
from tests.conftest import csrf_token, sign_up


def test_mode_switch_requires_login(client):
    response = client.post("/mode/review", data={"csrf_token": "x"})
    assert response.status_code == 302 and "/login" in response.headers["Location"]


def test_mode_switch_writes_both_places(client, db):
    sign_up(client, username="stu")
    token = csrf_token(client, "/")
    assert client.post("/mode/review", data={"csrf_token": token}).status_code == 302

    row = db.execute("SELECT value FROM user_setting WHERE key='mode'").fetchone()
    assert row["value"] == "review"          # user_setting 一份：换浏览器还记住
    assert "复习" in client.get("/").get_data(as_text=True)


def test_new_user_defaults_to_study(client):
    """新用户还没录过题，默认落在学习模式（方案三-18）。"""
    sign_up(client, username="stu")
    body = client.get("/").get_data(as_text=True)
    assert 'class="mode on">学习' in body and 'class="mode">' in body


def test_menu_groups_swap_with_mode(client):
    """切模式 → 侧边栏那一组整块换掉（步 8、9 之后两组都有真条目了）。"""
    sign_up(client, username="stu")
    study_body = client.get("/").get_data(as_text=True)
    assert "/study/" in study_body and "/review/today" not in study_body   # 复习组整块不出现

    client.post("/mode/review", data={"csrf_token": csrf_token(client, "/")})
    review_body = client.get("/").get_data(as_text=True)
    assert "/review/today" in review_body and "/study/" not in review_body   # 换成复习组


def test_mode_is_not_a_permission(client):
    """★ 复习模式下直敲学习网址照样进——菜单跟着切，但拦人的是路由装饰器，不是模式。"""
    sign_up(client, username="stu")
    client.post("/mode/review", data={"csrf_token": csrf_token(client, "/")})
    assert client.get("/").status_code == 200


def test_unknown_mode_is_404(client):
    sign_up(client, username="stu")
    response = client.post("/mode/whatever", data={"csrf_token": csrf_token(client, "/")})
    assert response.status_code == 404


def test_mode_switch_needs_the_token(client):
    """没签不切换，但也不弹一整页错误——切模式是个小按钮，贴一句提示回到原页。"""
    sign_up(client, username="stu")
    response = client.post("/mode/review", data={})
    assert response.status_code == 302
    body = client.get(response.headers["Location"]).get_data(as_text=True)
    assert prompts.CSRF_FAILED in body
    assert 'class="mode on">学习' in body          # 模式没被改掉
