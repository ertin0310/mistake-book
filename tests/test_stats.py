"""步 15 演示：统计四图。

这层的价值全在口径上，所以每条用例都盯着"数字是怎么来的"：
掌握度只看 `step_index`（不新建字段）、热力图按复习日且空格也出格、
薄弱排行两个错源同权、已下架的知识点不参与也不报错。
"""

from config import schedule
from src.data.repository.knowledge_repo import KnowledgeRepo
from src.data.repository.mistake_repo import MistakeRepo
from src.domain import clock
from src.services import stats_service
from tests.conftest import (STAMP, add_knowledge, add_mistake, add_question, add_review_log,
                           add_subject, add_user)

REVIEW_LOG = ("INSERT INTO review_log (user_id, mistake_id, reviewed_on, reviewed_at, rating,"
              " rating_source, duration_seconds, algorithm_version, interval_before,"
              " interval_after, due_date_before, due_date_after, step_before, step_after)"
              " VALUES (:u, :m, :on, :at, :r, 'user_override', 30, 'ladder-1', 0, 1, :on, :on, 0, 1)")
ATTEMPT = ("INSERT INTO study_attempt (user_id, question_id, subject_id, result, grade_source,"
           " answer_submitted, recorded_on, created_at)"
           " VALUES (:u, :q, 1, :result, 'manual', '', :on, :stamp)")


def link(conn, question_id, point_id, user_id=7):
    conn.execute("INSERT INTO question_knowledge_point (question_id, knowledge_point_id, user_id,"
                 " created_at) VALUES (?, ?, ?, ?)", (question_id, point_id, user_id, STAMP))


def one_review(conn, mistake_id, day, rating=2, user_id=7):
    conn.execute(REVIEW_LOG, {"u": user_id, "m": mistake_id, "on": day,
                              "at": f"{day} 10:00:00", "r": rating})


def one_attempt(conn, question_id, day, result="wrong", user_id=7):
    conn.execute(ATTEMPT, {"u": user_id, "q": question_id, "result": result, "on": day,
                           "stamp": STAMP})


# ---------------------------------------------------------------- 一、掌握度四格

def test_mastery_bands_come_from_config_not_from_code(db):
    """四格的名字与边界一律读 `config/schedule.py`，改口径不碰代码。"""
    keys = [item["key"] for item in stats_service.mastery_distribution([])]
    assert keys == [band[0] for band in schedule.MASTERY_BANDS]
    assert [item["label"] for item in stats_service.mastery_distribution([])] == [band[1] for band in schedule.MASTERY_BANDS]


def test_step_index_sorts_into_the_right_band(db):
    add_user(db, 7, "s")
    qids = [add_question(db, 700 + n, owner_id=7) for n in range(4)]
    ids = [add_mistake(db, 7, qid) for qid in qids]
    for index, (step, reviewed) in enumerate([(0, 0), (2, 1), (4, 3), (7, 9)]):
        db.execute("UPDATE mistake SET step_index=?, review_count=? WHERE id=?",
                   (step, reviewed, ids[index]))
    db.commit()
    counts = {item["key"]: item["count"] for item in stats_service.overview(db, 7)["mastery"]}
    assert counts == {"not_started": 1, "just_started": 1, "on_the_way": 1, "settled": 1}


def test_lapsed_back_to_zero_still_lands_in_a_band(db):
    """★ 选「完全没记住」会把台阶打回 0，但 `review_count` 已经不为 0。
    这种行必须仍有一格收容它（抬进"刚上手"），否则四格加起来少于队列长度，图就骗人。"""
    add_user(db, 7, "s")
    mistake_id = add_mistake(db, 7, add_question(db, 700, owner_id=7))
    db.execute("UPDATE mistake SET step_index=0, review_count=3 WHERE id=?", (mistake_id,))
    db.commit()
    counts = {item["key"]: item["count"] for item in stats_service.overview(db, 7)["mastery"]}
    assert sum(counts.values()) == 1
    assert counts["just_started"] == 1 and counts["not_started"] == 0


# ---------------------------------------------------------------- 二、热力图

def test_heatmap_has_45_days_and_keeps_the_empty_ones(db):
    add_user(db, 7, "s")
    mistake_id = add_mistake(db, 7, add_question(db, 700, owner_id=7))
    one_review(db, mistake_id, "2026-10-22")
    one_review(db, mistake_id, "2026-10-22")
    db.commit()
    cells = stats_service.overview(db, 7)["heatmap"]
    assert len(cells) == stats_service.HEATMAP_DAYS == 45
    assert sum(cell["count"] for cell in cells) == 2
    assert sum(1 for cell in cells if cell["count"] == 0) == 44      # 空格照样出格，图才不骗人


def test_heatmap_groups_into_full_weeks(db):
    weeks = stats_service.overview(db, 7)["heatmap_weeks"]
    assert all(len(row) == 7 for row in weeks[:-1])
    assert sum(len(row) for row in weeks) >= 45


