"""步 5 演示：切模式 → 侧边栏两组跟着换；⚠️ 但模式不是权限（方案二-12、三-18）。

断言里刻意包含"复习模式下直敲首页网址照样 200"——这条是防止将来有人把模式
当成权限来实现。
"""

import re

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


def sidebar(body):
    """只看侧边栏那一块。首页正文里本来就写着"今日复习"等功能名，整页比会误判。"""
    match = re.search(r"<aside.*?</aside>", body, re.S)
    assert match, "页面里没有侧边栏"
    return match.group(0)


def test_menu_groups_swap_with_mode(client):
    """切模式 → 那一组整块换掉；但「录题 / 导入」两种模式都得在。"""
    sign_up(client, username="stu")
    study_bar = sidebar(client.get("/").get_data(as_text=True))
    assert "我的题目" in study_bar and "今日复习" not in study_bar   # 复习组整块不出现

    client.post("/mode/review", data={"csrf_token": csrf_token(client, "/")})
    review_bar = sidebar(client.get("/").get_data(as_text=True))
    assert "今日复习" in review_bar and "我的题目" not in review_bar  # 换成复习组

    # ★ 录题不该被模式挡住：复习模式下也要能手动录题、能传 CSV
    for bar in (study_bar, review_bar):
        assert "手动录题" in bar and "CSV 录题" in bar


def test_mode_buttons_land_on_that_mode_home(client):
    """点「学习」跳我的题目、点「复习」跳今日复习——切完停在原地会让人觉得开关没生效。"""
    sign_up(client, username="stu")
    to_review = client.post("/mode/review", data={"csrf_token": csrf_token(client, "/")})
    assert to_review.headers["Location"].endswith("/review/today")
    to_study = client.post("/mode/study",
                           data={"csrf_token": csrf_token(client, "/review/today")})
    assert to_study.headers["Location"].endswith("/study/")


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
