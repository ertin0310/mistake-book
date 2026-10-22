"""复习日与时间点生效规则的测试（方案三-3、铁律 2）。

日期全部由参数捏出来，不碰数据库、不读墙上时钟。
"""

from datetime import date, datetime

import pytest

from src.domain import clock

DAY = date(2026, 10, 19)


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute)


# ---------------------------------------------------------------- 复习日归属

def test_default_rollover_equals_calendar_day():
    """默认 00:00：复习日恒等于自然日，凌晨也不例外。"""
    assert clock.compute_review_date(at(DAY, 0, 0), "00:00") == DAY
    assert clock.compute_review_date(at(DAY, 3, 30), "00:00") == DAY
    assert clock.compute_review_date(at(DAY, 23, 59), "00:00") == DAY


def test_evening_rollover_before_cut_off_belongs_to_yesterday():
    """T=20:00 时，10/19 下午 14:00 打开看到的是 10/18 那批。"""
    assert clock.compute_review_date(at(DAY, 14, 0), "20:00") == date(2026, 10, 18)


def test_evening_rollover_at_and_after_cut_off():
    """10/19 20:00 一到，刷出的就是 10/19 这批；23:59 仍属今天。"""
    assert clock.compute_review_date(at(DAY, 20, 0), "20:00") == DAY
    assert clock.compute_review_date(at(DAY, 23, 59), "20:00") == DAY


def test_next_early_morning_still_yesterday():
    """次日凌晨 00:30 还没到新批次，仍属前一天。"""
    assert clock.compute_review_date(at(date(2026, 10, 20), 0, 30), "20:00") == DAY


# ---------------------------------------------------------------- 脏值兜底

@pytest.mark.parametrize("bad", ["", None, "25:00", "12:75", "八点", "20", "abc"])
def test_parse_hhmm_falls_back_to_default(bad):
    assert clock.parse_hhmm(bad) == "00:00"


def test_parse_hhmm_normalizes_single_digit_hour():
    assert clock.parse_hhmm("8:5") == "08:05"


# ---------------------------------------------------------------- 到期判定

def test_due_on_the_day_counts_as_due():
    assert clock.is_due("2026-10-19", DAY) is True


def test_due_in_the_future_is_not_due():
    assert clock.is_due("2026-10-20", DAY) is False


def test_overdue_is_due():
    assert clock.is_due("2026-10-16", DAY) is True


# ---------------------------------------------------------------- 改动何时生效

def test_change_before_cut_off_applies_today():
    """14:00 改（原 T=20:00，还没过）→ 当日立即生效，不留待生效值。"""
    change = clock.decide_rollover_change("20:00", "04:00", at(DAY, 14, 0))
    assert change.apply_immediately is True
    assert change.effective_value == "04:00"
    assert change.pending_value is None


def test_change_after_cut_off_applies_tomorrow():
    """21:00 改（已过原 T）→ 今天这一轮不能中途换轨，挂到明天。"""
    change = clock.decide_rollover_change("20:00", "04:00", at(DAY, 21, 0))
    assert change.apply_immediately is False
    assert change.effective_value == "20:00"
    assert change.pending_value == "04:00"
    assert change.pending_from == "2026-10-20"


def test_default_rollover_always_defers_to_tomorrow():
    """★ 默认 00:00 时"当日生效"这条路一次都走不到（"现在 < 00:00"恒为假）。

    这不是 bug，但很容易被当成 bug，所以用断言钉住：没改过时间点的用户
    改设置一律次日生效。哪天有人觉得这里"应该立即生效"，会先撞见这条测试。
    """
    for hour in (0, 8, 14, 23):
        change = clock.decide_rollover_change("00:00", "20:00", at(DAY, hour, 30))
        assert change.apply_immediately is False, f"{hour} 点改设置不该立即生效"
        assert change.pending_from == "2026-10-20"


# ---------------------------------------------------------------- 待生效值的采纳

def test_pending_is_adopted_on_the_day():
    result = clock.resolve_rollover("20:00", "04:00", "2026-10-20", at(date(2026, 10, 20), 1, 0))
    assert result.rollover_time == "04:00"
    assert result.should_clear_pending is True


def test_pending_is_not_adopted_before_the_day():
    result = clock.resolve_rollover("20:00", "04:00", "2026-10-20", at(DAY, 23, 0))
    assert result.rollover_time == "20:00"
    assert result.should_clear_pending is False


def test_no_pending_keeps_current():
    result = clock.resolve_rollover("20:00", None, None, at(date(2026, 10, 25), 9, 0))
    assert result.rollover_time == "20:00"
    assert result.should_clear_pending is False


def test_adopted_pending_with_dirty_value_falls_back():
    """待生效值本身是脏的，也不能把异常抛到页面上。"""
    result = clock.resolve_rollover("20:00", "乱填", "2026-10-20", at(date(2026, 10, 21), 9, 0))
    assert result.rollover_time == "00:00"


# ---------------------------------------------------------------- 时区回落（三-3 ★）

def test_empty_timezone_falls_back_to_local():
    assert clock.resolve_timezone(None) is None
    assert clock.resolve_timezone("") is None
    assert clock.resolve_timezone("   ") is None


def test_unrecognized_timezone_falls_back_not_raises():
    """认不出来只回落本机，不报错——时区是"存了暂时也不生效"的偏好项，
    为它弹一个错误页，用户只会以为程序坏了。"""
    assert clock.resolve_timezone("火星/标准时") is None
    assert clock.resolve_timezone("Asia/Shangai") is None      # 少一个 h


def test_real_timezone_returns_tzinfo():
    tz = clock.resolve_timezone("Asia/Shanghai")
    assert tz is not None and str(tz) == "Asia/Shanghai"
