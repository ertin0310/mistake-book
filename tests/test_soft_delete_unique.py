"""步 14 演示（其二）：软删不占名字——四条 partial unique 各验一次。

库里那四条唯一索引都带 `WHERE` 条件（`schema.sql` 末尾），意思是
**"只有还在用的那些行才互斥"**。这一份验的是两件事：
1. 删掉（软删）之后同名能重建 —— 少一条就报"重复"，用户会以为程序不让他用；
2. 重建之后再还原旧的 —— 必须撞出冲突提示，而不是 500 白屏（步 11 的预检）。
"""

import sqlite3

import pytest

from src.data.repository.archive_repo import ArchiveRepo
from src.data.repository.knowledge_repo import KnowledgeRepo
from src.data.repository.mistake_repo import MistakeRepo
from src.data.repository.question_repo import QuestionRepo
from src.domain.errors import RestoreConflictError
from tests.conftest import STAMP, add_knowledge, add_mistake, add_question, add_subject, add_user

TAG = "INSERT INTO tag (user_id, name, created_at, deleted_at) VALUES (?, ?, ?, ?)"
SUBJECT = ("INSERT INTO subject (name, status, created_at, updated_at, deleted_at)"
           " VALUES (?, 'active', ?, ?, ?)")


def add_tag(conn, user_id, name, deleted_at=None):
    return conn.execute(TAG, (user_id, name, STAMP, deleted_at)).lastrowid


# ---------------------------------------------------------------- 错题

def test_deleted_mistake_frees_the_pair(db):
    """软删一条错题之后，同一道题能再进队列（`uq_mistake_active` 只管未删的那些）。"""
    add_user(db, 31, "u31")
    qid = add_question(db, 310, owner_id=31)
    first = add_mistake(db, 31, qid)
    db.execute("UPDATE mistake SET deleted_at=?, purged_at=NULL WHERE id=?", (STAMP, first))
    db.commit()
    second = add_mistake(db, 31, qid)          # 不炸就是对的
    assert second != first
    assert MistakeRepo(db, 31).active_for(qid)["id"] == second


def test_active_mistake_still_blocks_the_same_pair(db):
    add_user(db, 31, "u31")
    qid = add_question(db, 310, owner_id=31)
    add_mistake(db, 31, qid)
    with pytest.raises(sqlite3.IntegrityError):
        add_mistake(db, 31, qid)


# ---------------------------------------------------------------- 标签

def test_soft_deleted_tag_frees_the_name(db):
    add_user(db, 32, "u32")
    add_tag(db, 32, "错题多", deleted_at=STAMP)
    add_tag(db, 32, "错题多")                  # 同名但一个是死的 → 允许
    assert db.execute("SELECT COUNT(*) AS n FROM tag WHERE user_id=32").fetchone()["n"] == 2
    with pytest.raises(sqlite3.IntegrityError):
        add_tag(db, 32, "错题多")              # 两个都活着 → 拦下


def test_tag_name_is_per_person(db):
    add_user(db, 32, "u32")
    add_user(db, 33, "u33")
    add_tag(db, 32, "错题多")
    add_tag(db, 33, "错题多")                  # 别人的同名标签与我不相干


# ---------------------------------------------------------------- 知识点

def test_rejected_and_hidden_names_do_not_block_a_new_submission(db):
    """★ 被驳回 / 被下架 / 已删的知识点都不占名字（三-6）。"""
    add_user(db, 34, "u34")
    add_knowledge(db, 401, 1, "泰勒公式", created_by=34, status="rejected")
    add_knowledge(db, 402, 1, "冲量定理", created_by=34, status="hidden")
    # 第三种死法：状态还是 approved，但已经软删。`uq_kp_approved` 的条件是
    # `deleted_at IS NULL AND status='approved'`，两个条件少一个都还占着名字
    add_knowledge(db, 403, 1, "斯托尔兹定理", created_by=34, deleted_at=STAMP)
    for name in ("泰勒公式", "冲量定理", "斯托尔兹定理"):
        assert KnowledgeRepo(db, 34).submit(34, 1, name)   # 三条都能重新一份 approved
    with pytest.raises(sqlite3.IntegrityError):
        KnowledgeRepo(db, 34).submit(34, 1, "泰勒公式")     # approved 之间仍然互斥


# ---------------------------------------------------------------- 科目

def test_hidden_subject_frees_the_name(db):
    add_subject(db, 61, "高等数学", status="hidden")
    db.execute(SUBJECT, ("高等数学", STAMP, STAMP, None))   # 停用不占名字，能再建同名 active
    assert db.execute("SELECT COUNT(*) AS n FROM subject WHERE name='高等数学'").fetchone()["n"] == 2


# ---------------------------------------------------------------- 还原撞回来要有话可说

def test_restore_after_recreating_hits_a_conflict_not_a_crash(db):
    """软删→同名重建→再还原旧的：必须给中文冲突提示（409），不能是 500 白屏。"""
    add_user(db, 35, "u35")
    actor = ArchiveRepo(db, 35)
    qid = add_question(db, 350, owner_id=35)

    mistake_id = add_mistake(db, 35, qid)
    db.execute("UPDATE mistake SET deleted_at=?, deleted_by=? WHERE id=?",
               (STAMP, 35, mistake_id))
    db.commit()
    add_mistake(db, 35, qid)                   # 队列里又活了一条
    with pytest.raises(RestoreConflictError):
        actor.restore_from_trash("mistake", mistake_id, 35)

    tag_id = add_tag(db, 35, "错题多", deleted_at=STAMP)
    add_tag(db, 35, "错题多")
    with pytest.raises(RestoreConflictError):
        actor.restore_from_trash("tag", tag_id, 35)

    point_id = add_knowledge(db, 501, 1, "泰勒公式", created_by=35, status="rejected")
    KnowledgeRepo(db, 35).submit(35, 1, "泰勒公式")
    with pytest.raises(RestoreConflictError):
        actor.restore_from_trash("knowledge_point", point_id, 35)


def test_question_restore_conflict_uses_delisted_by(db):
    """题这一格判"在用"的条件是 `delisted_by`，不是 `deleted_at`——还原预检必须跟着它。"""
    add_user(db, 36, "u36")
    add_user(db, 99, "boss", role="admin")
    qid = add_question(db, 360, owner_id=36)
    db.execute("UPDATE question_bank SET deleted_at=?, deleted_by=? WHERE id=?",
               (STAMP, 36, qid))
    add_question(db, 361, owner_id=36)          # 另一道题活着，跟同名无关
    db.commit()
    ArchiveRepo(db, 36).restore_from_trash("question", qid, 36)     # 能还原
    assert QuestionRepo(db, 36).mine_one(qid) is not None
