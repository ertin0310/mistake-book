"""步 14 演示（其三）：可见性锁一致性——死掉的行既不占名字，也不许被"推荐"给活人。

三-6 ★ 的那条死局长这样：甲提交「泰勒公式」被驳回 → 乙提交同名 →
查重如果按"同名就拦"，乙会被告知"已经有了，去选用一条**只有甲看得见**的记录" →
乙卡死在页面上。这一份把两头都钉住：**不拦乙新建**，也**不把甲的死行推给乙**。
"""

from src.data.repository.import_session_repo import ImportSessionRepo
from src.data.repository.knowledge_repo import KnowledgeRepo
from src.data.repository.question_repo import QuestionRepo
from src.domain import visibility as vis
from src.services import import_service
from tests.conftest import STAMP, add_knowledge, add_question, add_user, uid_of

甲, 乙 = 51, 52                       # 名字就写成两个人，读用例时不用回头找


def test_rejected_or_hidden_row_is_invisible_to_everyone_but_the_author(db):
    assert vis.knowledge_point_visible("rejected", None, 甲, 甲) is True
    assert vis.knowledge_point_visible("rejected", None, 乙, 甲) is False
    assert vis.knowledge_point_visible("hidden", None, 乙, 甲) is False
    assert vis.knowledge_point_visible("approved", None, 乙, 甲) is True


def test_dead_rows_do_not_appear_in_the_usable_names(db):
    """`usable_names()` 是导入预检与查重共用的那一份，死行必须不在里面。"""
    names = {name for _, name in KnowledgeRepo(db, 乙).usable_names()}
    assert "泰勒公式" not in names        # 被驳回（作者另有其人）
    assert "冲量定理" not in names        # 被下架
    assert "已删知识点" not in names      # 软删：作者本人也不该看见
    assert "牛顿定律" in names


def test_other_person_can_submit_the_same_name_and_it_is_the_one_they_see(db):
    """★ 死局的两半：乙能建（不撞锁），建的这条是活的；乙找同名只找到自己那条。"""
    add_user(db, 甲, "u51")
    add_user(db, 乙, "u52")
    dead = add_knowledge(db, 901, 1, "开氏温标", created_by=甲, status="rejected")
    fresh = KnowledgeRepo(db, 乙).submit(乙, 1, "开氏温标")
    assert fresh != dead
    assert KnowledgeRepo(db, 乙).find_usable(1, "开氏温标") == fresh
    assert KnowledgeRepo(db, 甲).find_usable(1, "开氏温标") == fresh   # 甲也看不到自己那条死的


def test_hidden_question_is_invisible_even_to_its_owner(db):
    """题这一格同理：被官方收起（`delisted_by`）之后连作者都读不到，
    所以它既不占"我的题目"的位置，也不会在还原时被当成"已经有一份了"。"""
    add_user(db, 甲, "u51")
    qid = add_question(db, 902, owner_id=甲, visibility="shared", delisted_by=9)
    assert QuestionRepo(db, 甲).mine_one(qid) is None
    assert QuestionRepo(db, 乙).any_visible(qid) is None


def test_import_lists_a_name_that_only_exists_as_someones_dead_row(db):
    """步 12 那个 bug 的正身：导入时不能被同名的死行顶掉，必须报"库里还没有"并给建。"""
    add_user(db, 甲, "u51")
    alice = uid_of(db, "u51")
    add_knowledge(db, 903, 1, "冲量定理", created_by=甲, status="hidden")
    text = ("type,subject,stem,options,answer,explanation,knowledge_points\n"
            'essay,数学,求冲量,[],{"text":"I=Ft"},,冲量定理\n')
    result = import_service.preview(db, "question", "csv", text)
    assert [item["name"] for item in result["missing"]] == ["冲量定理"]
    session_id = ImportSessionRepo(db, alice).start("question", "csv", "t.csv")
    ImportSessionRepo(db, alice).add_rows(session_id, result["rows"])
    counts = import_service.commit(db, alice, session_id, create_missing=True)
    assert counts["knowledge_points"] == 1
    linked = db.execute("SELECT knowledge_point_id FROM question_knowledge_point WHERE user_id=?",
                        (alice,)).fetchone()["knowledge_point_id"]
    assert linked == KnowledgeRepo(db, alice).find_usable(1, "冲量定理")
