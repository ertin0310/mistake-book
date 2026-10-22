"""步 6 演示：四档各动多少、顶格夹住、★ 评完不许当天回队。

`MIN_INTERVAL_AFTER_REVIEW` 那条是 2026-10-22 发现并补的洞：台阶第 0 级间隔是 0 天，
新入队要靠它做到"当天就出现在今日复习"，但**评完**还落回 0 级就会当天回队出不去。
"""

from datetime import date

import pytest

from config import schedule
from src.domain.scheduling import registry
from src.domain.scheduling.base import ReviewState
from src.domain.scheduling.ladder import next_state

TODAY = date(2026, 10, 22)


def state(step):
    return ReviewState(step_index=step, interval_days=schedule.LADDER_INTERVALS[step],
                       due_date=TODAY)


def move(step, rating):
    return next_state(step, TODAY, rating, TODAY)


# ---------------------------------------------------------------- 四档

def test_rating_one_jumps_two_rungs():
    after = move(4, 1).after          # 第 4 级（7 天）
    assert after.step_index == 6 and after.interval_days == 30
    assert after.due_date == date(2026, 11, 21)


def test_rating_two_jumps_one_rung():
    after = move(4, 2).after
    assert after.step_index == 5 and after.interval_days == 15


def test_rating_three_steps_back_one_rung():
    after = move(4, 3).after
    assert after.step_index == 3 and after.interval_days == 4


def test_rating_four_resets_and_records_lapse():
    result = move(4, 4)
    assert result.after.step_index == 0
    assert result.lapsed is True
    assert result.after.due_date == date(2026, 10, 23)      # ★ 明天，不是今天


@pytest.mark.parametrize("rating", [1, 2, 3])
def test_only_rating_four_records_a_lapse(rating):
    assert move(4, rating).lapsed is False


# ---------------------------------------------------------------- ★ 出不去那条

def test_step_zero_rating_three_does_not_return_same_day():
    """第 0 级退无可退 → 夹回 0，但间隔至少 1 天，所以明天才回来。"""
    after = move(0, 3).after
    assert after.step_index == 0
    assert after.due_date == date(2026, 10, 23)


def test_step_one_rating_three_does_not_return_same_day():
    after = move(1, 3).after
    assert after.step_index == 0 and after.interval_days == 1


def test_new_mistake_still_shows_up_today():
    """入队不是"评完"：新错题仍然 `due_date = 当前复习日`，当天就出现在今日复习里
    （v7 三-13 那条 30 分的演示判据不受 `MIN_INTERVAL_AFTER_REVIEW` 影响）。"""
    assert schedule.LADDER_INTERVALS[0] == 0


# ---------------------------------------------------------------- 夹住与报错

def test_top_rung_is_clamped_at_sixty_days():
    after = move(7, 1).after
    assert after.step_index == 7 and after.interval_days == 60
    assert after.due_date == date(2026, 12, 21)


def test_six_rung_rating_one_clamps_instead_of_crashing():
    assert move(6, 1).after.step_index == 7


def test_unknown_rating_raises():
    for bad in (0, 5, "1", None):
        with pytest.raises(ValueError):
            move(4, bad)


# ---------------------------------------------------------------- 接口与注册表

def test_move_carries_algorithm_version_for_review_log():
    result = move(4, 2)
    assert result.algorithm_version == "ladder-1"
    assert (result.before.step_index, result.after.step_index) == (4, 5)


def test_registry_default_is_ladder_and_rejects_unknown():
    assert registry.get().name == "ladder"
    assert registry.get("ladder") is registry.get()
    with pytest.raises(ValueError):
        registry.get("sm2")


def test_strategy_is_pure_same_input_same_output():
    """纯函数：不查库、不读时钟，所以重放 45 天历史能得到一模一样的序列。"""
    first = move(3, 2)
    second = move(3, 2)
    assert first == second


def test_intervals_come_from_config_not_from_code():
    """改台阶不动算法：把配置里的顶格改掉，算法跟着变。"""
    original = schedule.LADDER_INTERVALS
    try:
        schedule.LADDER_INTERVALS = [0, 1, 2, 4, 7, 15, 30, 45]
        assert move(7, 1).after.interval_days == 45
    finally:
        schedule.LADDER_INTERVALS = original
