"""步 18 演示：知识点全套（提交即入池、审核队列、查重与「这不是同一个知识点」）。

这一页最容易被做成"管理员点通过之后才可用"，那会让新用户提交完什么也挂不上，
所以三-6 定的是**提交即 `approved`**，审核只决定它以后还在不在池子里。
"""

import pytest

from config import prompts
from src.data.repository.knowledge_repo import KnowledgeRepo
from src.domain.errors import NotFoundError, ValidationError
from src.services import knowledge_service
from tests.conftest import add_subject, add_user, csrf_token, sign_up, uid_of

甲, 乙 = 71, 72


def submit(conn, user_id, name, subject_id=1, not_same=None):
    return knowledge_service.create(conn, user_id, {"subject_id": str(subject_id), "name": name,
                                                    "not_same": not_same})


# ---------------------------------------------------------------- 提交即入池

def test_a_new_submission_is_usable_immediately_and_queued(db):
    add_user(db, 甲, "u71")
    add_user(db, 乙, "u72")
    new_id = submit(db, 甲, "高斯公式")["id"]
    assert new_id
    # 别人立刻能用（不是"等管理员点通过"）
    assert KnowledgeRepo(db, 乙).find_usable(1, "高斯公式") == new_id
    # 同时它就在待审队列里：判据是 `reviewed_by IS NULL`，不是另一个状态
    assert new_id in {row["id"] for row in KnowledgeRepo(db).pending()}
    assert db.execute("SELECT status FROM knowledge_point WHERE id=?", (new_id,)).fetchone()[0] \
        == "approved"


def test_the_queue_is_exactly_the_unreviewed_rows(db):
    add_user(db, 甲, "u71")
    first = submit(db, 甲, "斯托尔兹定理")["id"]
    KnowledgeRepo(db, 甲).reject(first, 9, "名字与教材不一致")
    assert first not in {row["id"] for row in KnowledgeRepo(db).pending()}


# ---------------------------------------------------------------- 查重那颗勾

def test_same_name_offers_the_existing_row_instead_of_a_second_one(db):
    add_user(db, 甲, "u71")
    existing = submit(db, 甲, "牛顿第二定律")["id"]
    result = submit(db, 甲, "牛顿第二定律")
    assert result["id"] is None
    assert [row["id"] for row in result["duplicates"]] == [existing]


def test_the_tick_allows_the_same_name_under_another_subject(db):
    """勾了「这不是同一个知识点」之后，**换科目**才真能各留一条。"""
    add_user(db, 甲, "u71")
    add_subject(db, 61, "物理")
    submit(db, 甲, "极限存在定理", subject_id=1)
    assert submit(db, 甲, "极限存在定理", subject_id=1)["id"] is None
    second = submit(db, 甲, "极限存在定理", subject_id=61, not_same="1")
    assert second["id"] and second["duplicates"] == []


def test_the_tick_cannot_defeat_the_unique_index_in_one_subject(db):
    """同一科目下同名硬建第二条：库里那条索引说了算，服务层只把它翻成人话。"""
    add_user(db, 甲, "u71")
    submit(db, 甲, "叠加原理")
    with pytest.raises(ValidationError) as excinfo:
        submit(db, 甲, "叠加原理", not_same="1")
    assert prompts.KP_SAME_SUBJECT_CLASH == excinfo.value.message


@pytest.mark.parametrize("typed", ["牛顿 第二定律", "  牛顿第二定律  ", "牛顿第二定律"])
def test_dedup_runs_on_the_normalized_name(db, typed):
    add_user(db, 甲, "u71")
    submit(db, 甲, "牛顿第二定律")
    assert submit(db, 甲, typed)["id"] is None


def test_no_fuzzy_matching_on_purpose(db):
    """★ 已知边界：「牛顿第二定律」与「牛顿第二定律的应用」是两条，有意不做近似匹配。"""
    add_user(db, 甲, "u71")
    submit(db, 甲, "牛顿第二定律")
    assert submit(db, 甲, "牛顿第二定律的应用")["id"]


# ---------------------------------------------------------------- 改名重提

def test_author_edit_sends_it_back_to_the_queue(db):
    add_user(db, 甲, "u71")
    point_id = submit(db, 甲, "泰勒公式")["id"]
    KnowledgeRepo(db, 甲).reject(point_id, 9, "写错了")
    knowledge_service.rename(db, 甲, point_id, "泰勒展开式")
    row = db.execute("SELECT name, status, reviewed_by, review_note FROM knowledge_point"
                     " WHERE id=?", (point_id,)).fetchone()
    assert row["name"] == "泰勒展开式" and row["status"] == "approved"
    assert row["reviewed_by"] is None and row["review_note"] is None   # 审核痕迹清空 → 重新排队
    assert point_id in {item["id"] for item in KnowledgeRepo(db).pending()}


