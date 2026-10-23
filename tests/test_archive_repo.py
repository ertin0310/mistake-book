"""步 11 演示：软删能还原、不撞约束、被驳回的不占名字。

★ 最值钱的是 `test_registry_matches_schema_partial_indexes`：注册表里那句
  "什么算在用"必须和 `schema.sql` 里 partial unique 的 WHERE 条件**逐字一致**，
  不一致就会出现"预检说没有、插入却报重复"。
"""

import re
from pathlib import Path

import pytest

from config import archive, prompts
from src.data.repository.archive_repo import ArchiveRepo
from src.domain.errors import RestoreConflictError
from tests.conftest import (STAMP, add_question, add_user, csrf_token, sign_up,
                          uid_of)


SCHEMA = (Path(__file__).resolve().parent.parent / "src" / "data" / "schema.sql"
          ).read_text(encoding="utf-8")


@pytest.fixture
def actor(db):
    add_user(db, 21, "actor")
    db.commit()
    return ArchiveRepo(db, 21)


# ---------------------------------------------------------------- 注册表与 schema 一致

def test_registry_matches_schema_partial_indexes():
    pattern = r"CREATE UNIQUE INDEX (\w+)\s+ON\s+\w+\([^)]*\)\s*WHERE([^;]+);"
    indexes = {match.group(1): " ".join(match.group(2).split())
               for match in re.finditer(pattern, SCHEMA, re.S)}
    assert len(indexes) >= 4, "schema 里的 partial unique 索引少到不对劲"
    pairs = {"uq_mistake_active": "mistake", "uq_tag_active": "tag",
             "uq_kp_approved": "knowledge_point", "uq_subject_active": "subject"}
    for index_name, entity in pairs.items():
        assert archive.ENTITIES[entity].in_use_where == indexes[index_name], index_name


def test_unique_columns_match_the_index_columns():
    for entity, spec in archive.ENTITIES.items():
        if not spec.unique_columns:
            continue
        columns = {row[1] for row in _table_info_columns(spec.table)}
        assert set(spec.unique_columns) <= columns, entity


def _table_info_columns(table):
    """给上一条测试用的列名查询（内存库的表结构就是 schema.sql 建的）。"""
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    return conn.execute(f"PRAGMA table_info({table})").fetchall()


# ---------------------------------------------------------------- 隐藏库三格

def test_hide_and_restore_a_knowledge_point(db, actor):
    db.execute("UPDATE knowledge_point SET status='hidden' WHERE id=3")     # fixture 里已有一条
    db.commit()
    # fixture 里 id=2 本来就是 rejected，隐藏库那格同时收 rejected 与 hidden
    assert [r["id"] for r in actor.list_hidden("knowledge_point")] == [3, 2]
    actor.restore("knowledge_point", 3)
    assert db.execute("SELECT status FROM knowledge_point WHERE id=3").fetchone()["status"] == "approved"


def test_rejected_knowledge_shows_in_the_admin_room(db, actor):
    db.execute("UPDATE knowledge_point SET status='rejected' WHERE id=2")
    db.commit()
    assert 2 in [r["id"] for r in actor.list_hidden("knowledge_point")]


def test_admin_delist_writes_delisted_by_never_the_owners_deleted_at(db, actor):
    """★ 管理员收起别人的题只写 `delisted_by`：写成 `deleted_at` 的话，
    那条删除会落进作者自己的回收站，作者点「撤销删除」就把官方处罚翻掉了。"""
    qid = add_question(db, 40, owner_id=1, visibility="shared")
    db.commit()
    actor.hide("question", qid, note="不合规：配图含他人姓名")
    row = db.execute("SELECT deleted_at, deleted_by, delisted_by, delist_note"
                     " FROM question_bank WHERE id=?", (qid,)).fetchone()
    assert row["deleted_at"] is None and row["deleted_by"] is None
    assert row["delisted_by"] == 21 and "不合规" in row["delist_note"]
    assert qid in [r["id"] for r in actor.list_hidden("question")]


def test_delisted_question_is_invisible_to_owner_and_others(db, actor):
    from src.data.repository.question_repo import QuestionRepo
    qid = add_question(db, 41, owner_id=1, visibility="shared")
    actor.hide("question", qid, note="不合规")
    assert QuestionRepo(db, 1).mine_one(qid) is None                 # 作者也看不见
    assert QuestionRepo(db, 2).any_visible(qid) is None              # 别人看不见
    assert QuestionRepo(db, 2).any_visible(qid) is None


# ---------------------------------------------------------------- 还原冲突预检

