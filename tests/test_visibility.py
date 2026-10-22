"""可见性判断的钉子：全站只有这一份（方案三-24），四种页面共用。

这里钉的是"规则本身"；步 3 的 test_visibility_policy.py 钉的是"repo 有没有照它过滤"。
"""

import pytest

from src.domain import visibility as v


# ---------------------------------------------------------------- 知识点

def test_approved_knowledge_visible_to_everyone():
    assert v.knowledge_point_visible("approved", None, 7, 99) is True


def test_rejected_knowledge_only_visible_to_author():
    assert v.knowledge_point_visible("rejected", None, 7, 7) is True
    assert v.knowledge_point_visible("rejected", None, 7, 8) is False


def test_deleted_knowledge_invisible_even_for_author():
    assert v.knowledge_point_visible("approved", "2026-10-01 10:00", 7, 7) is False


# ---------------------------------------------------------------- 科目

def test_subject_hidden_from_all():
    assert v.subject_visible("active", None) is True
    assert v.subject_visible("hidden", None) is False
    assert v.subject_visible("active", "2026-10-01 10:00") is False


# ---------------------------------------------------------------- 题目

def test_own_question_visible_until_deleted():
    assert v.question_visible("private", None, None, 7, 7) is True
    assert v.question_visible("shared", None, None, 7, 7) is True
    assert v.question_visible("shared", "2026-10-01 10:00", None, 7, 7) is False


def test_shared_question_visible_to_others():
    assert v.question_visible("shared", None, None, 7, 8) is True
    assert v.question_visible("private", None, None, 7, 8) is False


def test_delisted_is_invisible_to_author_too():
    """★ 管理员只写收起标记，作者看不到这道题了，但能在失效页看到原因并申诉。
    收起标记绝不能写成 deleted_at，否则作者点撤销删除就把官方处置翻掉了。"""
    assert v.question_visible("shared", None, 1, 7, 8) is False
    assert v.question_visible("shared", None, 1, 7, 7) is False


def test_official_question_visible_to_everyone_when_not_delisted():
    assert v.question_visible("shared", None, None, None, 8) is True


# ---------------------------------------------------------------- 统一入口

def test_is_visible_dispatches_by_entity():
    assert v.is_visible(v.ENTITY_SUBJECT, "active", None, 8) is True
    assert v.is_visible(v.ENTITY_KNOWLEDGE, "rejected", None, 8, owner_user_id=7) is False
    assert v.is_visible(v.ENTITY_KNOWLEDGE, "rejected", None, 7, owner_user_id=7) is True
    assert v.is_visible(v.ENTITY_QUESTION, "shared", None, 8,
                        owner_user_id=7, delisted_by=None) is True
    assert v.is_visible(v.ENTITY_QUESTION, "shared", None, 8,
                        owner_user_id=7, delisted_by=1) is False


def test_is_visible_rejects_unknown_entity():
    """拼错实体名要当场炸，不许悄悄当成"可见"放行。"""
    with pytest.raises(ValueError):
        v.is_visible("note", "active", None, 8)


# ---------------------------------------------------------------- 占名字

def test_occupies_name_matches_partial_unique():
    """★ 这条判据必须与 schema 里 partial unique 的 WHERE 条件逐字一致（三-12a）。"""
    assert v.occupies_name("approved", None, "approved") is True
    assert v.occupies_name("rejected", None, "approved") is False   # 被驳回的不占名字
    assert v.occupies_name("hidden", None, "approved") is False
    assert v.occupies_name("approved", "2026-10-01 10:00", "approved") is False
