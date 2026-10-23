# 步 21 演示：判分与耗时预选。
# 判分错不是显示错，是判分错，所以每条口径都要能单独钉住：竖线只切「同一个空的多种
# 写法」、斜杠永远不切、多选必须全对、耗时只预选不代提交。

import pytest

from config import schedule
from src.data.repository.mistake_repo import MistakeRepo
from src.data.repository.question_repo import QuestionRepo
from src.data.repository.study_attempt_repo import ReviewLogRepo
from src.domain import grading
from src.domain.question_types import registry
from src.services import question_service, review_service
from tests.conftest import add_user, csrf_token, sign_up, uid_of


@pytest.mark.parametrize("written", ["F=MA", " F=ma ", "F = ma"])
def test_case_spaces_and_fullwidth_are_folded(written):
    assert grading.plain(written) == "f=ma"


def test_punctuation_is_kept():
    # 逗号是内容的一部分：`1, 2` 与 `12` 是两回事，不能一视同仁地抹掉
    assert grading.plain("1, 2") != grading.plain("12")


def test_choice_requires_all_correct_but_ignores_order_and_case():
    answer = '{"letters":"AC"}'
    assert grading.grade_letters(answer, "AC")["right"] is True
    assert grading.grade_letters(answer, "ca")["right"] is True
    assert "少选" in grading.grade_letters(answer, "A")["detail"]
    assert "多选" in grading.grade_letters(answer, "ABC")["detail"]


def test_choice_empty_and_unparsable_inputs_do_not_crash():
    assert grading.grade_letters('{"letters":"B"}', "")["detail"] == "没作答"
    assert grading.grade_letters("null", "B") is None      # None = 机器判不了，交回人自评


def test_blank_one_line_per_gap_with_alternatives():
    answer = '[["连续","continues"],["不可导"]]'
    assert grading.grade_blanks(answer, "连续\n不可导")["right"] is True
    assert grading.grade_blanks(answer, "CONTINUES\n不可导")["right"] is True
    assert "第 1 空" in grading.grade_blanks(answer, "可导\n不可导")["detail"]


def test_slash_never_splits_an_answer():
    # 这条最值钱：1/2 要是被劈成 1 和 2，填 1 就会被判对
    assert grading.grade_blanks('[["1/2"]]', "1/2")["right"] is True
    assert grading.grade_blanks('[["1/2"]]', "1")["right"] is False
    assert grading.grade_blanks('[["1/2"]]', "2")["right"] is False


def test_partial_credit_switch_is_honoured(monkeypatch):
    answer = '[["甲"],["乙"]]'
    monkeypatch.setattr(schedule, "BLANK_PARTIAL_CREDIT", True)
    half = grading.grade_blanks(answer, "甲\n丙")
    assert half["right"] is True and half["full"] is False and half["score"] == 0.5
    monkeypatch.setattr(schedule, "BLANK_PARTIAL_CREDIT", False)
    assert grading.grade_blanks(answer, "甲\n丙")["right"] is False


def test_missing_lines_count_as_wrong_not_index_error():
    # 少写一行不该抛越界，要当成"那个空没填对"；部分给分开着时整题仍算"半对"
    verdict = grading.grade_blanks('[["甲"],["乙"]]', "甲")
    assert verdict["full"] is False and verdict["score"] == 0.5
    assert "第 2 空" in verdict["detail"] and "空）" in verdict["detail"]


def test_no_preselect_until_there_are_enough_samples():
    samples = [30] * (schedule.DURATION_MIN_SAMPLES - 1)
    assert grading.preselect_rating(30, samples)[0] is None


def test_preselect_bands_follow_the_config():
    history = [100] * 20                        # 中位 100 秒
    for seconds, expected in [(30, 1), (100, 2), (180, 3), (400, 4)]:
        assert grading.preselect_rating(seconds, history)[0] == expected, seconds


def test_one_afk_session_does_not_warp_the_baseline():
    # 离群点先按上限裁一刀再算中位数：一次挂机不该把整科基准拖飞
    history = [100] * 10 + [schedule.DURATION_CAP_SECONDS * 40]
    assert grading.preselect_rating(100, history)[1] <= schedule.DURATION_CAP_SECONDS


def test_three_types_registered_and_only_two_auto_gradable():
    assert set(registry.known()) == {"essay", "choice", "blank"}
    assert registry.get("choice").auto_gradable and registry.get("blank").auto_gradable
    assert registry.get("essay").grade('{"text":"答"}', "随便写") is None


