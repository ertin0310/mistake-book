"""隐藏库与回收站的通用仓库（方案三-24、三-12a）。

**一个类、三个动作**：`list_hidden()` / `hide()` / `restore()`，实体差异全部
从 `config/archive.py` 的注册表取。第四种东西要进库房 = 注册表加一项。

★ `restore()` 必须先做冲突预检，判据与 partial unique 索引条件**逐字一致**：
  预检查"能看见的活跃行"，数据库也只看"能看见的活跃行"，一边看全部就会出
  "提示说没有、插入却报重复"这种最难查的错。默认策略是**阻止 + 提示**，
  不做"合并后还原"——两套进度谁赢会变成解释不清的 bug。
"""

import sqlite3

from config import archive
from config.prompts import RESTORE_CONFLICT
from src.domain import clock
from src.domain.errors import RestoreConflictError, ValidationError


class ArchiveRepo:
    def __init__(self, conn: sqlite3.Connection, actor_id: int):
        self.conn = conn
        self.actor_id = actor_id

    @staticmethod
    def spec(entity: str) -> archive.EntitySpec:
        if entity not in archive.ENTITIES:
            raise ValidationError(f"未知的实体类型：{entity}")
        return archive.ENTITIES[entity]

    # ------------------------------------------------------------ 隐藏库三格

    def list_hidden(self, entity: str) -> list:
        """管理员那间库房：科目 / 知识点 / 被官方收起的题，各用自己的判据。"""
        if entity == "knowledge_point":
            where = "status IN ('hidden', 'rejected')"
        elif entity == "subject":
            where = "status = 'hidden'"
        elif entity == "question":
            where = "delisted_by IS NOT NULL"
        else:
            raise ValidationError(f"{entity} 不进隐藏库，它在用户回收站那边")
        spec = self.spec(entity)
        return self.conn.execute(
            f"SELECT * FROM {spec.table} WHERE {where} ORDER BY id DESC").fetchall()

    def hide(self, entity: str, row_id: int, note: str = "") -> None:
        """下架/收起。**题目只写 `delisted_by`，绝不写别人的 `deleted_at`**（三-23）。"""
        spec = self.spec(entity)
        if entity == "question":
            self.conn.execute(
                "UPDATE question_bank SET delisted_by=:admin, delist_note=:note"
                " WHERE id=:id AND delisted_by IS NULL",
                {"admin": self.actor_id, "note": note, "id": row_id})
        elif entity in ("knowledge_point", "subject"):
            self.conn.execute(f"UPDATE {spec.table} SET status='hidden',"
                              f" updated_at=datetime('now','localtime') WHERE id=:id",
                              {"id": row_id})
        else:
            raise ValidationError(f"{entity} 不能用下架，请走回收站")
        self.conn.commit()

    def restore(self, entity: str, row_id: int) -> None:
        """从隐藏库放回。撞名字的先拦下，不硬来。"""
        spec = self.spec(entity)
        row = self.conn.execute(f"SELECT * FROM {spec.table} WHERE id=?", (row_id,)).fetchone()
        if row is None:
            raise ValidationError("这条记录不在了")
        self._reject_conflict(spec, row)
        if entity == "question":
            self.conn.execute("UPDATE question_bank SET delisted_by=NULL, delist_note=NULL"
                              " WHERE id=?", (row_id,))
        elif entity == "knowledge_point":
            self.conn.execute("UPDATE knowledge_point SET status='approved',"
                              " updated_at=datetime('now','localtime') WHERE id=?", (row_id,))
        else:
            self.conn.execute("UPDATE subject SET status='active',"
                              " updated_at=datetime('now','localtime') WHERE id=?", (row_id,))
        self.conn.commit()

    # ------------------------------------------------------------ 冲突预检

    def _reject_conflict(self, spec: archive.EntitySpec, row) -> None:
        if not spec.unique_columns:
            return
        same = " AND ".join(f"{column} = :{column}" for column in spec.unique_columns)
        params = {column: row[column] for column in spec.unique_columns}
        clash = self.conn.execute(
            f"SELECT 1 FROM {spec.table} WHERE {same} AND {spec.in_use_where}"
            f" AND id <> :id LIMIT 1", dict(params, id=row["id"])).fetchone()
        if clash is not None:
            raise RestoreConflictError(RESTORE_CONFLICT[spec.conflict_prompt_key])

    # ------------------------------------------------------------ 用户回收站

    def list_trash(self, entity: str, user_id: int) -> list:
        """只看这个人自己扔进去的。

        有 `deleted_by` 列的表（题目、错题）按它过滤——官方收起和用户删除是两回事；
        没有这一列的表（标签）本来就只属于一个人，按 `user_id` 即可。
        """
        spec = self.spec(entity)
        columns = {row[1] for row in self.conn.execute(f"PRAGMA table_info({spec.table})")}
        if "deleted_by" in columns:
            who, params = "deleted_by=:user", {"user": user_id}
        else:
            who, params = f"{spec.owner_column}=:user", {"user": user_id}
        return self.conn.execute(
            f"SELECT * FROM {spec.table} WHERE {spec.deleted_column} IS NOT NULL AND {who}"
            f" ORDER BY {spec.deleted_column} DESC", params).fetchall()

    def restore_from_trash(self, entity: str, row_id: int, user_id: int) -> None:
        spec = self.spec(entity)
        columns = {row[1] for row in self.conn.execute(f"PRAGMA table_info({spec.table})")}
        if "deleted_by" in columns:
            row = self.conn.execute(
                f"SELECT * FROM {spec.table} WHERE id=? AND deleted_by=?",
                (row_id, user_id)).fetchone()
            clear = f"UPDATE {spec.table} SET {spec.deleted_column}=NULL, deleted_by=NULL WHERE id=?"
        else:
            row = self.conn.execute(
                f"SELECT * FROM {spec.table} WHERE id=? AND {spec.owner_column}=?",
                (row_id, user_id)).fetchone()
            clear = f"UPDATE {spec.table} SET {spec.deleted_column}=NULL WHERE id=?"
        if row is None:
            raise ValidationError("这条不在你的回收站里")
        self._reject_conflict(spec, row)
        self.conn.execute(clear, (row_id,))
        self.conn.commit()

    def purge_expired(self) -> int:
        """30 天懒清理（查询时顺手做，不依赖后台常驻进程）。

        ★ 分两类：`mistake` **永不物理删**（`review_log.mistake_id` 指着它），
          到期只打 `purged_at` 做"过期封存"；`tag` 没人引用了，可以连 `tag_link`
          一起真删。
        """
        expired = self.conn.execute(
            "SELECT id FROM mistake WHERE deleted_at IS NOT NULL AND purged_at IS NULL"
            " AND deleted_at <= datetime('now', '-30 days')").fetchall()
        for row in expired:
            self.conn.execute("UPDATE mistake SET purged_at=datetime('now','localtime')"
                              " WHERE id=?", (row["id"],))
        tags = self.conn.execute(
            "SELECT id FROM tag WHERE deleted_at IS NOT NULL"
            " AND deleted_at <= datetime('now', '-30 days')").fetchall()
        for row in tags:
            self.conn.execute("DELETE FROM tag_link WHERE tag_id=?", (row["id"],))
            self.conn.execute("DELETE FROM tag WHERE id=?", (row["id"],))
        self.conn.commit()
        return len(expired) + len(tags)

    def count_expired(self) -> int:
        """回收站底部那句"已过期 N 条"——一次 COUNT，不建页面、不落新状态。"""
        return int(self.conn.execute(
            "SELECT COUNT(*) FROM mistake WHERE purged_at IS NOT NULL").fetchone()[0])
