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
