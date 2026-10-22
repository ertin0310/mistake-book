"""注册与登录的业务规则。路由里不许出现这些判断（方案二-1）。

本层不碰 Flask 的 session：它只吃 `conn` 和参数，返回用户行或抛自定义错误。
"登录了没有"是 web 层的事（`src/web/decorators.py`）。
"""

import secrets
import sqlite3

import bcrypt

from config import prompts
from src.data.repository.profile_repo import ProfileRepo
from src.data.repository.user_repo import UserRepo
from src.domain.errors import ValidationError

MIN_PASSWORD = 8
MAX_USERNAME = 20
ROLE_MEMBER = "member"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def _check_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        # 库里存的不是合法 bcrypt 串：按"密码不对"处理，不往外抛。
        return False


def register(conn: sqlite3.Connection, username: str, password: str, confirm: str) -> dict:
    """注册一律 member（三-16）：唯一的提权入口是 seed 预置的 admin 与后台角色页。"""
    username = (username or "").strip()
    if not username or not password or not confirm:
        raise ValidationError(prompts.FIELD_REQUIRED)
    if len(username) > MAX_USERNAME:
        raise ValidationError(prompts.USERNAME_TOO_LONG)
    if len(password) < MIN_PASSWORD:
        raise ValidationError(prompts.PASSWORD_TOO_SHORT)
    if password != confirm:
        raise ValidationError(prompts.PASSWORD_CONFIRM_MISMATCH)

    repo = UserRepo(conn)
    if repo.by_username(username) is not None:
        raise ValidationError(prompts.USERNAME_TAKEN)
    try:
        user_id = repo.register(username, hash_password(password), ROLE_MEMBER)
    except sqlite3.IntegrityError:
        # 两个人同时提交同名：以数据库的 UNIQUE 为准，别自己判完再插。
        raise ValidationError(prompts.USERNAME_TAKEN) from None
    ProfileRepo(conn, user_id).ensure_row()
    conn.commit()
    return {"id": user_id, "username": username, "role": ROLE_MEMBER}


def login(conn: sqlite3.Connection, username: str, password: str) -> dict:
    """用户名不存在与密码不对给**同一句**提示：不然这页就成了"查哪些用户名存在"的工具。"""
    username = (username or "").strip()
    if not username or not password:
        raise ValidationError(prompts.FIELD_REQUIRED)
    row = UserRepo(conn).by_username(username)
    if row is None or not _check_password(password, row["password_hash"]):
        raise ValidationError(prompts.CREDENTIALS_WRONG)
    return {"id": row["id"], "username": row["username"], "role": row["role"]}
