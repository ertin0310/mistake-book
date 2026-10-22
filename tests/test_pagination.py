"""第 3 步演示：全站唯一的 `paginate()`（二-15 ★）。

两条要点：① 页码越界**回落到最后一页**，不给空页也不报错；
② 排序串只认白名单形状——ORDER BY 是唯一不能参数化的地方（二-11）。
"""

import pytest

from src.data.repository.base import SCOPE_USER, BaseRepo
from tests.conftest import add_mistake, add_question


class MistakeRepo(BaseRepo):
    table = "mistake"
    scope = SCOPE_USER


@pytest.fixture
def twenty_five(db):
    """给 u1 灌 25 道错题（各配一道自己的题，外键要过）。"""
    for n in range(1, 26):
        add_question(db, 100 + n, owner_id=1)
        add_mistake(db, 1, 100 + n)
    db.commit()
    return MistakeRepo(db, 1)


def test_default_page_size_is_twenty(twenty_five):
    page = twenty_five.paginate()
    assert page.page_size == 20
    assert len(page.items) == 20
    assert (page.total, page.total_pages) == (25, 2)


def test_second_page_has_the_remainder(twenty_five):
    page = twenty_five.paginate(page=2)
    assert len(page.items) == 5
    assert page.page == 2


def test_page_999_falls_back_to_last_page(twenty_five):
    """★ 越界页码回落到最后一页：列表页上的"第 999 页"多半是旧链接或手输，
    给空页会让人以为自己的错题被删了。"""
    page = twenty_five.paginate(page=999)
    assert page.page == 2
    assert len(page.items) == 5


def test_page_zero_or_negative_falls_back_to_first(twenty_five):
    assert twenty_five.paginate(page=0).page == 1
    assert twenty_five.paginate(page=-7).page == 1


def test_empty_table_still_gives_one_page(twenty_five):
    page = twenty_five.paginate(where="due_date = :d", params={"d": "1900-01-01"})
    assert (page.total, page.total_pages, page.items) == (0, 1, [])
    assert page.page == 1


def test_page_size_override(twenty_five):
    page = twenty_five.paginate(page=3, page_size=10)
    assert page.page == 3 and len(page.items) == 5


def test_pagination_never_rewrites_due_dates(twenty_five):
    """翻页只管"一屏看多少道"，不许为了凑数去动 `due_date`（三-11 ★）。

    上限管今天排多少道、翻页管一屏看多少道，两件事不混；这条断言把
    "翻页会污染到期日"这条路提前堵死。
    """
    before = [row["due_date"] for row in twenty_five.rows()]
    for page_no in (1, 2, 999):
        twenty_five.paginate(page=page_no)
    assert [row["due_date"] for row in twenty_five.rows()] == before


def test_where_and_order_still_filtered(twenty_five):
    page = twenty_five.paginate(where="due_date = :d", params={"d": "2026-10-21"},
                                order="id DESC")
    assert page.total == 25
    assert page.items[0]["id"] == max(row["id"] for row in twenty_five.rows())


@pytest.mark.parametrize("bad", [
    "id; DROP TABLE mistake", "1=1", "id, name", "(SELECT 1)", "random()",
])
def test_illegal_order_rejected(twenty_five, bad):
    """多列、分号、函数、子查询一律拒——排序串永远来自代码里写死的字面量。"""
    with pytest.raises(ValueError):
        twenty_five.paginate(order=bad)


def test_named_read_shares_the_same_fallback(db):
    """具名读法与 paginate 用同一套越界规则，翻页这件事全站只有一份。"""
    from src.data.repository.base import SCOPE_NAMED

    class QuestionRepo(BaseRepo):
        table = "question_bank"
        scope = SCOPE_NAMED
        named_reads = ("mine",)

    for n in range(1, 26):
        add_question(db, 200 + n, owner_id=1)
    db.commit()
    page = QuestionRepo(db, 1).read_named("mine", "user_id = :viewer AND id >= 200", page=999)
    assert page.total == 25 and page.page == 2 and len(page.items) == 5
