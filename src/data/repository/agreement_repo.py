"""`agreement`（字典表）与 `user_agreement`（谁同意过哪一版）。

两张表分工：前者是正文，全站一份、只增不改（改了就是新版本）；
后者是一条条同意记录，**只追加**——"某人于某时同意过 SITE-1"是历史事实，
将来升版或争议都要拿得出来。
"""

import sqlite3

from src.data.repository.base import SCOPE_DICT, SCOPE_USER, BaseRepo


class AgreementRepo(BaseRepo):
    table = "agreement"
    scope = SCOPE_DICT

    def by_version(self, version: str):
        return self.conn.execute("SELECT * FROM agreement WHERE version=?", (version,)).fetchone()


class UserAgreementRepo(BaseRepo):
    table = "user_agreement"
    scope = SCOPE_USER

    def agreed(self, version: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM user_agreement WHERE user_id=? AND version=?",
            (self.viewer_id, version)).fetchone()
        return row is not None

    def record(self, version: str) -> None:
        """记一次同意。同一版重复记没有意义，所以先查再写（不上唯一索引：
        将来"撤销同意"要能留痕，索引会挡住那条路）。"""
        if self.agreed(version):
            return
        self.conn.execute(
            "INSERT INTO user_agreement (user_id, version, agreed_at)"
            " VALUES (?, ?, datetime('now','localtime'))", (self.viewer_id, version))
        self.conn.commit()