def test_heatmap_follows_the_review_day_column(db):
    """热力图数的是 `reviewed_on`（复习日），不是墙上时钟那一天——三-3 只认这一个日历。"""
    add_user(db, 7, "s")
    mistake_id = add_mistake(db, 7, add_question(db, 700, owner_id=7))
    db.execute(REVIEW_LOG, {"u": 7, "m": mistake_id, "on": "2026-10-21",
                            "at": "2026-10-22 00:20:00", "r": 2})     # 评的当下已过零点
    db.commit()
    cells = {cell["date"].isoformat(): cell["count"] for cell in stats_service.overview(db, 7)["heatmap"]}
    assert cells["2026-10-21"] == 1 and cells.get("2026-10-22", 0) == 0


# ---------------------------------------------------------------- 三、近 30 天

def test_trend_only_covers_the_last_thirty_days(db):
    add_user(db, 7, "s")
    mistake_id = add_mistake(db, 7, add_question(db, 700, owner_id=7))
    one_review(db, mistake_id, "2026-10-22", rating=4)
    one_review(db, mistake_id, "2026-01-05", rating=1)
    db.commit()
    series = stats_service.overview(db, 7)["trend"]
    assert [row["date"].isoformat() for row in series] == ["2026-10-22"]
    assert series[0] == {"date": series[0]["date"], "total": 1, "missed": 1}


def test_trend_shapes_are_scaled_into_the_chart_box(db):
    add_user(db, 7, "s")
    mistake_id = add_mistake(db, 7, add_question(db, 700, owner_id=7))
    for count in range(3):
        one_review(db, mistake_id, "2026-10-22")
    one_review(db, mistake_id, "2026-10-21")
    db.commit()
    shapes = stats_service.overview(db, 7)["trend_shapes"]
    assert shapes["peak"] == 3
    points = shapes["total"].split()
    assert points[-1].endswith(f",{0.0:.1f}")          # 最高的那天贴顶
    assert points[0].startswith("0.0,")                 # 最早那天从左边起笔


# ---------------------------------------------------------------- 四、薄弱排行

def test_both_error_sources_count_the_same(db):
    """练习做错一次 + 复习自评「没记住」一次 = 2，两源同权、错一次计一次（三-19）。"""
    add_user(db, 7, "s")
    qid = add_question(db, 700, owner_id=7)
    point = add_knowledge(db, 21, 1, "稳态近似", created_by=7)
    link(db, qid, point)
    mistake_id = add_mistake(db, 7, qid)
    one_attempt(db, qid, "2026-10-22")
    one_review(db, mistake_id, "2026-10-22", rating=4)
    db.commit()
    weak = stats_service.overview(db, 7)["weak_points"]
    assert [(item["name"], item["count"]) for item in weak] == [("稳态近似", 2)]


def test_a_good_rating_does_not_count_as_weak(db):
    add_user(db, 7, "s")
    qid = add_question(db, 700, owner_id=7)
    link(db, qid, add_knowledge(db, 22, 1, "雅可比矩阵", created_by=7))
    one_review(db, add_mistake(db, 7, qid), "2026-10-22", rating=1)
    db.commit()
    assert stats_service.overview(db, 7)["weak_points"] == []


def test_delisted_point_is_skipped_without_a_complaint(db):
    """★ 已下架的知识点不参与排行、也不报错：统计页上冒出一句"有东西看不见"比少一根柱子更糟。"""
    add_user(db, 7, "s")
    qid = add_question(db, 700, owner_id=7)
    live = add_knowledge(db, 23, 1, "留数定理", created_by=7)
    dead = add_knowledge(db, 24, 1, "已下架的东西", created_by=7, status="hidden")
    link(db, qid, live)
    link(db, qid, dead)
    one_attempt(db, qid, "2026-10-22")
    db.commit()
    weak = stats_service.overview(db, 7)["weak_points"]
    assert [(item["name"], item["count"]) for item in weak] == [("留数定理", 1)]


def test_deleted_question_does_not_inflate_the_ranking(db):
    add_user(db, 7, "s")
    qid = add_question(db, 700, owner_id=7)
    link(db, qid, add_knowledge(db, 25, 1, "中值定理", created_by=7))
    one_attempt(db, qid, "2026-10-22")
    db.execute("UPDATE question_bank SET deleted_at=? WHERE id=?", (STAMP, qid))
    db.commit()
    assert stats_service.overview(db, 7)["weak_points"] == []


def test_statistics_never_mine_someone_elses_rows(db):
    add_user(db, 7, "me")
    add_user(db, 8, "other")
    qid = add_question(db, 700, owner_id=8, visibility="private")
    one_attempt(db, qid, clock.review_date_of("00:00").isoformat(), user_id=8)
    db.commit()
    assert stats_service.overview(db, 7)["today"]["wrong_today"] == 0
    assert stats_service.overview(db, 8)["today"]["wrong_today"] == 1


# ---------------------------------------------------------------- 页面

def test_stats_page_renders_four_charts(client, db):
    from tests.conftest import sign_up
    sign_up(client, username="stu")
    body = client.get("/review/stats").get_data(as_text=True)
    for heading in ("掌握度分布", "复习热力图", "近 30 天", "薄弱知识点"):
        assert heading in body
    assert 'class="heat"' in body                      # 一个数据也没有，空格也照样画满 45 格
    assert "这 30 天还没有复习记录" in body          # 折线没数据时给的是这句话，不是一张空图


def test_stats_page_requires_login(client):
    assert client.get("/review/stats").status_code == 302
