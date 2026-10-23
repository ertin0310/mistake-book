"""步 8 演示（数据与业务层部分）：录一道简答题 → 我的题目列表能筛能翻。

视图层（录题表单、列表页）还没做，所以这里测的是 service 与 repo 这一段；
页面做完再补浏览器那一条用例。
"""

import pytest

from config import prompts
from src.data.repository.mistake_repo import MistakeRepo
from src.data.repository.question_repo import QuestionRepo
from src.domain import clock
from src.domain.errors import ValidationError
from src.domain.question_types import registry
from src.services import question_service


def essay_form(stem="为什么引入线程？它比进程轻在哪里？", answer="线程共享地址空间，切换只换上下文",
               subject="1", type_name="essay"):
    return {"subject_id": subject, "type": type_name, "stem": stem, "answer": answer,
            "explanation": "答「共享地址空间」才算说到点上。"}


# ---------------------------------------------------------------- 录题

def test_create_returns_id_and_stores_canonical_json(db):
    qid = question_service.create(db, 1, essay_form())
    row = QuestionRepo(db, 1).mine_one(qid)
    assert row["stem"].startswith("为什么引入线程")
    assert row["options_json"] == "[]"
    assert row["answer_json"] == '{"text":"线程共享地址空间，切换只换上下文"}'
    assert row["visibility"] == "private"          # 共享默认关闭，必须用户主动（三-10）


def test_stem_with_vertical_bars_is_not_split(db):
    """题干里的 `|x|` 一个字符都不许丢——它是纯文本，不走列内规范化。"""
    qid = question_service.create(db, 1, essay_form(stem="|x| 在 x=0 处连续吗？"))
    assert QuestionRepo(db, 1).mine_one(qid)["stem"] == "|x| 在 x=0 处连续吗？"


@pytest.mark.parametrize("bad", [
    {"stem": "", "answer": "有答案"},
    {"stem": "有题干", "answer": ""},
])
def test_validation_collects_chinese_errors(db, bad):
    form = dict(essay_form(), **bad)
    errors = question_service.new_errors(db, form)
    assert errors and all("不能空着" in e for e in errors)


def test_unknown_subject_or_type_is_rejected(db):
    assert prompts.SUBJECT_UNUSABLE in question_service.new_errors(db, essay_form(subject="2"))
    assert question_service.new_errors(db, essay_form(type_name="choice"))


# ---------------------------------------------------------------- 两个具名读法

def test_mine_and_shared_pool_do_not_leak(db):
    question_service.create(db, 1, essay_form(stem="我的私有题"))
    shared = question_service.create(db, 1, essay_form(stem="我要共享的题"))
    db.execute("UPDATE question_bank SET visibility='shared' WHERE id=?", (shared,))
    db.commit()

    mine = [r["stem"] for r in question_service.mine(db, 1).items]
    assert "我的私有题" in mine and "我要共享的题" in mine

    # 共享池是"别人的池"：自己的共享题不该出现在自己的共享池里
    pool = [r["stem"] for r in question_service.shared_pool(db, 1).items]
    assert "我要共享的题" not in pool

    other_pool = [r["stem"] for r in QuestionRepo(db, 2).shared_pool().items]
    assert "我要共享的题" in other_pool
    assert "我的私有题" not in other_pool


def test_official_questions_show_up_in_the_pool(db):
    """官方题 `user_id` 为 NULL——一条 SQL 混捞就会把它漏掉，这正是 named 存在的理由。"""
    db.execute("INSERT INTO question_bank (user_id, subject_id, type, stem, options_json,"
               " answer_json, explanation, source, visibility, created_at, updated_at)"
               " VALUES (NULL, 1, 'essay', '官方题', '[]', '{\"text\":\"答案\"}', '',"
               " 'official', 'shared', datetime('now','localtime'), datetime('now','localtime'))")
    db.commit()
    assert "官方题" in [r["stem"] for r in QuestionRepo(db, 2).shared_pool().items]


def test_named_repo_refuses_generic_read(db):
    with pytest.raises(ValueError):
        QuestionRepo(db, 1).rows()


# ---------------------------------------------------------------- 列表翻页

def test_list_pages_at_twenty_and_falls_back(db):
    for n in range(25):
        question_service.create(db, 1, essay_form(stem=f"第 {n} 题"))
    db.commit()
    first = question_service.mine(db, 1, page=1)
    # fixture 里 u1 有 3 道未删的题，但其中"题干 3"被官方收起 → mine 读法也看不见它
    assert (first.total, first.total_pages, len(first.items)) == (27, 2, 20)
    assert question_service.mine(db, 1, page=999).page == 2


def test_list_can_filter_by_subject(db):
    question_service.create(db, 1, essay_form(stem="数学题", subject="1"))
    db.execute("UPDATE subject SET status='active' WHERE id=2")     # 把英语启用，造第二个科目
    db.commit()
    question_service.create(db, 1, essay_form(stem="英语题", subject="2"))
    db.commit()
    stems = [r["stem"] for r in question_service.mine(db, 1, subject_id=2).items]
    assert stems == ["英语题"]


# ---------------------------------------------------------------- 错题队列（步 9 要用，先钉住取题条件）

def test_due_page_respects_the_four_conditions(db):
    today = clock.review_date_of("00:00")
    mine = question_service.create(db, 1, essay_form(stem="该复习的"))
    hidden = question_service.create(db, 1, essay_form(stem="回收站里的"))
    db.execute("UPDATE question_bank SET deleted_at=datetime('now','localtime') WHERE id=?", (hidden,))
    db.commit()
    repo = MistakeRepo(db, 1)
    repo.add(mine, today)
    repo.add(hidden, today)
    db.commit()
    rows, total, page, pages = repo.due_page(today)
    assert [r["stem"] for r in rows] == ["该复习的"]
    assert total == 1
