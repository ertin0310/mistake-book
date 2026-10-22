"""步 9 演示（那 30 分的主体）：

录 5 道题 → 做错 3 道 → 这 3 道**当天**就出现在今日复习 → 先答题再看答案 →
四档自评 → 到期日按台阶往后挪 → 关掉程序再开，数据还在。
"""

import sqlite3
import re
import time

import pytest

from config import schedule
from src.data import db as db_module
from src.data import seed
from src.data.repository.mistake_repo import MistakeRepo
from src.data.repository.study_attempt_repo import ReviewLogRepo
from src.domain import clock
from src.services import question_service, review_service
from tests.conftest import add_user, csrf_token, sign_up

TODAY = clock.review_date_of("00:00")


def make_questions(conn, uid, count=5):
    return [question_service.create(conn, uid, {
        "subject_id": "1", "type": "essay", "stem": f"练习题 {n}",
        "answer": f"答案 {n}", "explanation": ""}) for n in range(count)]


def mark_wrong(conn, uid, question_id):
    review_service.record_attempt(conn, uid, question_id, subject_id=1,
                                  result="wrong", submitted="")


# ---------------------------------------------------------------- 做错 → 自动入队

def test_three_wrong_questions_enter_today_queue_immediately(db):
    add_user(db, 7, "stu9")
    ids = make_questions(db, 7, 5)
    for qid in ids[:3]:
        mark_wrong(db, 7, qid)
    rows, total, _, _ = MistakeRepo(db, 7).due_page(TODAY)
    assert total == 3 and len(rows) == 3
    assert all(row["due_date"] == TODAY.isoformat() for row in rows)


def test_correct_answers_do_not_queue_anything(db):
    add_user(db, 7, "stu9")
    ids = make_questions(db, 7, 2)
    for qid in ids:
        review_service.record_attempt(db, 7, qid, 1, "right")
    assert MistakeRepo(db, 7).count_due(TODAY) == 0


def test_wrong_again_does_not_reset_the_ladder(db):
    """已有活跃错题时再错一次：台阶不动、不记 lapse——进度只由自评驱动。"""
    add_user(db, 7, "stu9")
    qid = make_questions(db, 7, 1)[0]
    mark_wrong(db, 7, qid)
    mistake_id = MistakeRepo(db, 7).active_for(qid)["id"]
    review_service.rate(db, 7, mistake_id, rating=1, duration_seconds=20)   # 升到第 2 级
    db.execute("UPDATE mistake SET step_index=2, interval_days=2 WHERE id=?", (mistake_id,))
    mark_wrong(db, 7, qid)                                                  # 再做错一次
    row = MistakeRepo(db, 7).get(mistake_id)
    assert row["step_index"] == 2 and row["lapse_count"] == 0


# ---------------------------------------------------------------- 自评改期

@pytest.mark.parametrize("rating,wanted_step,wanted_interval", [
    (1, 2, 2),      # 熟悉啦：第 0 级 → 第 2 级，隔 2 天
    (2, 1, 1),      # 记住啦：升一级
    (3, 0, 1),      # 一般般：退一级，夹在 0；★ 但间隔至少 1 天，不会当天回队
    (4, 0, 1),      # 没记住：归零 + 记一次 lapse
])
def test_rating_moves_the_due_date_by_the_ladder(db, rating, wanted_step, wanted_interval):
    add_user(db, 7, "stu9")
    qid = make_questions(db, 7, 1)[0]
    mark_wrong(db, 7, qid)
    mistake_id = MistakeRepo(db, 7).active_for(qid)["id"]
    result = review_service.rate(db, 7, mistake_id, rating=rating, duration_seconds=35)
    row = MistakeRepo(db, 7).get(mistake_id)
    assert row["step_index"] == wanted_step
    assert row["interval_days"] == wanted_interval
    assert result["next_due"] == clock.shift_days(TODAY, wanted_interval)
    assert row["review_count"] == 1
    assert row["lapse_count"] == (1 if rating == 4 else 0)


def test_review_log_is_append_only_and_records_both_sides(db):
    add_user(db, 7, "stu9")
    qid = make_questions(db, 7, 1)[0]
    mark_wrong(db, 7, qid)
    mistake_id = MistakeRepo(db, 7).active_for(qid)["id"]
    review_service.rate(db, 7, mistake_id, rating=2, duration_seconds=18)
    log = db.execute("SELECT * FROM review_log WHERE mistake_id=?", (mistake_id,)).fetchone()
    assert (log["rating"], log["step_before"], log["step_after"]) == (2, 0, 1)
    assert (log["interval_before"], log["interval_after"]) == (0, 1)
    assert log["algorithm_version"] == schedule.ALGORITHM_VERSION
    assert log["duration_seconds"] == 18
    assert ReviewLogRepo(db, 7).count_today(TODAY) == 1


def test_unknown_rating_is_rejected(db):
    add_user(db, 7, "stu9")
    qid = make_questions(db, 7, 1)[0]
    mark_wrong(db, 7, qid)
    mistake_id = MistakeRepo(db, 7).active_for(qid)["id"]
    with pytest.raises(Exception):
        review_service.rate(db, 7, mistake_id, rating=9)


