"""步 16/17 演示：凡是侧边栏上看得见的链接，点过去都不许是死链或白屏。

`config/menu.py` 里 `visible=True` 就是"这页已经做了"的承诺。
这条用例把承诺变成机器能查的东西：**点亮一条链接却忘了挂路由，这里当场红**。
"""

import pytest

from config import menu, permissions
from src.data.repository.mistake_repo import MistakeRepo
from src.data.repository.question_repo import QuestionRepo
from tests.conftest import add_mistake, add_question, add_user, sign_up, uid_of

# 只有先有内容才打得开的页面，单独列出并先造数据
NEEDS_DATA = {"/review/card": "card", "/study/edit": "edit"}


def paths_to_visit():
    return [item for item in menu.MENU if item.visible]


@pytest.mark.parametrize("item", paths_to_visit(), ids=lambda item: item.key)
def test_every_visible_link_responds_for_a_member(client, item):
    sign_up(client, username="stu")
    if item.role == "admin":
        pytest.skip("管理员条目由 test_admin_links 单独走")
    response = client.get(item.url)
    assert response.status_code < 500, f"{item.key} → {response.status_code}"
    # 302 只允许是"切模式"那种带 next 的跳转；正常页面必须给 200
    assert response.status_code in (200, 302), f"{item.key} → {response.status_code}"


def test_admin_only_items_are_closed_to_members(client):
    """菜单不显示不等于路由敞开：普通用户直接敲后台地址必须被拦住。"""
    sign_up(client, username="stu")
    for item in menu.MENU:
        if item.role != "admin":
            continue
        assert client.get(item.url).status_code in (302, 403, 404), item.key


def test_hidden_items_stay_out_of_the_sidebar(client):
    sign_up(client, username="stu")
    body = client.get("/study/").get_data(as_text=True)
    for item in menu.MENU:
        if not item.visible:
            assert f'href="{item.url}"' not in body, item.key


# ---------------------------------------------------------------- 回收站回归

def test_trash_page_renders_a_deleted_mistake(client, db):
    """★ 这条用例来自步 17 截图时撞到的 500：回收站里躺着一道错题时页面白屏。

    `_describe()` 为了给错题取标题去查题干，属性名写错就整页崩——
    而库里没有软删错题的时候这条路径根本走不到，所以必须拿数据把它踩一遍。
    """
    sign_up(client, username="stu")
    alice = uid_of(db, "stu")
    question_id = add_question(db, 900, owner_id=alice)
    mistake_id = add_mistake(db, alice, question_id)
    db.execute("UPDATE mistake SET deleted_at=?, deleted_by=? WHERE id=?",
               ("2026-10-21 10:00:00", alice, mistake_id))
    db.commit()
    body = client.get("/review/trash").get_data(as_text=True)
    assert "错题" in body and f"题目 #{mistake_id}" not in body      # 标题取到了题干本身
    assert "题干 900" in body
