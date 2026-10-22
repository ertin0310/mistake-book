"""步 7 演示：科目下拉只给能用的科目；重名科目由数据库自己拦。

★ 这里没有"建科目"的按钮——本期科目由 seed 预置，普通用户只能选用（方案三-5）。
  写操作整组留给步 23 的后台，所以本步的"建"只能用 SQL 直插来验证约束。
"""

import sqlite3

import pytest

from config import prompts
from src.data.repository.subject_repo import SubjectRepo
from src.domain.errors import ValidationError
from src.services import subject_service


def insert_subject(conn, name, status="active", deleted_at=None):
    return conn.execute(
        "INSERT INTO subject (name, status, created_at, updated_at, deleted_at)"
        " VALUES (?, ?, datetime('now','localtime'), datetime('now','localtime'), ?)",
        (name, status, deleted_at)).lastrowid


# ---------------------------------------------------------------- 下拉读取

def test_dropdown_only_shows_active_subjects(db):
    assert subject_service.options(db) == [(1, "数学")]      #  fixture 里英语是 hidden


def test_dict_scope_is_not_affected_by_who_is_looking(db):
    """科目没有归属人：谁来看都一模一样（基类不会给它注入 user_id 条件）。"""
    assert SubjectRepo(db).name_map() == SubjectRepo(db, viewer_id=2).name_map()


def test_hidden_subject_disappears_from_dropdown(db):
    insert_subject(db, "体育")
    db.commit()
    assert len(subject_service.options(db)) == 2
    db.execute("UPDATE subject SET status='hidden' WHERE name='体育'")
    db.commit()
    assert len(subject_service.options(db)) == 1


def test_soft_deleted_subject_disappears_too(db):
    sid = insert_subject(db, "实验课")
    db.execute("UPDATE subject SET deleted_at=datetime('now','localtime') WHERE id=?", (sid,))
    db.commit()
    assert sid not in dict(subject_service.options(db))


# ---------------------------------------------------------------- 校验

def test_require_usable_passes_valid_subject(db):
    assert subject_service.require_usable(db, "1") == 1


@pytest.mark.parametrize("bad", [None, "", "abc", "0", "2", "999"])
def test_require_usable_rejects_everything_else(db, bad):
    """`2` 是 fixture 里那个下架的英语科目：**下架的科目选不到，但历史题还在**。"""
    with pytest.raises(ValidationError) as exc:
        subject_service.require_usable(db, bad)
    assert exc.value.message == prompts.SUBJECT_UNUSABLE


def test_hidden_subject_still_reachable_for_existing_questions(db):
    """停用科目只掐新引用，不动已存在的题——不然一停用就把用户的题一起弄没了。"""
    db.execute("INSERT INTO question_bank (user_id, subject_id, type, stem, options_json,"
               " answer_json, explanation, source, visibility, created_at, updated_at)"
               " VALUES (1, 2, 'essay', '题干', '[]', '{\"text\":\"答案\"}', '', 'manual',"
               " 'private', datetime('now','localtime'), datetime('now','localtime'))")
    db.commit()
    assert db.execute("SELECT COUNT(*) FROM question_bank WHERE subject_id=2").fetchone()[0] == 1
    assert 2 not in dict(subject_service.options(db))


# ---------------------------------------------------------------- 数据库约束

def test_duplicate_active_subject_is_rejected_by_database(db):
    """★ 不是代码查重，是 partial unique 索引拦的（schema 第 281 行）。"""
    insert_subject(db, "高等数学")
    db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        insert_subject(db, "高等数学")


def test_same_name_allowed_when_the_other_one_is_off(db):
    """下架的同名科目可以存在——锁只算"在用"的行，与 `occupies_name()` 逐字一致。"""
    insert_subject(db, "英语", status="active")          # fixture 已有一个 hidden 的英语
    db.commit()
    assert len(db.execute("SELECT id FROM subject WHERE name='英语'").fetchall()) == 2


def test_subject_has_no_user_id_column(db):
    """科目表根本没有 user_id 列：它必须在注入豁免名单里，否则基类会拼出坏 SQL。"""
    columns = {row[1] for row in db.execute("PRAGMA table_info(subject)")}
    assert "user_id" not in columns
