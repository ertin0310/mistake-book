"""让 `tests/` 里能直接 `from src... import ...` 和 `from config import ...`。

pytest 默认只把测试文件所在目录放进 sys.path，项目根不在里面，
所以不写这个文件，第一步就会以"找不到模块"收场。

第 3 步起还需要一个**内存库**：可见性过滤必须在真 SQL 上验才作数——
用假对象 mock 出来的测试只能证明"我调了那个函数"，证明不了"SQL 真把别人的行滤掉了"。
"""

import re
import sqlite3
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SCHEMA_PATH = PROJECT_ROOT / "src" / "data" / "schema.sql"
STAMP = "2026-10-21 10:00:00"


@pytest.fixture
def mem_db():
    """跑过 schema.sql 的内存库，外键开关按 `db.connect()` 的同一口径打开。"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    yield conn
    conn.close()


def add_user(conn, user_id, username, role="member"):
    conn.execute("INSERT INTO user (id, username, password_hash, role, created_at)"
                 " VALUES (?, ?, ?, ?, ?)", (user_id, username, "x", role, STAMP))
    return user_id


def uid_of(db, username):
    """注册走的是自增主键，测试里别硬写 id——第 6 个用户不一定是 6。"""
    return db.execute("SELECT id FROM user WHERE username=?", (username,)).fetchone()["id"]


def add_subject(conn, subject_id, name, status="active", deleted_at=None):
    conn.execute("INSERT INTO subject (id, name, status, created_at, updated_at, deleted_at)"
                 " VALUES (?, ?, ?, ?, ?, ?)",
                 (subject_id, name, status, STAMP, STAMP, deleted_at))
    return subject_id


def add_knowledge(conn, kp_id, subject_id, name, created_by, status="approved", deleted_at=None):
    conn.execute("INSERT INTO knowledge_point (id, subject_id, name, name_normalized, status,"
                 " created_by_user_id, created_at, updated_at, deleted_at)"
                 " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (kp_id, subject_id, name, name, status, created_by, STAMP, STAMP, deleted_at))
    return kp_id


def add_question(conn, question_id, owner_id, subject_id=1, visibility="private",
                 deleted_at=None, delisted_by=None):
    conn.execute("INSERT INTO question_bank (id, user_id, subject_id, type, stem, options_json,"
                 " answer_json, explanation, source, visibility, created_at, updated_at,"
                 " deleted_at, delisted_by) VALUES (?, ?, ?, 'essay', ?, '[]',"
                 " '{\"text\":\"参考答案\"}', '', 'manual', ?, ?, ?, ?, ?)",
                 (question_id, owner_id, subject_id, f"题干 {question_id}", visibility,
                  STAMP, STAMP, deleted_at, delisted_by))
    return question_id


def add_mistake(conn, user_id, question_id, due_date="2026-10-21", deleted_at=None):
    return conn.execute("INSERT INTO mistake (user_id, question_id, entry_reason, step_index,"
                        " interval_days, due_date, review_count, lapse_count, created_at,"
                        " updated_at, deleted_at) VALUES (?, ?, 'marked_wrong', 0, 0, ?, 0, 0,"
                        " ?, ?, ?)",
                        (user_id, question_id, due_date, STAMP, STAMP, deleted_at)).lastrowid


def add_review_log(conn, user_id, mistake_id, rating=2):
    """手工落一笔复习流水（走 service 那条链在 `test_review_cycle.py` 里另有用例）。"""
    return conn.execute(
        "INSERT INTO review_log (user_id, mistake_id, reviewed_on, reviewed_at, rating,"
        " rating_source, duration_seconds, algorithm_version, interval_before,"
        " interval_after, due_date_before, due_date_after, step_before, step_after)"
        " VALUES (?, ?, '2026-10-21', '2026-10-21 10:00:00', ?, 'user_override', 30, 'ladder-1',"
        " 0, 1, '2026-10-21', '2026-10-22', 0, 1)", (user_id, mistake_id, rating)).lastrowid


@pytest.fixture
def db(mem_db):
    """两个用户 + 一活一停的科目 + 把每种可见性各摆一行。

    刻意让每种情形都恰好有一行：任何一侧漏过滤就会立刻多一条或少一条，
    而不是碰巧对上。
    """
    # 协议正文：`user_agreement.version` 外键指向 `agreement.version`，
    # 所以"同意"之前这一版得先存在于库里——测试只摆版本行，正文由 seed 负责。
    from config import agreement as agreement_config
    for seq, (key, version) in enumerate(agreement_config.CURRENT.items(), start=1):
        mem_db.execute("INSERT INTO agreement (version, seq, title, content, effective_from,"
                       " created_at) VALUES (?, ?, ?, ?, '2026-10-01', ?)",
                       (version, seq, agreement_config.KINDS[key].label, "测试用正文", STAMP))

    add_user(mem_db, 1, "u1")
    add_user(mem_db, 2, "u2")
    add_user(mem_db, 9, "admin", role="admin")
    add_subject(mem_db, 1, "数学")
    add_subject(mem_db, 2, "英语", status="hidden")

    add_knowledge(mem_db, 1, 1, "牛顿定律", created_by=1)                     # 通过：人人可见
    add_knowledge(mem_db, 2, 1, "泰勒公式", created_by=1, status="rejected")  # 驳回：只有作者
    add_knowledge(mem_db, 3, 1, "冲量定理", created_by=1, status="hidden")    # 下架：只有作者
    add_knowledge(mem_db, 4, 1, "傅里叶级数", created_by=2)                   # 别人的通过行
    add_knowledge(mem_db, 5, 1, "已删知识点", created_by=1, deleted_at=STAMP)  # 作者也不该看见

    add_question(mem_db, 1, owner_id=1, visibility="private")                    # 自己私有
    add_question(mem_db, 2, owner_id=1, visibility="shared")                     # 自己已共享
    add_question(mem_db, 3, owner_id=1, visibility="shared", delisted_by=9)      # 被官方收起
    add_question(mem_db, 4, owner_id=2, visibility="shared")                     # 别人共享的
    add_question(mem_db, 5, owner_id=2, visibility="private")                    # 别人私有的
    add_question(mem_db, 6, owner_id=None, visibility="shared")                  # 官方题
    add_question(mem_db, 7, owner_id=1, visibility="private", deleted_at=STAMP)  # 自己软删
    mem_db.commit()
    return mem_db


class KeepOpen:
    """把 fixture 的内存连接借给一次请求用，但别让 teardown 把它关掉。"""

    def __init__(self, conn):
        self._conn = conn

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._conn, name)


@pytest.fixture
def client(db, monkeypatch):
    """跑真 Flask 应用的测试客户端：路由、会话、防冒名签、模板渲染全都真的走一遍。"""
    import src.app as app_module

    monkeypatch.setattr(app_module.db, "connect", lambda: KeepOpen(db))
    monkeypatch.setattr(app_module.db, "init_db", lambda: None)
    monkeypatch.setattr(app_module.db, "has_any_user", lambda: True)   # 别在测试库里灌 seed
    app = app_module.create_app()
    app.config["TESTING"] = True
    return app.test_client()


def sign_up(client, username="stu", password="goodpass123"):
    """注册 → 登录 → 同意《站点协议》，和真人第一次进来走的顺序一模一样。

    协议这道门是登录后第一站（三-16a），所以每个页面级用例都得先过它——
    这里统一过，免得二十个文件各写一遍、漏一个就全线 302。
    """
    token = csrf_token(client, "/register")
    response = client.post("/register", data={"username": username, "password": password,
                                              "confirm": password, "csrf_token": token})
    agree_to_terms(client)
    return response


def agree_to_terms(client):
    """跟着门跳到协议页并点「我已阅读并同意」；已经同意过就直接返回。"""
    gate = client.get("/")
    location = gate.headers.get("Location", "")
    if "/agreement/" not in location:
        return None
    version = location.split("/agreement/")[1].split("?")[0]
    return client.post(f"/agreement/{version}/accept",
                       data={"next": "/study/", "csrf_token": csrf_token(client, location)})


def csrf_token(client, path):
    match = TOKEN_IN_HTML.search(client.get(path).get_data(as_text=True))
    assert match, f"{path} 页面里没有防冒名签那一行"
    return match.group(1)


TOKEN_IN_HTML = re.compile(r'name="csrf_token" value="([^"]+)"')
