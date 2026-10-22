"""步 4 演示：注册 → 登录 → 进首页；三种非法输入各有中文提示且不崩；
★ 把表单里那行防冒名签删掉再提交，给的是"页面放得太久了"，不是 500。
"""

import pytest

from config import prompts
from src.data.repository.profile_repo import ProfileRepo
from src.domain.errors import ValidationError
from src.services import auth_service
from tests.conftest import csrf_token, sign_up


def register(conn, username="stu", password="goodpass123", confirm=None):
    return auth_service.register(conn, username, password, confirm or password)


# ---------------------------------------------------------------- service 层

def test_register_then_login(db):
    user = register(db)
    assert user["role"] == "member"          # 注册一律 member（三-16）
    assert auth_service.login(db, "stu", "goodpass123")["id"] == user["id"]


def test_register_creates_profile_row(db):
    user = register(db)
    assert ProfileRepo(db, user["id"]).profile() == {"display_name": "", "school": ""}


def test_duplicate_username(db):
    register(db)
    with pytest.raises(ValidationError) as exc:
        register(db)
    assert exc.value.message == prompts.USERNAME_TAKEN


@pytest.mark.parametrize("password,confirm,wanted", [
    ("short", "short", prompts.PASSWORD_TOO_SHORT),
    ("goodpass123", "goodpass999", prompts.PASSWORD_CONFIRM_MISMATCH),
    ("", "", prompts.FIELD_REQUIRED),
])
def test_bad_password_input_gives_chinese_hint(db, password, confirm, wanted):
    with pytest.raises(ValidationError) as exc:
        auth_service.register(db, "stu", password, confirm)
    assert exc.value.message == wanted


def test_unknown_user_and_wrong_password_share_one_message(db):
    register(db)
    for username, password in (("stu", "wrongpass1"), ("ghost", "goodpass123")):
        with pytest.raises(ValidationError) as exc:
            auth_service.login(db, username, password)
        assert exc.value.message == prompts.CREDENTIALS_WRONG


def test_password_is_not_stored_in_plaintext(db):
    register(db)
    stored = db.execute("SELECT password_hash FROM user WHERE username='stu'").fetchone()
    assert "goodpass123" not in stored["password_hash"]
    assert stored["password_hash"].startswith("$2b$")


# ---------------------------------------------------------------- web 层

def test_home_requires_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_register_without_token_is_rejected_with_chinese_hint(client):
    response = client.post("/register", data={
        "username": "stu", "password": "goodpass123", "confirm": "goodpass123"})
    body = response.get_data(as_text=True)
    assert response.status_code == 400
    assert prompts.CSRF_FAILED in body and "Traceback" not in body


def test_full_register_flow(client):
    assert sign_up(client).status_code == 302
    home = client.get("/")
    assert home.status_code == 200 and "stu" in home.get_data(as_text=True)


def test_logout_ends_the_session(client):
    sign_up(client)
    client.post("/logout", data={"csrf_token": csrf_token(client, "/")})
    assert client.get("/").status_code == 302


def test_login_page_rejects_wrong_password(client):
    sign_up(client)
    client.post("/logout", data={"csrf_token": csrf_token(client, "/")})
    token = csrf_token(client, "/login")
    response = client.post("/login", data={"username": "stu", "password": "nope-nope-nope",
                                           "csrf_token": token})
    assert response.status_code == 400
    assert prompts.CREDENTIALS_WRONG in response.get_data(as_text=True)


def test_next_param_cannot_bounce_offsite(client):
    sign_up(client)
    client.post("/logout", data={"csrf_token": csrf_token(client, "/")})
    token = csrf_token(client, "/login")
    response = client.post("/login", data={"username": "stu", "password": "goodpass123",
                                           "csrf_token": token, "next": "//evil.example.com"})
    assert response.status_code == 302
    assert "evil.example.com" not in response.headers["Location"]
