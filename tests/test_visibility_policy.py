"""第 3 步演示：四种 scope 真的在 SQL 层过滤掉了别人的数据。

★ 本文件最值钱的是最后那条 `test_sql_clause_matches_python_predicate`：可见性规则在
  `visibility.py` 里是 Python、在 `base.py` 里是 SQL 字符串，**同一条规则写了两遍**
  （过滤必须发生在 SQL 里，否则翻页的总数就不对）。那条测试穷举取值组合逐格比对，
  两边一旦漂移立刻红。
"""

from itertools import product

from src.data.repository.base import (
    NO_USER_INJECTION, SCOPE_DICT, SCOPE_NAMED, SCOPE_POLICY, SCOPE_USER,
    VISIBILITY_CLAUSES, BaseRepo,
)
from src.domain import visibility as vis
from tests.conftest import STAMP
import pytest


class MistakeRepo(BaseRepo):
    table = "mistake"
    scope = SCOPE_USER


class KnowledgeRepo(BaseRepo):
    table = "knowledge_point"
    scope = SCOPE_POLICY
    visibility_entity = vis.ENTITY_KNOWLEDGE


class SubjectRepo(BaseRepo):
    table = "subject"
    scope = SCOPE_DICT
    visibility_entity = vis.ENTITY_SUBJECT


class QuestionRepo(BaseRepo):
    table = "question_bank"
    scope = SCOPE_NAMED
    named_reads = ("mine", "shared_pool")


def ids(rows):
    return sorted(row["id"] for row in rows)


# `mistake` 有一串 NOT NULL 且无默认值的列，测试里每次写全太吵，收成一份。
MISTAKE_DEFAULTS = dict(entry_reason="marked_wrong", step_index=0, interval_days=0,
                        due_date="2026-10-21", review_count=0, lapse_count=0,
                        created_at=STAMP, updated_at=STAMP)


# ---------------------------------------------------------------- user scope

def test_user_scope_hides_others_rows(db):
    MistakeRepo(db, 1).create(question_id=1, **MISTAKE_DEFAULTS)
    MistakeRepo(db, 2).create(question_id=4, **MISTAKE_DEFAULTS)
    db.commit()
    assert ids(MistakeRepo(db, 1).rows()) == [1]
    assert ids(MistakeRepo(db, 2).rows()) == [2]


def test_user_scope_get_returns_none_for_others(db):
    """别人的行与"不存在"是同一件事——service 层据此统一给 404（七-1）。"""
    mistake_id = MistakeRepo(db, 1).create(question_id=1, **MISTAKE_DEFAULTS)
    assert MistakeRepo(db, 1).get(mistake_id) is not None
    assert MistakeRepo(db, 2).get(mistake_id) is None


def test_user_scope_requires_viewer(db):
    with pytest.raises(ValueError):
        MistakeRepo(db, None).rows()


def test_create_forces_owner_to_viewer(db):
    """调用方就算传了别人的 user_id 也会被覆盖，归属不可能写错（二-5）。"""
    mistake_id = MistakeRepo(db, 1).create(question_id=1, user_id=2, **MISTAKE_DEFAULTS)
    row = MistakeRepo(db, 1).get(mistake_id)
    assert row is not None and row["user_id"] == 1


def test_create_rejects_unknown_column(db):
    with pytest.raises(ValueError):
        MistakeRepo(db, 1).create(question_id=1, not_a_column=5)


def test_dict_scope_write_waits_for_step4(db):
    with pytest.raises(ValueError):
        SubjectRepo(db, 1).create(name="新科目", status="active")


# ---------------------------------------------------------------- policy / dict

def test_policy_scope_knowledge(db):
    assert ids(KnowledgeRepo(db, 1).rows()) == [1, 2, 3, 4]   # 通过的（含别人提交的）+ 自己被驳回/下架的
    assert ids(KnowledgeRepo(db, 2).rows()) == [1, 4]         # 别人的驳回、下架行看不见
    assert 5 not in ids(KnowledgeRepo(db, 1).rows())          # ★ 软删的连作者也不给看见


def test_dict_scope_subject_has_no_owner_filter(db):
    """科目没有归属人：谁来看都只有 active 那一条，下架的只在后台可见。"""
    assert ids(SubjectRepo(db, 1).rows()) == [1]
    assert ids(SubjectRepo(db, 2).rows()) == [1]
    assert ids(SubjectRepo(db, None).rows()) == [1]


# ---------------------------------------------------------------- named scope

