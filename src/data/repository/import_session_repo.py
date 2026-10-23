"""导入会话仓库：`import_session` + `import_session_row`（方案三-14）。

两步式导入要能"预览完再确认"，所以预览结果先整批落成草稿行；
用户中途走掉也不丢——批次停在 `pending`，回来一键重跑，不重填不重传。
"""

import json

from src.data.repository.base import SCOPE_USER, BaseRepo


class ImportSessionRepo(BaseRepo):
    table = "import_session"
    scope = SCOPE_USER

    def start(self, target: str, fmt: str, filename: str) -> int:
        return int(self.conn.execute(
            "INSERT INTO import_session (user_id, target, format, source_filename, owner,"
            " default_visibility, status, created_at) VALUES (:viewer, :target, :format,"
            " :filename, 'self', 'private', 'pending', datetime('now','localtime'))",
            {"viewer": self.viewer_id, "target": target, "format": fmt,
             "filename": filename}).lastrowid)

    def add_rows(self, session_id: int, rows) -> None:
        """ok 的行带将要写入的内容，blocked 的行带原因（含行号已经在那儿了）。"""
        self.conn.executemany(
            "INSERT INTO import_session_row (session_id, line_no, payload_json, error_code,"
            " error_msg, status) VALUES (?, ?, ?, ?, ?, ?)",
            [(session_id, row.line, json.dumps(row.payload, ensure_ascii=False),
              "" if row.ok else "invalid", "；".join(row.errors),
              "ok" if row.ok else "blocked") for row in rows])
        self.conn.commit()

    def finish(self, session_id: int, status: str) -> None:
        self.conn.execute(
            "UPDATE import_session SET status=? WHERE id=? AND user_id=?",
            (status, session_id, self.viewer_id))
        self.conn.commit()

    def get_session(self, session_id: int):
        """按 id 取自己那一批。别人报来的批次号一律取不到（确认入库前先问这个）。"""
        return self.conn.execute(
            "SELECT * FROM import_session WHERE id=? AND user_id=?",
            (session_id, self.viewer_id)).fetchone()

    def rows_of(self, session_id: int) -> list:
        return self.conn.execute(
            "SELECT * FROM import_session_row WHERE session_id=? ORDER BY line_no",
            (session_id,)).fetchall()

    def pending_for(self, target: str) -> list:
        """上次那批还在不在——回来能接着确认。"""
        return self.conn.execute(
            "SELECT * FROM import_session WHERE user_id=:viewer AND target=:target"
            " AND status='pending' ORDER BY id DESC",
            {"viewer": self.viewer_id, "target": target}).fetchall()