def test_cannot_rename_someone_elses_point(db):
    add_user(db, 甲, "u71")
    add_user(db, 乙, "u72")
    point_id = submit(db, 甲, "雅可比矩阵")["id"]
    with pytest.raises(NotFoundError):
        knowledge_service.rename(db, 乙, point_id, "我改的名字")
    assert KnowledgeRepo(db, 甲).find_usable(1, "雅可比矩阵") == point_id


def test_empty_name_is_rejected(db):
    add_user(db, 甲, "u71")
    with pytest.raises(ValidationError):
        knowledge_service.rename(db, 甲, 1, "   ")


# ---------------------------------------------------------------- 死局不再出现

def test_a_rejected_row_never_blocks_its_own_author(db):
    """三-6 那个死局的正身：作者自己也不能被那条被驳回的行顶掉。"""
    add_user(db, 甲, "u71")
    dead = submit(db, 甲, "冲量定理")["id"]
    KnowledgeRepo(db, 甲).reject(dead, 9, "与教材叫法不一致")
    fresh = submit(db, 甲, "冲量定理")["id"]
    assert fresh and fresh != dead
    assert KnowledgeRepo(db, 甲).find_usable(1, "冲量定理") == fresh


def test_hidden_point_disappears_from_the_pool_but_stays_with_its_author(db):
    add_user(db, 甲, "u71")
    add_user(db, 乙, "u72")
    point_id = submit(db, 甲, "傅里叶积分")["id"]
    db.execute("UPDATE knowledge_point SET status='hidden', reviewed_by=9 WHERE id=?", (point_id,))
    db.commit()
    assert KnowledgeRepo(db, 乙).find_usable(1, "傅里叶积分") is None
    assert KnowledgeRepo(db, 甲).find_usable(1, "傅里叶积分") is None      # 作者也不能再挂它
    assert point_id in {row["id"] for row in KnowledgeRepo(db, 甲).submitted_by(甲)}


# ---------------------------------------------------------------- 页面

def test_knowledge_pages_need_login(client):
    assert client.get("/knowledge/").status_code == 302
    assert client.get("/knowledge/mine").status_code == 302


def test_submitting_through_the_page_lands_in_the_pool(client, db):
    sign_up(client, username="stu")
    alice = uid_of(db, "stu")
    response = client.post("/knowledge/", data={
        "subject_id": "1", "name": "洛必达法则",
        "csrf_token": csrf_token(client, "/knowledge/")})
    assert response.status_code == 302
    assert KnowledgeRepo(db, alice).find_usable(1, "洛必达法则")
    assert "洛必达法则" in client.get("/knowledge/").get_data(as_text=True)
    assert "我的知识点申请" in client.get("/knowledge/mine").get_data(as_text=True)


def test_the_page_shows_the_existing_option_when_the_name_is_taken(client, db):
    sign_up(client, username="stu")
    client.post("/knowledge/", data={"subject_id": "1", "name": "柯西中值定理",
                                     "csrf_token": csrf_token(client, "/knowledge/")})
    token = csrf_token(client, "/knowledge/")
    response = client.post("/knowledge/", data={"subject_id": "1", "name": "柯西中值定理",
                                                "csrf_token": token})
    body = response.get_data(as_text=True)
    assert response.status_code == 400
    assert prompts.KP_EXISTS.split("{")[0].strip() in body      # "这一科下已经有同名知识点"
    assert "柯西中值定理" in body                                # 可选项列出来了
    assert prompts.KP_NOT_SAME in body                          # 那颗勾就在旁边
    clash = client.post("/knowledge/", data={"subject_id": "1", "name": "柯西中值定理",
                                             "not_same": "1",
                                             "csrf_token": csrf_token(client, "/knowledge/")})
    assert clash.status_code == 400                              # 同一科目勾了也建不出第二条
    assert prompts.KP_SAME_SUBJECT_CLASH in clash.get_data(as_text=True)


def test_rename_form_on_my_page(client, db):
    sign_up(client, username="stu")
    alice = uid_of(db, "stu")
    client.post("/knowledge/", data={"subject_id": "1", "name": "格林公式",
                                     "csrf_token": csrf_token(client, "/knowledge/")})
    point_id = KnowledgeRepo(db, alice).find_usable(1, "格林公式")
    body = client.get("/knowledge/mine").get_data(as_text=True)
    assert f"/knowledge/rename/{point_id}" in body
    client.post(f"/knowledge/rename/{point_id}", data={
        "name": "格林第一公式", "csrf_token": csrf_token(client, "/knowledge/mine")})
    assert KnowledgeRepo(db, alice).find_usable(1, "格林第一公式") == point_id
    assert KnowledgeRepo(db, alice).find_usable(1, "格林公式") is None
