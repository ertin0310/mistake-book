"""`question_bank`：唯一走 `named` scope 的表（方案二-5）。

★ 两个具名读法，**禁止混用一条 SQL**：
    mine          —— 我自己的题（含我共享出去的、含我软删的由 deleted_at 挡掉）
    shared_pool   —— 别人共享给我的 + 官方题（user_id 为 NULL 也算）
  为什么必须分开：`user_id` 这一列在官方题上是 NULL，一条 SQL 同时表达
  "我的"和"共享池"就一定会漏掉其中一种——漏掉官方题时，共享池看着是空的，
  功能当场"是坏的"。基类对 named 表直接拒绝通用读法，混用在入口就报错。

`user_id` 由 `add()` 强制填成当前登录者，不接受调用方传别人的 id。
"""

import sqlite3

from config import settings
from src.data.repository.base import SCOPE_NAMED, BaseRepo

MINE = "user_id = :viewer AND deleted_at IS NULL"
SHARED_POOL = ("deleted_at IS NULL AND delisted_by IS NULL AND visibility = 'shared'"
               " AND (user_id IS NULL OR user_id <> :viewer)")


class QuestionRepo(BaseRepo):
    table = "question_bank"
    scope = SCOPE_NAMED
    named_reads = ("mine", "shared_pool")

    def __init__(self, conn: sqlite3.Connection, viewer_id: int):
        super().__init__(conn, viewer_id)

    # ------------------------------------------------------------ 两个具名读法

    def mine(self, page: int = 1, subject_id: int | None = None, size: int | None = None):
        return self._page("mine", MINE, page, subject_id, size)

    def shared_pool(self, page: int = 1, subject_id: int | None = None, size: int | None = None):
        return self._page("shared_pool", SHARED_POOL, page, subject_id, size)

    def _page(self, read_name: str, clause: str, page: int, subject_id, size):
        where, params = clause, {}
        if subject_id:
            where = f"({clause}) AND subject_id = :subject"
            params["subject"] = int(subject_id)
        return self.read_named(read_name, where, params, order="id DESC",
                               page=page, page_size=size or settings.PAGE_SIZE)

    def mine_one(self, question_id: int):
        """取自己的一道题。named 表不许走基类的 `get()`，所以"按 id 取"也要有个名字。"""
        page = self.read_named("mine", f"({MINE}) AND id = :only", {"only": question_id})
        return page.items[0] if page.items else None

    # ------------------------------------------------------------ 写

    def add(self, subject_id: int, type_name: str, stem: str, options_json: str,
            answer_json: str, explanation: str, source: str = "manual") -> int:
        cursor = self.conn.execute(
            "INSERT INTO question_bank (user_id, subject_id, type, stem, options_json,"
            " answer_json, explanation, source, visibility, created_at, updated_at)"
            " VALUES (:viewer, :subject, :type, :stem, :options, :answer, :explanation,"
            " :source, 'private', datetime('now','localtime'), datetime('now','localtime'))",
            {"viewer": self.viewer_id, "subject": subject_id, "type": type_name,
             "stem": stem, "options": options_json, "answer": answer_json,
             "explanation": explanation, "source": source})
        self.conn.commit()
        return int(cursor.lastrowid)

    def touch(self, question_id: int) -> None:
        """改题面直接生效、不做快照（方案三-10）：只更新时间戳。"""
        self.conn.execute("UPDATE question_bank SET updated_at=datetime('now','localtime')"
                          " WHERE id=? AND user_id=?", (question_id, self.viewer_id))
