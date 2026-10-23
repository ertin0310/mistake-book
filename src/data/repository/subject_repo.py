"""`subject` 表：系统级共享字典（方案三-5）。

scope 用 `dict` + 可见性判据 `subject_visible`：**所有人只读，写只走 `require_admin()`**。
`subject` 没有 `user_id` 列，在注入豁免名单里，基类不会给它加归属过滤。

★ 科目**永不物理删**：下架只把 `status` 改成 `hidden`（进隐藏库），
  已经引用它的题目不受影响——这正是二-13"被引用的行不许真删"的落点。
"""

import sqlite3

from src.data.repository.base import SCOPE_DICT, BaseRepo
from src.domain import visibility as vis


class SubjectRepo(BaseRepo):
    table = "subject"
    scope = SCOPE_DICT
    visibility_entity = vis.ENTITY_SUBJECT

    def __init__(self, conn: sqlite3.Connection, viewer_id: int | None = None):
        """`viewer_id` 收下但不用：字典表没有归属人概念，签名与其它 repo 保持一致，
        service 层才能一律 `TheRepo(conn, uid)` 地调用。"""
        super().__init__(conn, viewer_id=None)

    def options(self) -> list:
        """下拉框要的那份：只给可见的（active 且未删），按名字排。"""
        return self.rows(order="name")

    def name_map(self) -> dict:
        """`id -> 名称`。列表页显示科目名靠它，不在模板里现查库。"""
        return {row["id"]: row["name"] for row in self.options()}

    def is_usable(self, subject_id) -> bool:
        """能不能被新题引用：只认看得见的科目。下架的科目**读得到历史题、选不到新题**。"""
        return self.get(int(subject_id)) is not None

    # ------------------------------------------------------------ 管理员侧（步 23）
    # 这三个方法不改任何用户写的内容，只动字典本身；调用方必须先过 require_admin()。

    def browse(self) -> list:
        """后台列表：停用的也要看得见，所以不走可见性过滤。"""
        return self.conn.execute("SELECT * FROM subject ORDER BY name").fetchall()

    def create(self, name: str) -> int:
        """直建科目。撞名由 `uq_subject_active` 拦，调用方接住翻成人话。"""
        cursor = self.conn.execute(
            "INSERT INTO subject (name, status, created_at, updated_at)"
            " VALUES (?, 'active', datetime('now','localtime'), datetime('now','localtime'))",
            (name.strip(),))
        self.conn.commit()
        return int(cursor.lastrowid)

    def browse_one(self, subject_id: int):
        """后台按 id 取一条（含停用的）。"""
        return self.conn.execute("SELECT * FROM subject WHERE id=?", (subject_id,)).fetchone()

    def rename(self, subject_id: int, name: str) -> int:
        return self.conn.execute(
            "UPDATE subject SET name=?, updated_at=datetime('now','localtime') WHERE id=?",
            (name.strip(), subject_id)).rowcount

    def set_status(self, subject_id: int, status: str) -> int:
        """只有 active / hidden 两态——**科目没有"删除"这个动作**（永不物理删）。"""
        rows = self.conn.execute(
            "UPDATE subject SET status=?, updated_at=datetime('now','localtime') WHERE id=?",
            (status, subject_id)).rowcount
        self.conn.commit()
        return rows
