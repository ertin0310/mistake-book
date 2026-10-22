"""`user` 表：登录名、密码哈希、角色。

scope 用 `dict`（所有人可读、无归属人过滤）。★ 注册是**唯一一件"写之前还没有登录者"
的操作**，所以这里不能走基类的 `create()`：那条路会把 `user_id` 注入成当前会话的人，
而注册时根本没有会话。基类对非 user scope 一律拒绝写入正是为了逼出这个说明——
本文件因此自己写 INSERT，且只写这一条。
"""

import sqlite3

from src.data.repository.base import SCOPE_DICT, BaseRepo


class UserRepo(BaseRepo):
    table = "user"
    scope = SCOPE_DICT

    def __init__(self, conn: sqlite3.Connection):
        super().__init__(conn, viewer_id=None)

    def by_username(self, username: str):
        return self.conn.execute("SELECT * FROM user WHERE username = ?", (username,)).fetchone()

    def register(self, username: str, password_hash: str, role: str) -> int:
        """插入一个账号。用户名撞唯一约束由调用方（service）捕获并翻成中文提示。"""
        cursor = self.conn.execute(
            "INSERT INTO user (username, password_hash, role, created_at)"
            " VALUES (?, ?, ?, datetime('now','localtime'))",
            (username, password_hash, role))
        return int(cursor.lastrowid)