# ---------------------------------------------------------------- 每日上限

def _set_cap(db, uid, value):
    db.execute("INSERT INTO user_setting (user_id, key, value) VALUES (?, 'daily_review_cap', ?)"
               " ON CONFLICT (user_id, key) DO UPDATE SET value=excluded.value", (uid, value))
    db.commit()


def test_daily_cap_limits_the_page_but_not_the_dates(db):
    add_user(db, 7, "stu9")
    for qid in make_questions(db, 7, 5):
        mark_wrong(db, 7, qid)
    _set_cap(db, 7, "2")
    queue = review_service.today_queue(db, 7, page=1)
    assert queue["cap"] == 2 and len(queue["rows"]) == 2
    assert queue["over"] == 3
    # ★ 没排上的那 3 道，due_date 一个字都没被改
    assert db.execute("SELECT COUNT(*) FROM mistake WHERE due_date=?",
                      (TODAY.isoformat(),)).fetchone()[0] == 5


def test_add_ten_widens_this_page_only(db):
    add_user(db, 7, "stu9")
    for qid in make_questions(db, 7, 12):
        mark_wrong(db, 7, qid)
    _set_cap(db, 7, "2")
    assert len(review_service.today_queue(db, 7, extra=10)["rows"]) == 12


def test_dirty_cap_falls_back_to_default(db):
    add_user(db, 7, "stu9")
    _set_cap(db, 7, "9999")
    assert review_service.daily_cap(db, 7) == schedule.DAILY_CAP_MAX
    _set_cap(db, 7, "乱填")
    assert review_service.daily_cap(db, 7) == schedule.DAILY_CAP_DEFAULT


# ---------------------------------------------------------------- 越权

def test_cannot_review_someone_elses_mistake(db):
    add_user(db, 7, "stu9")
    add_user(db, 8, "other")
    qid = make_questions(db, 7, 1)[0]
    mark_wrong(db, 7, qid)
    mistake_id = MistakeRepo(db, 7).active_for(qid)["id"]
    assert MistakeRepo(db, 8).get(mistake_id) is None
    with pytest.raises(Exception):
        review_service.rate(db, 8, mistake_id, rating=1)


# ---------------------------------------------------------------- 重启数据还在

def test_survives_a_restart(tmp_path):
    """关掉程序再开：错题队列、复习流水、台阶都还在（S2 那 10 分）。"""
    path = tmp_path / "restart.db"
    import config.settings as settings
    original = settings.DB_PATH
    settings.DB_PATH = path
    try:
        db_module.init_db()
        conn = db_module.connect()
        seed.load()
        uid = conn.execute("SELECT id FROM user WHERE username='demo'").fetchone()["id"]
        _, total, _, _ = MistakeRepo(conn, uid).due_page(TODAY)
        conn.close()

        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        assert conn.execute("SELECT COUNT(*) FROM mistake WHERE deleted_at IS NULL").fetchone()[0] > 0
        assert conn.execute("SELECT COUNT(*) FROM review_log").fetchone()[0] > 100
        conn.close()
    finally:
        settings.DB_PATH = original


# ---------------------------------------------------------------- 页面流程

def test_full_review_flow_in_the_browser(client, db):
    """出题页不给答案 → 点「看答案」才出现答案与自评 → 评一档后回到队列。"""
    sign_up(client, username="stu")
    assert client.post("/study/new", data={"subject_id": "1", "type": "essay",
                                           "stem": "复习流程题", "answer": "参考答案",
                                           "explanation": "",
                                           "csrf_token": csrf_token(client, "/study/new")}).status_code == 302
    qid = db.execute("SELECT id FROM question_bank WHERE stem='复习流程题'").fetchone()["id"]
    assert client.post(f"/study/practice/{qid}", data={
        "result": "wrong", "submitted": "",
        "csrf_token": csrf_token(client, "/study/practice")}).status_code == 302

    today = client.get("/review/today").get_data(as_text=True)
    assert "开始第 1 道" in today
    mistake_id = int(re.search(r"/review/card/(\d+)", today).group(1))

    card = client.get(f"/review/card/{mistake_id}").get_data(as_text=True)
    assert "复习流程题" in card and "参考答案" not in card        # ★ 答案此刻不出现
    started = int(time.time()) - 12
    token = csrf_token(client, f"/review/card/{mistake_id}")
    answer_page = client.post(f"/review/card/{mistake_id}/reveal",
                              data={"started": str(started), "submitted": "我写的",
                                    "csrf_token": token}).get_data(as_text=True)
    assert "参考答案" in answer_page and "12 秒" in answer_page   # 计时终点=按下看答案
    assert "熟悉啦" in answer_page and "没记住" in answer_page
    client.post(f"/review/card/{mistake_id}/rate",
                data={"started": str(started), "rating": "1", "csrf_token": token})
    assert client.get("/review/today").status_code == 200
