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

    def usable_rows(self) -> list:
        """能用的那些行，整份拿出来（统计页要在内存里反复查同一批名字）。"""
        return self.rows(where=USABLE)

    def points_of_question(self, question_id: int) -> list:
        """这道题挂着哪几个知识点（返回行，含 `subject_id` 与归一化名，调用方自己筛）。"""
        return self.conn.execute(
            f"SELECT kp.* FROM knowledge_point kp"
            f" JOIN question_knowledge_point link ON link.knowledge_point_id = kp.id"
            f" WHERE link.question_id = :q AND {USABLE} ORDER BY kp.id", {"q": question_id}).fetchall()

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

    # ------------------------------------------------------------ 步 18 补的读法与写法

    def browse(self, subject_id, page: int = 1):
        """浏览页：只看当前能用的那些，按名字排；`subject_id=None` 表示全部科目。"""
        where = f"({USABLE})"
        params = {}
        if subject_id:
            where = f"(subject_id = :subject) AND {where}"
            params["subject"] = int(subject_id)
        return self.paginate(where=where, params=params, order="name", page=page)

    def same_name(self, subject_id: int, name: str) -> list:
        """同科目下同名（按归一化名）的**能用**行——就是"已经有了"要列给用户看的那几条。"""
        return self.rows(where=f"(subject_id = :subject AND name_normalized = :clean) AND ({USABLE})",
                         params={"subject": subject_id, "clean": normalize.normalize_name(name)},
                         order="name")

    def submitted_by(self, user_id: int) -> list:
        """我提交过的知识点，含被驳回与下架的（这两档只有作者自己看得见，靠 policy 口径）。"""
        return self.rows(where="created_by_user_id = :who", params={"who": user_id},
                         order="id DESC")

    def pending(self) -> list:
        """审核队列 = `reviewed_by IS NULL`（三-6）；提交即入池，所以队列与可用性互不矛盾。"""
        return self.rows(where=f"reviewed_by IS NULL AND ({USABLE})", order="id")

    def resubmit(self, point_id: int, user_id: int, name: str) -> bool:
        """作者改名重提：回到 `approved` 并把审核痕迹清空 → 重新排队待审（三-6）。

        返回是否真改到。`WHERE created_by_user_id` 保证只能动自己提交的那条，
        改别人的 = 改不到，调用方据此给 404。
        """
        clean = normalize.normalize_name(name)
        cursor = self.conn.execute(
            "UPDATE knowledge_point SET name=?, name_normalized=?, status='approved',"
            " reviewed_by=NULL, reviewed_at=NULL, review_note=?"
            " WHERE id=? AND created_by_user_id=?",
            (name.strip(), clean, None, point_id, user_id))
        self.conn.commit()
        return cursor.rowcount > 0

    def reject(self, point_id: int, admin_id: int, note: str) -> bool:
        """驳回：状态给作者留着原因，行不删（步 23 后台页面用的就是它）。"""
        cursor = self.conn.execute(
            "UPDATE knowledge_point SET status='rejected', reviewed_by=:admin,"
            " reviewed_at=datetime('now','localtime'), review_note=:note WHERE id=:id",
            {"admin": admin_id, "note": note, "id": point_id})
        self.conn.commit()
        return cursor.rowcount > 0
