"""`appeal`：一张表管四类申诉与反馈（方案三-25）。

用户侧读自己的（`user` scope 强制过滤）；管理员侧的队列与收尾是**两个显式的管理员
读法**——权限在路由那一层用 `require_admin()` 判，不在这里偷偷判，这样"谁能看到全部"
这件事全站只有一处定义。
"""

from src.data.repository.base import SCOPE_USER, BaseRepo

OPEN = "open"
HANDLED = "handled"


class AppealRepo(BaseRepo):
    table = "appeal"
    scope = SCOPE_USER

    def mine(self) -> list:
        return self.rows(order="id DESC")

    def open_on(self, target_type: str, target_id) -> bool:
        """同一对象只允许一条未处理的申诉（防灌）。

        ★ 判重放在这里而不是唯一索引：一条处理完之后要允许再提。
        """
        row = self.conn.execute(
            "SELECT 1 FROM appeal WHERE user_id=? AND target_type=?"
            " AND (target_id IS ? OR target_id=?) AND status=?",
            (self.viewer_id, target_type, target_id, target_id, OPEN)).fetchone()
        return row is not None

    def submit(self, category: str, target_type: str, target_id, reason: str) -> int:
        cursor = self.conn.execute(
            "INSERT INTO appeal (user_id, category, target_type, target_id, reason, status,"
            " created_at) VALUES (:viewer, :category, :ttype, :tid, :reason, 'open',"
            " datetime('now','localtime'))",
            {"viewer": self.viewer_id, "category": category, "ttype": target_type,
             "tid": target_id, "reason": reason})
        self.conn.commit()
        return int(cursor.lastrowid)

    # ------------------------------------------------------------ 管理员专用读法

    def queue(self, status: str = OPEN) -> list:
        """后台队列：这里能看到是谁提的；被处置的作者看不到（三-25）。"""
        return self.conn.execute(
            "SELECT a.*, u.username FROM appeal a JOIN user u ON u.id = a.user_id"
            " WHERE a.status=? ORDER BY a.id DESC", (status,)).fetchall()

    def resolve(self, appeal_id: int, admin_id: int, reply: str) -> int:
        """收尾必须带回复。`AND status='open'` 保证重复点不会覆盖已写过的答复。"""
        rows = self.conn.execute(
            "UPDATE appeal SET status='handled', admin_reply=:reply, handled_by=:admin,"
            " handled_at=datetime('now','localtime') WHERE id=:id AND status='open'",
            {"reply": reply, "admin": admin_id, "id": appeal_id}).rowcount
        self.conn.commit()
        return rows
