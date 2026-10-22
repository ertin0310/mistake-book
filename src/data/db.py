"""SQLite 连接与首次建库。

两条规矩只写在这里，别处不许各写一份：

1. `PRAGMA foreign_keys = ON` 必须**每次建立连接都设**。这个开关是每条连接独立的、
   不会被数据库记住；而 schema.sql 一辈子只在首次建库时跑一次。只靠 schema 里那句
   的话，之后每个请求的连接其实都没有外键约束——我们花大力气保证的
   "被引用的行永不悬空"（二-13）当场失效。
2. 时间一律存 ISO-8601 文本，取出来还是字符串，交给 domain 的纯函数比较。
   不用 SQLite 的日期函数，避免"今天"出现第二个口径。
"""

import sqlite3
from pathlib import Path

from config import settings

SCHEMA_PATH = settings.DATA_DIR / "schema.sql"


def connect() -> sqlite3.Connection:
    """取一条连接，外键约束始终打开。"""
    settings.init_environment()
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> bool:
    """库文件不存在时执行 schema.sql。返回是否新建了库。"""
    if settings.DB_PATH.exists():
        return False
    settings.init_environment()
    sql = Path(SCHEMA_PATH).read_text(encoding="utf-8")
    conn = connect()
    try:
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()
    return True


def table_names() -> list[str]:
    """库里现有的表名（不含 SQLite 内部表）。首页用它核对 19 张是否齐。"""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        return [row["name"] for row in rows]
    finally:
        conn.close()


def row_count(table: str) -> int:
    """某表行数。table 只允许来自 table_names()，不接受用户输入。"""
    conn = connect()
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    finally:
        conn.close()


def has_any_user() -> bool:
    """`user` 表有行就说明灌过数据了，seed 靠它决定要不要跑（方案三-21）。"""
    conn = connect()
    try:
        return conn.execute("SELECT 1 FROM user LIMIT 1").fetchone() is not None
    finally:
        conn.close()
