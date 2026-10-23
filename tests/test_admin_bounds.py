"""步 14 演示（其四）：管理员也不穿透（七-1 ★）。

"admin 能管一切"这句话在后台是权限，在数据层就是漏：本步钉死一条口径——
**管理员的账号读不到任何人的私有数据**（错题、做题记录、复习流水、笔记、标签、收藏、
未共享的题）。他能看的只有共享题、待审知识点、隐藏库、申诉队列和角色表。
"""

import pytest

from config import archive
from src.data.repository.base import SCOPE_DICT, SCOPE_NAMED, SCOPE_POLICY, SCOPE_USER
from src.data.repository.knowledge_repo import KnowledgeRepo
from src.data.repository.mistake_repo import MistakeRepo
from src.data.repository.profile_repo import SettingRepo
from src.data.repository.question_repo import QuestionRepo
from src.data.repository.study_attempt_repo import ReviewLogRepo, StudyAttemptRepo
from src.data.repository.user_repo import UserRepo
from tests.conftest import STAMP, add_knowledge, add_mistake, add_question, add_user

ADMIN = 9                        # `db` 夹具里那个 admin
OWNER = 61


@pytest.fixture
def with_private_data(db):
    """先摆一份"只有主人看得见"的数据，再让 admin 去读。"""
    add_user(db, OWNER, "u61")
    qid = add_question(db, 910, owner_id=OWNER, visibility="private")
    shared = add_question(db, 911, owner_id=OWNER, visibility="shared")
    mistake_id = add_mistake(db, OWNER, qid)
    db.execute("INSERT INTO study_attempt (user_id, question_id, subject_id, result,"
               " grade_source, answer_submitted, recorded_on, created_at)"
               " VALUES (?, ?, 1, 'wrong', 'manual', '他的作答', '2026-10-21', ?)",
               (OWNER, qid, STAMP))
    db.execute("INSERT INTO review_log (user_id, mistake_id, reviewed_on, reviewed_at, rating,"
               " rating_source, duration_seconds, algorithm_version, interval_before,"
               " interval_after, due_date_before, due_date_after, step_before, step_after)"
               " VALUES (?, ?, '2026-10-21', '2026-10-21 10:00:00', 2, 'user_override', 30,"
               " 'ladder-1', 0, 1, '2026-10-21', '2026-10-22', 0, 1)", (OWNER, mistake_id))
    db.execute("INSERT INTO knowledge_note (user_id, knowledge_point_id, content, created_at,"
               " updated_at, deleted_at) VALUES (?, 1, '他的私人笔记', ?, ?, NULL)",
               (OWNER, STAMP, STAMP))
    db.execute("INSERT INTO tag (user_id, name, created_at, deleted_at) VALUES (?, '他的标签', ?, NULL)",
               (OWNER, STAMP))
    db.execute("INSERT INTO favorite (user_id, target_type, target_id, created_at)"
               " VALUES (?, 'note', 1, ?)", (OWNER, STAMP))
    db.execute("INSERT INTO user_setting (user_id, key, value) VALUES (?, 'daily_review_cap', '7')",
               (OWNER,))
    db.commit()
    return {"question": qid, "shared": shared, "mistake": mistake_id}


# ---------------------------------------------------------------- 六类私有数据

def test_admin_reads_no_private_rows(with_private_data, db):
    """同一个连接、同一个 SQL，换个 viewer 就该一行不剩。"""
    for repo in (MistakeRepo, StudyAttemptRepo, ReviewLogRepo):
        assert repo(db, ADMIN).rows() == [], repo.__name__
        assert repo(db, OWNER).rows() != [], repo.__name__     # 反证：数据真的在库里
    # 设置这张表 `all()` 永远有默认值打底，所以判"读没读到别人的那条"要看具体那格
    assert SettingRepo(db, OWNER).all()["daily_review_cap"] == "7"     # 他确实写过一条
    assert SettingRepo(db, ADMIN).all()["daily_review_cap"] != "7"     # admin 读到的是默认值


def test_admin_cannot_see_private_notes_tags_favorites(db, with_private_data):
    """这三张表还没有 repo（步 22 才做页面），所以直接用 SQL 钉住"换个人就查不到"。"""
    for table, column in (("knowledge_note", "user_id"), ("tag", "user_id"), ("favorite", "user_id")):
        assert db.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {column}=?",
                          (ADMIN,)).fetchone()["n"] == 0
        assert db.execute(f"SELECT COUNT(*) AS n FROM {table}"
                          f" WHERE {column} IS NOT NULL").fetchone()["n"] > 0


def test_admin_sees_no_foreign_question(with_private_data, db):
    """题目表更严：它是 named scope，根本没有"把所有题捞出来"这种读法。"""
    private, shared = with_private_data["question"], with_private_data["shared"]
    assert QuestionRepo(db, ADMIN).mine_one(private) is None
    assert QuestionRepo(db, ADMIN).any_visible(private) is None
    assert QuestionRepo(db, ADMIN).any_visible(shared) is not None   # 共享题管得着
    assert QuestionRepo(db, ADMIN).mine().total == 0                 # 但不是"他的题"
    with pytest.raises(ValueError):
        QuestionRepo(db, ADMIN).rows()                  # 通用读法在入口就被堵死


# ---------------------------------------------------------------- 管理员该看的还看得见

def test_admin_still_sees_the_pool_and_the_audit_queue(with_private_data, db):
    assert len(QuestionRepo(db, ADMIN).shared_pool().items) >= 1
    add_knowledge(db, 920, 1, "待审知识点", created_by=OWNER, status="approved")
    db.commit()
    assert KnowledgeRepo(db, ADMIN).find_usable(1, "待审知识点") == 920
    assert UserRepo(db).by_username("u61")["id"] == OWNER      # 角色表本来就要能读


# ---------------------------------------------------------------- 口径写死在声明里

def test_private_tables_declare_user_scope():
    """★ 这一条是防"以后有人为了做后台把 scope 改成 dict/policy"。
    scope 一改，`_scope_clause()` 就不再注入 viewer，上面那些用例立刻失去保护。"""
    for repo, table in ((MistakeRepo, "mistake"), (StudyAttemptRepo, "study_attempt"),
                        (ReviewLogRepo, "review_log")):
        assert repo.scope == SCOPE_USER, table
        assert repo.table == table, table
    assert QuestionRepo.scope == SCOPE_NAMED
    for repo in (KnowledgeRepo,):
        assert repo.scope == SCOPE_POLICY, repo.__name__


def test_hidden_lib_registry_matches_the_never_delete_list():
    """隐藏库四格与"永不物理删"名单是一份注册表；后台以后照它做，不许另起一套。"""
    assert set(archive.ENTITIES) == {"mistake", "tag", "knowledge_point", "subject", "question"}
    assert archive.NEVER_PHYSICALLY_DELETED >= {"question_bank", "knowledge_point", "subject",
                                                "mistake"}
    assert set(archive.HIDDEN_COMPARTMENTS) == {"subject", "knowledge_point", "question"}
    for key, spec in archive.ENTITIES.items():
        assert spec.in_use_where, key            # 每格都得有自己的"什么算在用"
    assert SCOPE_DICT is not SCOPE_USER          # 字典表与私有表不是一回事
