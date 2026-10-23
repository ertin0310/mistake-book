"""步 17 收尾：登录后那道《站点协议》的门（方案三-16a 的前半）。

判新旧一律用 `agreement.seq` 那个整数，不比版本号字符串——
`'SITE-2' > 'SITE-10'` 是字符串比较的正确答案、也是把人弹疯的正确答案的反面。
"""

import re

from config import agreement as kinds
from src.services import agreement_service
from tests.conftest import STAMP, add_user, csrf_token, sign_up

TOKEN = re.compile(r'name="csrf_token" value="([^"]+)"')


def agree(client, version="SITE-1", next_url="/study/"):
    return client.post(f"/agreement/{version}/accept",
                       data={"next": next_url, "csrf_token": csrf_token(client,
                                                                        f"/agreement/{version}")})


# ---------------------------------------------------------------- 门本身

def test_a_fresh_account_is_stopped_at_the_agreement(client):
    client.post("/register", data={"username": "stu", "password": "goodpass123",
                                   "confirm": "goodpass123",
                                   "csrf_token": csrf_token(client, "/register")})
    response = client.get("/study/")
    assert response.status_code == 302
    assert "/agreement/SITE-1" in response.headers["Location"]
    assert "next=/study/" in response.headers["Location"]        # 同意完要回到他原本要去的那页


def test_the_page_shows_the_text_from_the_database(client, db):
    sign_up(client, username="stu")
    db.execute("UPDATE agreement SET content=? WHERE version='SITE-1'", ("第五条测试正文",))
    db.commit()
    body = client.get("/agreement/SITE-1").get_data(as_text=True)
    assert "第五条测试正文" in body and "我已阅读并同意" in body


def test_accepting_once_opens_the_whole_site(client, db):
    sign_up(client, username="stu")
    assert agree(client).status_code == 302
    assert client.get("/study/").status_code == 200
    assert db.execute("SELECT COUNT(*) AS n FROM user_agreement").fetchone()["n"] == 1


def test_accepting_twice_does_not_record_twice(client):
    """重复点「同意」不该留两条痕迹——撤销同意将来要能对上号。"""
    sign_up(client, username="stu")
    agree(client)
    agree(client)
    body = client.get("/agreement/SITE-1").get_data(as_text=True)
    assert "奶蛙爱学习" in body                       # 已同意的人还能回来看这份协议


def test_agreement_gate_does_not_leak_outside_the_site(client):
    """`?next=https://evil` 不能跟着跳——开放重定向是白送的钓鱼位。"""
    client.post("/register", data={"username": "stu", "password": "goodpass123",
                                   "confirm": "goodpass123",
                                   "csrf_token": csrf_token(client, "/register")})
    response = agree(client, next_url="https://evil.example/x")
    assert response.headers["Location"].startswith("/")
    assert "evil" not in response.headers["Location"]


def test_post_without_token_cannot_record_consent(client):
    sign_up(client, username="stu")
    assert client.post("/agreement/SITE-1/accept", data={"next": "/study/"}).status_code == 400


def test_unknown_agreement_version_is_a_404(client):
    sign_up(client, username="stu")
    assert client.get("/agreement/SITE-99").status_code == 404


# ---------------------------------------------------------------- 升版必重弹

def test_a_new_version_prompts_again(client, db):
    """三-16a ★：正文升版，同意过旧版的人必须再同意一次。"""
    sign_up(client, username="stu")
    agree(client)
    db.execute("INSERT INTO agreement (version, seq, title, content, effective_from, created_at)"
               " VALUES ('SITE-2', 9, '站点协议', '新版正文', '2026-11-01', ?)", (STAMP,))
    db.commit()
    original = kinds.CURRENT["site"]
    kinds.CURRENT["site"] = "SITE-2"
    try:
        response = client.get("/study/")
        assert "/agreement/SITE-2" in response.headers["Location"]
        assert "新版正文" in client.get("/agreement/SITE-2").get_data(as_text=True)
    finally:
        kinds.CURRENT["site"] = original


def test_the_gate_is_judged_in_one_place_only(client, db):
    """★ 门写在 `app.py` 的 `before_request` 里：加页面不需要记得加判断。

    这条用例点遍所有已点亮的菜单链接，确认它们都被同一道门管着。
    """
    from config import menu
    client.post("/register", data={"username": "stu", "password": "goodpass123",
                                   "confirm": "goodpass123",
                                   "csrf_token": csrf_token(client, "/register")})
    for item in menu.MENU:
        if not item.visible or item.role == "admin":
            continue
        assert "/agreement/SITE-1" in client.get(item.url).headers.get("Location", ""), item.key


def test_seed_inserts_every_current_version():
    """配置里写的当前版本，seed 必须真的把那一版正文灌进来——两边漂移等于门开着却没锁。"""
    from pathlib import Path as _P
    source = _P(__file__).resolve().parent.parent / "src" / "data" / "seed.py"
    text = source.read_text(encoding="utf-8")
    for version in kinds.CURRENT.values():
        assert f'"{version}"' in text, version


def test_a_made_up_version_cannot_be_opened(client):
    """/agreement/SITE-99 不是"空的协议页"，是 404：随便编版本号钓不出东西。"""
    sign_up(client, username="stu")
    assert client.get("/agreement/SITE-99").status_code == 404
    assert client.post("/agreement/SITE-99/accept",
                       data={"csrf_token": csrf_token(client, "/study/")}).status_code == 404
