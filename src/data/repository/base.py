"""repository 基类：四种可见性 scope + 全站唯一的 `paginate()`（方案二-5、二-11、二-15）。

**这一步是"封装"最实的载体**：后面所有 repo 只继承这里，任何 repo 都不许自己写
`WHERE user_id = ?`。理由不是省字，是"过滤规则一旦散开，就会有一个页面忘了过滤"——
那种 bug 不报错，只是多显示几条别人的数据，是最难查的一类。

★ 防冒名签**不在这里**（已挪到步 4，跟第一个真表单一起验）。
★ 还原冲突预检的判据在 `visibility.occupies_name()`，本文件只留 SQL 侧的对应物，
  真正接上在步 11。
"""

import re
import sqlite3
from dataclasses import dataclass

from config import settings
from src.domain import visibility as vis

# ---------------------------------------------------------------- 四种 scope

SCOPE_USER = "user"        # 强制 user_id = 看的人：题目私有数据、笔记、记录、收藏、标签
SCOPE_DICT = "dict"        # 所有人只读，写走 require_admin()：科目
SCOPE_POLICY = "policy"    # 按 is_visible() 判：知识点
SCOPE_NAMED = "named"      # 只许两个具名读法，禁止混用一条 SQL：question_bank 等

# 注入豁免名单（二-11）：这些表**没有** user_id 列，任何 scope 都不许往它们身上注入。
# `question_bank.user_id` 可为 NULL（官方题归属软件本身），所以它根本不走 SCOPE_USER，
# 只走 SCOPE_NAMED 的 mine / shared_pool 两个读法——见步 8。
# `user_agreement` 不在名单里：它真的有 `user_id` 列，而且每一行只属于一个人
# （"谁在哪一版上点过同意"是私有记录），所以它走 `SCOPE_USER`。
NO_USER_INJECTION = frozenset({"subject", "agreement", "user"})

# 可见性判据的 SQL 版，与 `src/domain/visibility.py` 里三个 Python 判据一一对应。
#
# ★ 为什么同一条规则要写两遍：过滤必须发生在 SQL 里（否则翻页的总数就不对，
#   还会把不该读到的行取进内存），而"规则只有一份"这句话只能靠测试来保证——
#   `tests/test_visibility_policy.py` 穷举所有取值组合，逐格比对 SQL 判据与
#   Python 判据，两边一旦漂移就红。
VISIBILITY_CLAUSES: dict[str, str] = {
    vis.ENTITY_KNOWLEDGE: (
        "deleted_at IS NULL AND (status = :vis_active"
        " OR (created_by_user_id IS NOT NULL AND created_by_user_id = :viewer))"),
    vis.ENTITY_SUBJECT: (
        "deleted_at IS NULL AND status = :vis_active"),
    vis.ENTITY_QUESTION: (
        "deleted_at IS NULL AND delisted_by IS NULL"
        " AND (visibility = :vis_shared OR user_id = :viewer)"),
}

_ACTIVE_VALUES = {
    vis.ENTITY_KNOWLEDGE: vis.KP_ACTIVE,
    vis.ENTITY_SUBJECT: vis.SUBJECT_ACTIVE,
}

_ORDER_ITEM = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)(\s+(ASC|DESC))?\s*$", re.IGNORECASE)


def _safe_order(order: str, allowed: set[str]) -> str:
    """ORDER BY 是唯一不能参数化的地方，所以只认白名单形状（二-11）。

    两道闸：形状必须是"列名 [ASC|DESC]"，列名还必须真的存在于这张表。
    这里拼的一律是代码里写死的字面量；一旦有人把用户输入传进来，
    当场炸，而不是悄悄变成注入点。
    """
    items = []
    for part in (order or "id").split(","):
        match = _ORDER_ITEM.match(part)
        if not match or match.group(1) not in allowed:
            raise ValueError(f"非法的排序写法：{part!r}")
        direction = (match.group(3) or "ASC").upper()
        items.append(f"{match.group(1)} {direction}")
    return ", ".join(items)


@dataclass(frozen=True)
class Page:
    """一页数据。全站列表只认这一个形状（二-15）。"""

    items: list
    page: int
    page_size: int
    total: int
    total_pages: int


