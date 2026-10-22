"""步 10 演示：改与删 + 设置页 + 统一异常出口。

判据是"非法输入全是友好提示且程序不崩"：空题干、上限填 9999、时间填 25:99、
直接访问别人的题目网址——四种都要看到中文，且响应里不能出现 traceback。
"""

import pytest

from config import prompts, user_fields
from src.data.repository.question_repo import QuestionRepo
from src.data.repository.profile_repo import SettingRepo
from src.domain import clock
from src.services import profile_service
from src.domain.errors import ValidationError
from tests.conftest import csrf_token, sign_up


def body_of(response):
    return response.get_data(as_text=True)


def uid_of(db, username):
    """注册出来的用户 id 由 SQLite 自增决定（fixture 里已经有 1/2/9），不能写死。"""
    return db.execute("SELECT id FROM user WHERE username=?", (username,)).fetchone()["id"]


# ---------------------------------------------------------------- 校验器本身

def test_validator_rejects_dirty_time_and_out_of_range_cap():
    time_field = user_fields.field_by_key("review_time")
    cap_field = user_fields.field_by_key("daily_review_cap")
    assert profile_service.clean(time_field, "8:30") == "08:30"
    with pytest.raises(ValidationError) as exc:
        profile_service.clean(time_field, "25:99")
    assert exc.value.message == prompts.INVALID_TIME
    with pytest.raises(ValidationError):
        profile_service.clean(cap_field, "9999")
    with pytest.raises(ValidationError):
        profile_service.clean(cap_field, "字母")


def test_default_rollover_always_defers(db):
    """★ 默认 00:00 下"当日生效"这条路一次都走不到（不是 bug，README 要写）。"""
    change = profile_service.rollover_change("00:00", "20:00")
    assert change.apply_immediately is False and change.pending_value == "20:00"


# ---------------------------------------------------------------- 改与删

def test_edit_changes_the_stem_in_place(client, db):
    sign_up(client, username="stu")
    client.post("/study/new", data={"subject_id": "1", "type": "essay", "stem": "原题",
                                    "answer": "答案", "explanation": "",
                                    "csrf_token": csrf_token(client, "/study/new")})
    qid = db.execute("SELECT id FROM question_bank WHERE stem='原题'").fetchone()["id"]

    page = client.get(f"/study/edit/{qid}")
    assert page.status_code == 200 and "原题" in body_of(page)     # 控件里回填了现值
    client.post(f"/study/edit/{qid}", data={"subject_id": "1", "type": "essay",
                                            "stem": "改过的题", "answer": "答案",
                                            "explanation": "",
                                            "csrf_token": csrf_token(client, f"/study/edit/{qid}")})
    assert QuestionRepo(db, uid_of(db, "stu")).mine_one(qid)["stem"] == "改过的题"


def test_delete_is_a_soft_delete_only_the_owner_can_do(client, db):
    sign_up(client, username="stu")
    client.post("/study/new", data={"subject_id": "1", "type": "essay", "stem": "要删的题",
                                    "answer": "答案", "explanation": "",
                                    "csrf_token": csrf_token(client, "/study/new")})
    qid = db.execute("SELECT id FROM question_bank WHERE stem='要删的题'").fetchone()["id"]
    client.post(f"/study/delete/{qid}", data={"csrf_token": csrf_token(client, "/study/")})

    row = db.execute("SELECT deleted_at, deleted_by FROM question_bank WHERE id=?", (qid,)).fetchone()
    assert row["deleted_at"] is not None and row["deleted_by"] == uid_of(db, "stu")  # 谁按的按钮留痕
    assert "要删的题" not in body_of(client.get("/study/"))
    assert db.execute("SELECT 1 FROM question_bank WHERE id=?", (qid,)).fetchone() is not None


def test_cannot_edit_someone_elses_question(client):
    """别人的题和不存在给同一个 404 页，不透露"存在但不属于你"（方案七-1）。"""
    sign_up(client, username="owner")
    client.post("/study/new", data={"subject_id": "1", "type": "essay", "stem": "别人的题",
                                    "answer": "答案", "explanation": "",
                                    "csrf_token": csrf_token(client, "/study/new")})
    qid = 1                                                   # fixture 里 u1 的题，不是 owner 的
    sign_up(client, username="intruder")
    body = body_of(client.get(f"/study/edit/{qid}"))
    assert "这条记录不在你的错题本里" in body and "Traceback" not in body


# ---------------------------------------------------------------- 设置页

def test_settings_page_lists_declared_fields(client):
    sign_up(client, username="stu")
    body = body_of(client.get("/settings/"))
    assert "每日复习量上限" in body and "每日复习时间" in body and "时区" in body
    assert "暂时" in body or "不参与计算" in body              # 时区本期只存不算，页面上要讲明白


def test_settings_saves_a_valid_cap(client, db):
    sign_up(client, username="stu")
    response = client.post("/settings/", data={"daily_review_cap": "50", "review_time": "09:00",
                                               "time_zone": "Asia/Shanghai",
                                               "csrf_token": csrf_token(client, "/settings/")})
    assert response.status_code == 302
    values = SettingRepo(db, uid_of(db, "stu")).all()
    assert values["daily_review_cap"] == "50"
    assert values["time_zone"] == "Asia/Shanghai"


def test_settings_rejects_out_of_range_cap_with_chinese(client, db):
    sign_up(client, username="stu")
    body = body_of(client.post("/settings/", data={
        "daily_review_cap": "9999", "review_time": "25:99", "time_zone": "",
        "csrf_token": csrf_token(client, "/settings/")}))
    assert prompts.OUT_OF_RANGE in body and prompts.INVALID_TIME in body
    assert "Traceback" not in body
    assert SettingRepo(db, uid_of(db, "stu")).all()["daily_review_cap"] == "30"   # 没被脏值写进去


def test_rollover_change_is_parked_until_tomorrow(client, db):
    """默认 00:00 时改时间点一律挂到明天：今天已刷完的题不会又冒出来。"""
    sign_up(client, username="stu")
    client.post("/settings/", data={"daily_review_cap": "30", "review_time": "20:00",
                                    "time_zone": "", "csrf_token": csrf_token(client, "/settings/")})
    stored = SettingRepo(db, uid_of(db, "stu")).all()
    assert stored["review_time"] != "20:00"
    assert stored.get("review_time_pending") == "20:00"
    assert stored.get("review_time_pending_from") == clock.shift_days(
        clock.review_date_of("00:00"), 1).isoformat()


# ---------------------------------------------------------------- 异常出口

def test_unknown_url_gives_a_chinese_page_not_a_traceback(client):
    sign_up(client, username="stu")
    body = body_of(client.get("/no/such/page"))
    assert "404" in body and "这条记录不在你的错题本里" in body and "Traceback" not in body
