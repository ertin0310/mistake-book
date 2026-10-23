"""`knowledge_point`（`policy` scope，方案三-6）。

步 12 的导入预检就要用它，所以先建最小三件：查可用名字、找一条可用的、提交一条。
完整的提交即入池 + 重提回待审在步 18。

★ 查重一律按**归一化名**，且**只算 `is_visible()` 通过的行**——
  被驳回/下架的不占名字，否则会出"叫乙去选用一条只有甲看得见的记录"那种死局。
"""

import sqlite3

from src.data.repository.base import SCOPE_POLICY, BaseRepo
from src.domain import normalize, visibility as vis

# "能用"的定义只写这一份：状态是 approved 且没软删。它与"能不能看见"是两回事——
# 作者看得见自己被驳回的那条，但那条绝不能被他当成"已经有了"来复用（三-6 的死局）。
USABLE = "status = 'approved' AND deleted_at IS NULL"


class KnowledgeRepo(BaseRepo):
    table = "knowledge_point"
    scope = SCOPE_POLICY
    visibility_entity = vis.ENTITY_KNOWLEDGE

    def __init__(self, conn: sqlite3.Connection, viewer_id: int | None = None):
        super().__init__(conn, viewer_id)

    def usable_names(self) -> set:
        """当前看得见的知识点名字集合，元素是 `(subject_id, 归一化名)`。"""
        return {(row["subject_id"], row["name_normalized"]) for row in self.rows(where=USABLE)}

    def find_usable(self, subject_id: int, name: str):
        """在"能用"的行里按归一化名找：既要是 approved 的活行，也要当前这个人看得见。

        ★ 两个条件缺一不可：少后者，别人那条同名但已下架/驳回的行会先被捞上来，
          刚建好的知识点挂不上题；少前者，作者本人会撞回自己那条被驳回的行，
          页面提示"已经有了，去选用一条"，可那条是死的，他永远改不回来。
        """
        rows = self.rows(where="(subject_id = :subject_id AND name_normalized = :clean)"
                              f" AND ({USABLE})",
                         params={"subject_id": subject_id,
                                 "clean": normalize.normalize_name(name)})
        return rows[0]["id"] if rows else None

    def names_by_question(self, question_id: int) -> list:
        """这道题挂了哪些还在用池子里的知识点名（导出题目清单、以后详情页都靠它）。"""
        return [row["name"] for row in self.conn.execute(
            "SELECT kp.name FROM question_knowledge_point link"
            " JOIN knowledge_point kp ON kp.id = link.knowledge_point_id"
            " WHERE link.question_id = :q AND kp.status = 'approved' AND kp.deleted_at IS NULL"
            " ORDER BY kp.id", {"q": question_id})]

    def submit(self, user_id: int, subject_id: int, name: str) -> int:
        """提交即 `approved` 所有人可用；`reviewed_by` 留空 = 进审核队列（三-6）。"""
        clean = normalize.normalize_name(name)
        cursor = self.conn.execute(
            "INSERT INTO knowledge_point (subject_id, name, name_normalized, status,"
            " created_by_user_id, created_at, updated_at)"
            " VALUES (?, ?, ?, 'approved', ?, datetime('now','localtime'),"
            " datetime('now','localtime'))",
            (subject_id, name.strip(), clean, user_id))
        self.conn.commit()
        return int(cursor.lastrowid)