def test_named_scope_refuses_generic_read(db):
    """`question_bank` 用一条 SQL 混捞"我的"和"共享池"必出错，入口就堵掉（二-5）。"""
    repo = QuestionRepo(db, 1)
    for call in (repo.rows, repo.count, repo.paginate):
        with pytest.raises(ValueError):
            call()
    with pytest.raises(ValueError):
        repo.get(1)


def test_named_reads_do_not_leak(db):
    mine = ids(QuestionRepo(db, 1).read_named(
        "mine", "user_id = :viewer AND deleted_at IS NULL AND delisted_by IS NULL").items)
    pool = ids(QuestionRepo(db, 1).read_named(
        "shared_pool", "deleted_at IS NULL AND delisted_by IS NULL"
        " AND visibility = 'shared' AND (user_id IS NULL OR user_id <> :viewer)").items)
    assert mine == [1, 2]     # 自己的：私有 + 已共享；软删的 7、被官方收起的 3 都不在
    assert pool == [4, 6]     # 别人的共享 + 官方题，不含自己那两道


def test_named_read_must_be_declared(db):
    with pytest.raises(ValueError):
        QuestionRepo(db, 1).read_named("everything")


# ---------------------------------------------------------------- 声明自检

def test_subject_cannot_declare_user_scope(db):
    class Wrong(SubjectRepo):
        scope = SCOPE_USER

    with pytest.raises(ValueError):
        Wrong(db, 1)
    assert "subject" in NO_USER_INJECTION


def test_policy_scope_needs_entity(db):
    class Wrong(BaseRepo):
        table = "knowledge_point"
        scope = SCOPE_POLICY

    with pytest.raises(ValueError):
        Wrong(db, 1)


def test_named_scope_needs_read_names(db):
    class Wrong(BaseRepo):
        table = "question_bank"
        scope = SCOPE_NAMED

    with pytest.raises(ValueError):
        Wrong(db, 1)


def test_unknown_table_rejected(db):
    class Wrong(BaseRepo):
        table = "不存在的表"

    with pytest.raises(ValueError):
        Wrong(db, 1)


# ---------------------------------------------------------------- ★ 两边一致

def _sql_visible(conn, entity, row, viewer):
    probe = dict(status=None, deleted_at=None, delisted_by=None, visibility=None,
                 user_id=None, created_by_user_id=None)
    probe.update(row)
    sql = ("SELECT 1 FROM (SELECT :status AS status, :deleted_at AS deleted_at,"
           " :delisted_by AS delisted_by, :visibility AS visibility,"
           " :user_id AS user_id, :created_by_user_id AS created_by_user_id)"
           f" WHERE {VISIBILITY_CLAUSES[entity]}")
    params = dict(probe, viewer=viewer, vis_active=vis.KP_ACTIVE, vis_shared=vis.SHARED)
    if entity == vis.ENTITY_SUBJECT:
        params["vis_active"] = vis.SUBJECT_ACTIVE
    return conn.execute(sql, params).fetchone() is not None


def test_sql_clause_matches_python_predicate(mem_db):
    """穷举三种实体的取值组合：SQL 判据与 Python 判据必须逐格相同。

    没有这条，"规则只有一份"就是句空话——两份规则会各自演化，
    而漂移的表现是"某个列表多显示几条不该显示的数据"，不报错。
    """
    states = ["approved", "hidden", "rejected", "active", "private", "shared", None]
    stamps = [None, "2026-10-01 10:00"]
    people = [None, 1, 2]
    mismatches = []
    checked = 0
    for status, deleted, delisted, owner, viewer in product(states, stamps, stamps, people, people):
        row = dict(status=status, deleted_at=deleted, delisted_by=delisted,
                   visibility=status, user_id=owner, created_by_user_id=owner)
        answers = (
            (vis.ENTITY_KNOWLEDGE,
             vis.knowledge_point_visible(status or "", deleted, owner, viewer)),
            (vis.ENTITY_SUBJECT, vis.subject_visible(status or "", deleted)),
            (vis.ENTITY_QUESTION,
             vis.question_visible(status or "private", deleted, delisted, owner, viewer)),
        )
        for entity, python_answer in answers:
            if entity == vis.ENTITY_QUESTION and status not in ("private", "shared", None):
                continue
            checked += 1
            if _sql_visible(mem_db, entity, row, viewer) != python_answer:
                mismatches.append((entity, status, deleted, delisted, owner, viewer))
    assert checked >= 600, f"穷举格子数掉到 {checked}，是这条测试自己退化了"
    assert not mismatches, f"SQL 与 Python 判据漂移：{mismatches[:5]}"