class BaseRepo:
    """一张表一个子类，声明 `table` + `scope` 就得到全套过滤。

    `viewer_id` 是"谁在看"，由 service 层从会话里取，**绝不允许从表单/URL 传进来**。
    """

    table: str = ""
    scope: str = SCOPE_USER
    visibility_entity: str | None = None   # SCOPE_POLICY 必填；SCOPE_DICT 可填（科目就填 subject）
    named_reads: tuple[str, ...] = ()      # SCOPE_NAMED 必填：这张表允许哪几个具名读法
    columns_cache: dict[str, set[str]] = {}

    def __init__(self, conn: sqlite3.Connection, viewer_id: int | None = None):
        if not self.table:
            raise ValueError("repo 必须声明 table")
        if self.scope == SCOPE_NAMED and not self.named_reads:
            raise ValueError("named scope 必须声明 named_reads，且不许用基类的通用读法")
        if self.scope == SCOPE_POLICY and not self.visibility_entity:
            raise ValueError("policy scope 必须声明 visibility_entity")
        self.conn = conn
        self.viewer_id = viewer_id
        self._columns = self._table_columns(conn)
        self._check_declaration()

    # ------------------------------------------------------------ 声明自检

    def _table_columns(self, conn: sqlite3.Connection) -> set[str]:
        cached = BaseRepo.columns_cache.get(self.table)
        if cached is None:
            cached = {row[1] for row in conn.execute(f"PRAGMA table_info({self.table})")}
            if not cached:
                raise ValueError(f"表不存在：{self.table}")
            BaseRepo.columns_cache[self.table] = cached
        return cached

    def _check_declaration(self) -> None:
        """声明与实际表结构对不上要立刻报错，不许留到运行期静默失效。"""
        if self.scope == SCOPE_USER:
            if self.table in NO_USER_INJECTION:
                raise ValueError(f"{self.table} 在注入豁免名单里，不许声明 user scope")
            if "user_id" not in self._columns:
                raise ValueError(f"{self.table} 没有 user_id 列，用不了 user scope")
        if self.visibility_entity:
            clause = VISIBILITY_CLAUSES[self.visibility_entity]
            for column in re.findall(r"\b([a-z_]+)\s*(?:IS|=|IN)", clause):
                if column not in self._columns and not column.startswith("vis_"):
                    raise ValueError(f"{self.table} 没有列 {column}，可见性判据对不上")

    # ------------------------------------------------------------ scope 过滤

    def _scope_clause(self) -> tuple[str, dict]:
        """返回这一层强制附加的 WHERE 片段与参数。子类**不能**覆盖它。"""
        params: dict = {}
        clauses = []
        if self.scope == SCOPE_USER:
            if self.viewer_id is None:
                raise ValueError(f"{self.table} 按 user scope 读必须给 viewer_id")
            clauses.append("user_id = :viewer")
            params["viewer"] = self.viewer_id
        if self.visibility_entity:
            clauses.append(VISIBILITY_CLAUSES[self.visibility_entity])
            if self.visibility_entity in _ACTIVE_VALUES:
                params["vis_active"] = _ACTIVE_VALUES[self.visibility_entity]
            else:
                params["vis_shared"] = vis.SHARED
            params.setdefault("viewer", self.viewer_id)
        return (" AND ".join(f"({c})" for c in clauses) if clauses else "1", params)

    def _build_where(self, extra_where: str, extra_params: dict | None) -> tuple[str, dict]:
        self._reject_generic_read()
        clause, params = self._scope_clause()
        params.update(extra_params or {})
        if extra_where:
            clause = f"({clause}) AND ({extra_where})"
        return clause, params

    # ------------------------------------------------------------ 读

    def _reject_generic_read(self) -> None:
        """named 的表不许走通用读法（二-5）：一条 SQL 同时捞"我的"和"共享池"
        会把两种语义混在一起，步 8 之后一定出错，所以在入口就堵掉。"""
        if self.scope == SCOPE_NAMED:
            raise ValueError(f"{self.table} 只允许具名读法：{list(self.named_reads)}")

    def read_named(self, read_name: str, where: str = "", params: dict | None = None,
                   order: str = "id", page: int = 1, page_size: int | None = None) -> Page:
        """named 表唯一的读出口：子类只能从这里读，且必须先声明读法名字。

        与 `paginate()` 共用同一套越界回落规则——翻页这件事全站只有一份。
        """
        if read_name not in self.named_reads:
            raise ValueError(f"{self.table} 没有登记过读法 {read_name!r}")
        params = dict(params or {})
        params.setdefault("viewer", self.viewer_id)
        clause = where or "1"
        total = int(self.conn.execute(
            f"SELECT COUNT(*) FROM {self.table} WHERE {clause}", params).fetchone()[0])
        size = max(1, int(page_size or settings.PAGE_SIZE))
        total_pages = max(1, -(-total // size))
        current = min(max(1, int(page or 1)), total_pages)
        bound = dict(params, _limit=size, _offset=(current - 1) * size)
        items = self.conn.execute(
            f"SELECT * FROM {self.table} WHERE {clause} ORDER BY {_safe_order(order, self._columns)}"
            f" LIMIT :_limit OFFSET :_offset", bound).fetchall()
        return Page(items=items, page=current, page_size=size, total=total, total_pages=total_pages)

    def get(self, row_id: int, columns: str = "*"):
        """按 id 取一行，**取不到就是 None**——别人的行和不存在是同一件事（方案七-1 的 404）。"""
        self._reject_generic_read()
        clause, params = self._scope_clause()
        params["id"] = row_id
        sql = f"SELECT {columns} FROM {self.table} WHERE ({clause}) AND id = :id"
        return self.conn.execute(sql, params).fetchone()

    def rows(self, where: str = "", params: dict | None = None, order: str = "id",
             limit: int | None = None, columns: str = "*") -> list:
        clause, bound = self._build_where(where, params)
        sql = f"SELECT {columns} FROM {self.table} WHERE {clause} ORDER BY {_safe_order(order, self._columns)}"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        return self.conn.execute(sql, bound).fetchall()

    def count(self, where: str = "", params: dict | None = None) -> int:
        clause, bound = self._build_where(where, params)
        row = self.conn.execute(f"SELECT COUNT(*) FROM {self.table} WHERE {clause}", bound).fetchone()
        return int(row[0])

    def paginate(self, where: str = "", params: dict | None = None, order: str = "id",
                 page: int = 1, page_size: int | None = None, columns: str = "*") -> Page:
        """全站唯一的翻页函数（二-15 ★）。

        每页默认 20 条（`settings.PAGE_SIZE`）；**页码越界回落到最后一页**，
        不报错也不给空页——列表页上"第 999 页"是用户手输或旧链接，空页会让人
        以为数据被删了。★ 「今日复习」也走这里：上限管今天排多少道，
        翻页管一屏看多少道，两件事不混（三-11）。
        """
        size = max(1, int(page_size or settings.PAGE_SIZE))
        total = self.count(where, params)
        total_pages = max(1, -(-total // size))
        current = min(max(1, int(page or 1)), total_pages)
        items = self._slice(size, current, where, params, order, columns)
        return Page(items=items, page=current, page_size=size, total=total, total_pages=total_pages)

    def _slice(self, size: int, current: int, where: str, params: dict | None,
               order: str, columns: str) -> list:
        clause, bound = self._build_where(where, params)
        bound = dict(bound, _limit=size, _offset=(current - 1) * size)
        sql = (f"SELECT {columns} FROM {self.table} WHERE {clause}"
               f" ORDER BY {_safe_order(order, self._columns)} LIMIT :_limit OFFSET :_offset")
        return self.conn.execute(sql, bound).fetchall()

    # ------------------------------------------------------------ 写

    def create(self, **columns) -> int:
        """插入一行，user scope 的表**自动带上归属人**，子类想漏也漏不掉。

        dict / policy 的写操作不在这一层放开口子：它们要 `require_admin()`，
        那是步 4 的 `config/permissions.py`。在那之前调用就是报错，
        而不是"先写着，将来再说"。
        """
        if self.scope != SCOPE_USER:
            raise ValueError(f"{self.table} 的写操作要等步 4 的 require_admin()，本步不开口子")
        bad = set(columns) - self._columns - {"user_id"}
        if bad:
            raise ValueError(f"{self.table} 没有这些列：{sorted(bad)}")
        values = dict(columns)
        if "user_id" in self._columns:
            if self.viewer_id is None:
                raise ValueError(f"写 {self.table} 必须给 viewer_id")
            values["user_id"] = self.viewer_id      # ★ 覆盖，不接受调用方传进来的别人的 id
        names = ", ".join(values)
        marks = ", ".join(f":{n}" for n in values)
        cursor = self.conn.execute(
            f"INSERT INTO {self.table} ({names}) VALUES ({marks})", values)
        return int(cursor.lastrowid)