def test_choice_validation_catches_the_bad_inputs():
    handler = registry.get("choice")
    assert handler.validate({"stem": "", "options": "甲\n乙", "answer": "A"})
    assert handler.validate({"stem": "题干", "options": "只有一个", "answer": "A"})
    assert handler.validate({"stem": "题干", "options": "甲\n乙", "answer": ""})
    assert handler.validate({"stem": "题干", "options": "甲\n乙", "answer": "D"})
    assert handler.validate({"stem": "题干", "options": "甲\n乙", "answer": "B"}) == []


def record(db, uid, qtype, **form):
    # 录一道题，返回（题号, 库里那行）
    defaults = {"subject_id": "1", "type": qtype, "explanation": ""}
    question_id = question_service.create(db, uid, dict(defaults, **form))
    return question_id, QuestionRepo(db, uid).mine_one(question_id)


def test_practice_is_graded_by_the_machine_not_by_the_button(db):
    # 点「做对了」但答案错了，仍按错的记：否则错题本永远收不进真正做错的题
    add_user(db, 71, "g21")
    question_id, row = record(db, 71, "choice", stem="1+1 等于几？", options="1\n2\n3",
                              answer="B")
    outcome = question_service.record_practice(db, 71, row, "right", "C")
    assert outcome["result"] == "wrong" and outcome["source"] == "auto"
    assert MistakeRepo(db, 71).active_for(question_id) is not None


def test_essay_still_relies_on_the_human_rating(db):
    add_user(db, 72, "g22")
    _question_id, row = record(db, 72, "essay", stem="简述牛顿第二定律。", answer="F=ma")
    outcome = question_service.record_practice(db, 72, row, "wrong", "我写的内容")
    assert outcome["source"] == "manual" and outcome["verdict"] is None
    got = db.execute("SELECT grade_source FROM study_attempt WHERE user_id=72"
                     " ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert got == "manual"


def test_retract_only_works_for_an_unreviewed_auto_enqueued_mistake(db):
    add_user(db, 73, "g23")
    question_id, _row = record(db, 73, "blank", stem="填：__ 和 __", answer="光滑\n不可导")
    mistake_id = review_service.record_attempt(db, 73, question_id, 1, "wrong", "乱填")
    assert review_service.retract_wrong(db, 73, mistake_id) is True
    assert MistakeRepo(db, 73).active_for(question_id) is None
    # 收 = 软删：review_log 还指着这条，不能物理删
    assert db.execute("SELECT deleted_at FROM mistake WHERE id=?",
                      (mistake_id,)).fetchone()[0] is not None

    second = review_service.record_attempt(db, 73, question_id, 1, "wrong", "又乱填")
    db.execute("UPDATE mistake SET review_count=1 WHERE id=?", (second,))
    db.commit()
    assert review_service.retract_wrong(db, 73, second) is False    # 复习过的不给收
    assert MistakeRepo(db, 73).active_for(question_id)["id"] == second


def test_rating_source_records_whether_the_human_overrode_the_machine(db):
    # 人改判率是这步的副产品：点默认档 = duration_default，点别的 = user_override
    add_user(db, 74, "g24")
    question_id, _row = record(db, 74, "essay", stem="证明题", answer="过程")
    mistake_id = review_service.record_attempt(db, 74, question_id, 1, "wrong", "")
    for seconds in range(1, 13):                    # 攒够样本，预选才会生效
        review_service.rate(db, 74, mistake_id, 2, seconds)
    log = ReviewLogRepo(db, 74)
    assert len(log.durations_for_subject(1)) >= schedule.DURATION_MIN_SAMPLES
    review_service.rate(db, 74, mistake_id, 2, 120, rating_source="duration_default")
    review_service.rate(db, 74, mistake_id, 4, 120, rating_source="user_override")
    last_two = [row["rating_source"] for row in log.rows(order="id DESC", limit=2)]
    assert last_two == ["user_override", "duration_default"]


def test_answer_page_shows_verdict_and_retract_button(client, db):
    # 页面层：机器判分的话、「我其实答对了」按钮都得真的在页面上
    sign_up(client, username="g25")
    alice = uid_of(db, "g25")
    question_id, _row = record(db, alice, "choice", stem="下列正确的是（　）",
                               options="甲\n乙\n丙", answer="B", explanation="乙对")
    mistake_id = review_service.record_attempt(db, alice, question_id, 1, "wrong", "")
    token = csrf_token(client, f"/review/card/{mistake_id}")
    page = client.post(f"/review/card/{mistake_id}/reveal",
                       data={"started": "0", "submitted": "C", "csrf_token": token})
    body = page.get_data(as_text=True)
    assert "机器判分：错了" in body and "少选 B" in body
    assert "我其实答对了" in body
    assert "乙对" in body                                  # 解析照常给
    assert client.post(f"/review/card/{mistake_id}/retract",
                       data={"csrf_token": token}).status_code == 302
    assert MistakeRepo(db, alice).active_for(question_id) is None