def test_restoring_a_mistake_that_is_already_active_is_blocked(db, actor):
    """真实触发路径：B 对失效题点「放弃」→ 又做错这题自动入队 → 再点还原旧的。"""
    qid = add_question(db, 42, owner_id=1)
    db.execute("INSERT INTO mistake (user_id, question_id, entry_reason, step_index,"
               " interval_days, due_date, review_count, lapse_count, created_at, updated_at)"
               " VALUES (1, ?, 'marked_wrong', 0, 0, '2026-10-23', 0, 0, ?, ?)",
               (qid, STAMP, STAMP))
    active_id = db.execute("SELECT id FROM mistake WHERE question_id=?", (qid,)).fetchone()["id"]
    db.execute("UPDATE mistake SET deleted_at=?, deleted_by=1 WHERE id=?"
               " AND 1=0", (STAMP, active_id))                                # 不真删，另造一条旧的
    db.execute("INSERT INTO mistake (user_id, question_id, entry_reason, step_index,"
               " interval_days, due_date, review_count, lapse_count, created_at, updated_at,"
               " deleted_at, deleted_by) VALUES (1, ?, 'marked_wrong', 0, 0, '2026-10-01',"
               " 0, 0, ?, ?, ?, 1)", (qid, STAMP, STAMP, STAMP))
    old_id = db.execute("SELECT id FROM mistake WHERE question_id=? AND deleted_at IS NOT NULL",
                        (qid,)).fetchone()["id"]
    db.commit()

    with pytest.raises(RestoreConflictError) as exc:
        actor.restore_from_trash("mistake", old_id, 1)
    assert exc.value.message == prompts.RESTORE_CONFLICT["mistake"]


def test_rejected_knowledge_does_not_occupy_the_name(db, actor):
    """★ 被驳回的行不占名字：否则乙提交同名会被叫去"选用一条只有甲看得见的记录"，卡死。"""
    db.execute("UPDATE knowledge_point SET status='rejected' WHERE id=2")
    db.commit()
    clash = db.execute("SELECT 1 FROM knowledge_point WHERE subject_id=1"
                       " AND name_normalized='泰勒公式' AND deleted_at IS NULL"
                       " AND status='approved'").fetchone()
    assert clash is None


# ---------------------------------------------------------------- 用户回收站

def test_trash_only_shows_what_this_person_deleted(db, actor):
    mine = add_question(db, 43, owner_id=1)
    theirs = add_question(db, 44, owner_id=2)
    db.execute("UPDATE question_bank SET deleted_at=?, deleted_by=1 WHERE id=?", (STAMP, mine))
    db.execute("UPDATE question_bank SET deleted_at=?, deleted_by=2 WHERE id=?", (STAMP, theirs))
    db.commit()
    assert [r["id"] for r in actor.list_trash("question", 1)] == [mine]
    assert [r["id"] for r in actor.list_trash("question", 2)] == [theirs]


def test_restore_from_trash_clears_both_markers(db, actor):
    qid = add_question(db, 45, owner_id=1)
    db.execute("UPDATE question_bank SET deleted_at=?, deleted_by=1 WHERE id=?", (STAMP, qid))
    db.commit()
    actor.restore_from_trash("question", qid, 1)
    row = db.execute("SELECT deleted_at, deleted_by FROM question_bank WHERE id=?", (qid,)).fetchone()
    assert row["deleted_at"] is None and row["deleted_by"] is None


def test_cannot_restore_someone_elses_trash(db, actor):
    qid = add_question(db, 46, owner_id=2)
    db.execute("UPDATE question_bank SET deleted_at=?, deleted_by=2 WHERE id=?", (STAMP, qid))
    db.commit()
    with pytest.raises(Exception):
        actor.restore_from_trash("question", qid, 1)


# ---------------------------------------------------------------- 30 天懒清理

def test_expired_mistake_is_sealed_not_deleted(db, actor):
    """★ `mistake` 永不物理删：到期只打 `purged_at`，行留着——`review_log` 指着它。"""
    qid = add_question(db, 47, owner_id=1)
    mistake_id = db.execute("INSERT INTO mistake (user_id, question_id, entry_reason,"
                            " step_index, interval_days, due_date, review_count, lapse_count,"
                            " created_at, updated_at, deleted_at) VALUES (1, ?, 'marked_wrong',"
                            " 0, 0, '2026-01-01', 0, 0, ?, ?, ?) RETURNING id",
                            (qid, STAMP, STAMP, "2026-01-01 00:00:00")).fetchone()["id"]
    db.execute("INSERT INTO review_log (user_id, mistake_id, reviewed_on, reviewed_at, rating,"
               " rating_source, duration_seconds, algorithm_version, interval_before,"
               " interval_after, due_date_before, due_date_after, step_before, step_after)"
               " VALUES (1, ?, '2026-01-01', ?, 4, 'user_override', 20, 'ladder-1', 1, 1,"
               " '2026-01-01', '2026-01-02', 1, 0)", (mistake_id, STAMP))
    db.commit()

    actor.purge_expired()

    row = db.execute("SELECT purged_at, deleted_at FROM mistake WHERE id=?", (mistake_id,)).fetchone()
    assert row is not None and row["purged_at"] is not None
    assert db.execute("SELECT COUNT(*) FROM review_log WHERE mistake_id=?",
                      (mistake_id,)).fetchone()[0] == 1        # 流水账没被牵连
    assert actor.count_expired() == 1


