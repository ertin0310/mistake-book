"""`mistake`：复习队列（`user` scope，一行 = 一道错题）。

★ 这一张表**永不物理删**（方案三-11）：`review_log.mistake_id` 指着它，
  回收站到期只打 `purged_at` 做"过期封存"，行留在库里。

`due_page()` 是全站唯一取"今天该刷哪些题"的地方，四条条件一条都不能漏：
    m.deleted_at IS NULL          漏了会让回收站里的错题照天排期
    q.deleted_at IS NULL          作者把题删了就不该再排
    q.delisted_by IS NULL         ★ 被官方收起的不排期（v7.2）
    (q.user_id = :viewer OR q.visibility = 'shared')   自己的 + 共享池的
    m.due_date <= :review_date    到期判定按"复习日"，不是自然日
"""

import sqlite3

from config import schedule
from src.data.repository.base import SCOPE_USER, BaseRepo
from src.domain import clock

DUE_JOIN = (
    "FROM mistake m JOIN question_bank q ON q.id = m.question_id"
    " WHERE m.user_id = :viewer AND m.deleted_at IS NULL AND m.purged_at IS NULL"
    " AND q.deleted_at IS NULL AND q.delisted_by IS NULL"
    " AND (q.user_id = :viewer OR q.visibility = 'shared')"
    " AND m.due_date <= :review_date")

DEFAULTS = dict(entry_reason="marked_wrong", step_index=0, interval_days=0,
                review_count=0, lapse_count=0)


class MistakeRepo(BaseRepo):
    table = "mistake"
    scope = SCOPE_USER

    def rows_active(self) -> list:
        """活跃错题：未删、也未过期封存。统计四格与"还有多少没刷完"都只认这份。"""
        return self.rows(where="deleted_at IS NULL AND purged_at IS NULL", order="due_date")

    def active_for(self, question_id: int):
        """同一道题只允许一条活跃错题（partial unique: user_id+question_id WHERE 未删）。"""
        return self.conn.execute(
            "SELECT * FROM mistake WHERE user_id=:viewer AND question_id=:q"
            " AND deleted_at IS NULL", {"viewer": self.viewer_id, "q": question_id}).fetchone()

    def add(self, question_id: int, due_date, entry_reason: str = "marked_wrong") -> int:
        params = dict(DEFAULTS, question_id=question_id, user_id=self.viewer_id,
                      due_date=clock.to_date_str(due_date))
        params["entry_reason"] = entry_reason
        names, marks = ", ".join(params), ", ".join(f":{k}" for k in params)
        cursor = self.conn.execute(
            f"INSERT INTO mistake ({names}, created_at, updated_at)"
            f" VALUES ({marks}, datetime('now','localtime'), datetime('now','localtime'))",
            params)
        self.conn.commit()
        return int(cursor.lastrowid)

    def apply_move(self, mistake_id: int, move) -> None:
        """把 `Move` 算出来的新状态写回队列（`review_log` 由 service 另记一笔）。

        参数是步 6 的 `Move` 对象而不是散开的四个值：这样"写回队列"和"记流水"
        读的是同一份计算结果，不可能一个用新值一个用旧值。
        """
        after = move.after
        self.conn.execute(
            "UPDATE mistake SET step_index=:step, interval_days=:interval, due_date=:due,"
            " last_reviewed_at=:now, review_count=review_count+1,"
            " lapse_count=lapse_count+:lapsed, updated_at=:now"
            " WHERE id=:id AND user_id=:viewer",
            {"step": after.step_index, "interval": after.interval_days,
             "due": clock.to_date_str(after.due_date),
             "now": clock.now().strftime("%Y-%m-%d %H:%M:%S"),
             "lapsed": 1 if move.lapsed else 0,
             "id": mistake_id, "viewer": self.viewer_id})

    def due_page(self, review_date, page: int = 1, limit: int | None = None):
        """今日复习的一页。★ 上限只管 `LIMIT`，**不许为了凑数去改 `due_date`**（三-11）。"""
        size = limit or schedule.DAILY_CAP_DEFAULT
        params = {"viewer": self.viewer_id, "review_date": clock.to_date_str(review_date)}
        total = int(self.conn.execute(f"SELECT COUNT(*) {DUE_JOIN}", params).fetchone()[0])
        offset = max(0, (max(1, page) - 1) * size)
        rows = self.conn.execute(
            f"SELECT m.*, q.stem, q.type, q.subject_id, q.options_json, q.answer_json,"
            f" q.explanation {DUE_JOIN} ORDER BY m.due_date ASC, m.id ASC"
            f" LIMIT {int(size)} OFFSET {int(offset)}", params).fetchall()
        pages = max(1, -(-total // size))
        return rows, total, min(max(1, page), pages), pages

    def count_due(self, review_date) -> int:
        return int(self.conn.execute(
            f"SELECT COUNT(*) {DUE_JOIN}",
            {"viewer": self.viewer_id, "review_date": clock.to_date_str(review_date)}
        ).fetchone()[0])
