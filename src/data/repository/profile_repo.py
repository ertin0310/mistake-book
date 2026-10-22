"""`user_profile`（一行一人）与 `user_setting`（一行一个偏好）。

两张表都是 `user` scope：基类强制注入 `user_id`，读不到别人的资料，
也写不进别人的资料（`create()` 会把 `user_id` 覆盖成当前登录者）。

设置页在步 10，本文件只提供"注册时建一行空资料 + 按 key 读写偏好"这两件
步 4 立刻要用的事。字段清单来自 `config/user_fields.py`，不在这儿重复列一遍。
"""

import sqlite3

from config import user_fields
from src.data.repository.base import SCOPE_USER, BaseRepo


class ProfileRepo(BaseRepo):
    table = "user_profile"
    scope = SCOPE_USER

    def ensure_row(self) -> None:
        """注册后补一行空资料。已有就跳过（重复注册同一个人不该报错）。"""
        self.conn.execute(
            "INSERT OR IGNORE INTO user_profile (user_id, display_name, school)"
            " VALUES (:viewer, '', '')", {"viewer": self.viewer_id})

    def profile(self) -> dict:
        row = self.conn.execute(
            "SELECT display_name, school FROM user_profile WHERE user_id = :viewer",
            {"viewer": self.viewer_id}).fetchone()
        return dict(row) if row else {"display_name": "", "school": ""}


class SettingRepo(BaseRepo):
    table = "user_setting"
    scope = SCOPE_USER

    def all(self) -> dict:
        """默认值打底，库里有的覆盖上去——新用户一行设置都没写也能正常跑。"""
        values = dict(user_fields.defaults())
        for row in self.conn.execute("SELECT key, value FROM user_setting WHERE user_id = :viewer",
                                     {"viewer": self.viewer_id}):
            values[row["key"]] = row["value"]
        return values

    def set(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO user_setting (user_id, key, value) VALUES (:viewer, :key, :value)"
            " ON CONFLICT (user_id, key) DO UPDATE SET value = excluded.value",
            {"viewer": self.viewer_id, "key": key, "value": value})

    def clear_pending(self, key: str) -> None:
        """待生效的时间点被采纳之后要把那两行清掉（步 10 用得到，这里先备好）。"""
        self.conn.execute("DELETE FROM user_setting WHERE user_id = :viewer AND key = :key",
                          {"viewer": self.viewer_id, "key": key})