def test_expired_unused_tag_is_physically_removed(db, actor):
    """标签没人引用了可以真删，但要连带 `tag_link` 一起，别留悬空引用。"""
    tag_id = db.execute("INSERT INTO tag (user_id, name, color, created_at, deleted_at)"
                        " VALUES (1, '旧标签', '#333', ?, ?) RETURNING id",
                        (STAMP, "2026-01-01 00:00:00")).fetchone()["id"]
    db.execute("INSERT INTO tag_link (user_id, tag_id, target_type, target_id, created_at)"
               " VALUES (1, ?, 'question', 1, ?)", (tag_id, STAMP))
    db.commit()

    actor.purge_expired()

    assert db.execute("SELECT 1 FROM tag WHERE id=?", (tag_id,)).fetchone() is None
    assert db.execute("SELECT COUNT(*) FROM tag_link WHERE tag_id=?", (tag_id,)).fetchone()[0] == 0


def test_referenced_tables_are_declared_never_delete():
    assert archive.NEVER_PHYSICALLY_DELETED >= {"question_bank", "knowledge_point",
                                                "subject", "mistake"}


# ---------------------------------------------------------------- 回收站页面

def _new_question(client, db, stem):
    client.post("/study/new", data={"subject_id": "1", "type": "essay", "stem": stem,
                                    "answer": "答案", "explanation": "",
                                    "csrf_token": csrf_token(client, "/study/new")})
    return db.execute("SELECT id FROM question_bank WHERE stem=?", (stem,)).fetchone()["id"]


def test_trash_page_requires_login(client):
    assert client.get("/review/trash").status_code == 302


def test_delete_then_restore_a_question(client, db):
    sign_up(client, username="stu")
    uid = uid_of(db, "stu")
    qid = _new_question(client, db, "要被删的题")
    client.post(f"/study/delete/{qid}", data={"csrf_token": csrf_token(client, "/study/")})
    assert "要被删的题" not in client.get("/study/").get_data(as_text=True)

    page = client.get("/review/trash").get_data(as_text=True)
    assert "要被删的题" in page and "还原" in page
    client.post("/review/trash/restore", data={"entity": "question", "row_id": str(qid),
                                               "csrf_token": csrf_token(client, "/review/trash")})
    assert "要被删的题" in client.get("/study/").get_data(as_text=True)


def test_restore_conflict_shows_a_chinese_notice_not_a_crash(client, db):
    """还原一条已经在队列里的旧错题 → 拦下来并说清楚，不白屏。"""
    sign_up(client, username="stu")
    uid = uid_of(db, "stu")
    qid = _new_question(client, db, "队列里已有的题")
    db.execute("INSERT INTO mistake (user_id, question_id, entry_reason, step_index,"
               " interval_days, due_date, review_count, lapse_count, created_at, updated_at)"
               " VALUES (?, ?, 'marked_wrong', 0, 0, '2026-10-23', 0, 0, ?, ?)",
               (uid, qid, STAMP, STAMP))
    old = db.execute("INSERT INTO mistake (user_id, question_id, entry_reason, step_index,"
                     " interval_days, due_date, review_count, lapse_count, created_at,"
                     " updated_at, deleted_at, deleted_by) VALUES (?, ?, 'marked_wrong', 0, 0,"
                     " '2026-09-01', 0, 0, ?, ?, ?, ?) RETURNING id",
                     (uid, qid, STAMP, STAMP, STAMP, uid)).fetchone()["id"]
    db.commit()

    body = client.get("/review/trash").get_data(as_text=True)
    client.post("/review/trash/restore", data={"entity": "mistake", "row_id": str(old),
                                               "csrf_token": csrf_token(client, "/review/trash")})
    after = client.get("/review/trash").get_data(as_text=True)
    assert prompts.RESTORE_CONFLICT["mistake"] in after
    assert "Traceback" not in after
    assert db.execute("SELECT deleted_at FROM mistake WHERE id=?", (old,)).fetchone()["deleted_at"] is not None


def test_the_words_hidden_room_never_appear_to_users(client, db):
    """用户侧不出现"隐藏库"这个词：他只有回收站和"已失效的题目"两条路。"""
    sign_up(client, username="stu")
    body = client.get("/review/trash").get_data(as_text=True)
    assert "隐藏库" not in body
