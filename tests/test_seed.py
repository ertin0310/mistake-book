"""步 5 演示：`python run.py` 之后不需要任何手工命令就有内容（方案三-21）。

★ 最值钱的是 `test_review_log_is_self_consistent`：流水账必须由 `ladder.next_state()`
  真算出来。懂 Anki 的评审一眼能看出"选了『没记住』、间隔却从 7 天涨到 15 天"，
  这种不自洽会把 S6 和 S7 一起拉低——所以把它写成断言，而不是写成一句承诺。
"""

import pytest

from config import settings
from src.data import db, seed
from src.services import auth_service

DEMO_PASSWORD = "demo12345"


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "seed.db")
    db.init_db()
    assert seed.load() is True
    conn = db.connect()
    yield conn
    conn.close()


def count(conn, table):
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_accounts_and_subjects(seeded):
    assert count(seeded, "user") == 4                       # admin / demo / stu1 / stu2
    assert count(seeded, "subject") >= 4
    assert seeded.execute("SELECT 1 FROM user WHERE role='admin'").fetchone() is not None


def test_demo_has_thirty_questions_in_the_planned_mix(seeded):
    rows = seeded.execute(
        "SELECT type, COUNT(*) AS n FROM question_bank"
        " WHERE user_id = (SELECT id FROM user WHERE username='demo') GROUP BY type").fetchall()
    mix = {row["type"]: row["n"] for row in rows}
    assert sum(mix.values()) == 30
    assert mix == {"choice": 12, "blank": 10, "essay": 8}   # 方案三-21 明写的分布


def test_review_history_covers_the_last_45_days(seeded):
    logs = count(seeded, "review_log")
    days = int(seeded.execute("SELECT COUNT(DISTINCT reviewed_on) FROM review_log")
               .fetchone()[0])
    assert logs >= 100 and days >= 30


def test_review_log_is_self_consistent(seeded):
    """归零不许让间隔变长；评完不许当天回队。两条都是算法自洽的硬条件。"""
    bad_reset = seeded.execute(
        "SELECT COUNT(*) FROM review_log"
        " WHERE rating = 4 AND interval_after > interval_before AND interval_before > 1"
    ).fetchone()[0]
    same_day = seeded.execute(
        "SELECT COUNT(*) FROM review_log WHERE due_date_after <= reviewed_on").fetchone()[0]
    assert (bad_reset, same_day) == (0, 0)


def test_queue_has_the_planned_special_cases(seeded):
    """今天到期 / 逾期 / 已爬到高级 / 作者已撤走 / 被官方收起——演示要各有一条。"""
    assert int(seeded.execute(
        "SELECT COUNT(*) FROM mistake WHERE deleted_at IS NULL").fetchone()[0]) >= 10
    assert seeded.execute("SELECT 1 FROM mistake WHERE purged_at IS NOT NULL").fetchone()
    assert seeded.execute("SELECT 1 FROM question_bank WHERE delisted_by IS NOT NULL").fetchone()
    assert seeded.execute("SELECT 1 FROM knowledge_point WHERE reviewed_by IS NULL").fetchone()


def test_private_rows_are_not_empty(seeded):
    assert count(seeded, "knowledge_note") >= 3
    assert count(seeded, "tag") >= 3
    assert count(seeded, "favorite") >= 3
    assert count(seeded, "appeal") == 2                     # 一条 open 一条 handled


def test_demo_account_can_log_in(seeded):
    user = auth_service.login(seeded, "demo", DEMO_PASSWORD)
    assert user["role"] == "member"


def test_seed_is_idempotent(seeded):
    """第二次跑必须跳过：否则用户自己刷出来的数据会被覆盖（三-21 第②条）。"""
    before = (count(seeded, "question_bank"), count(seeded, "review_log"))
    assert seed.load() is False
    assert (count(seeded, "question_bank"), count(seeded, "review_log")) == before


def test_sample_import_files_are_written(seeded, tmp_path):
    assert settings.SAMPLE_CSV_PATH.exists() and settings.SAMPLE_JSONL_PATH.exists()
    text = settings.SAMPLE_CSV_PATH.read_text(encoding="utf-8-sig")
    assert "|x|" in text and "1/2" in text                  # 坑位真的在样例里
