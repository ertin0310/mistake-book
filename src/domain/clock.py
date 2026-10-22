"""全项目唯一的时间入口（方案二-6）。

别的文件不许自己 `date.today()` / `datetime.now()`：一个"今天"的口径散在十几处，
漏改一处就会出现"时间点之前看到了明天的题"这类极难复现的 bug。
除 `now()` 外全是纯函数——日期由调用方传进来，测试能把"今天"捏成任何一天。
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

DEFAULT_ROLLOVER = "00:00"


def now() -> datetime:
    """全项目唯一允许读墙上时钟的地方。二期启用时区换算只改这一行（方案三-3）。"""
    return datetime.now()


def today() -> date:
    return now().date()


def to_date_str(day: date) -> str:
    """`due_date` 只存 YYYY-MM-DD，不带时刻。"""
    return day.isoformat()


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def parse_hhmm(value: str | None, fallback: str = DEFAULT_ROLLOVER) -> str:
    """校验 "20:00" 这类串；脏值一律退回默认，宁可按自然日切，也不让队列算不出来。"""
    if not value:
        return fallback
    hour_text, _, minute_text = value.strip().partition(":")
    try:
        hour, minute = int(hour_text), int(minute_text)
    except ValueError:
        return fallback
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return f"{hour:02d}:{minute:02d}"
    return fallback


def rollover_moment(day: date, rollover_time: str) -> datetime:
    hour_text, _, minute_text = parse_hhmm(rollover_time).partition(":")
    return datetime(day.year, day.month, day.day, int(hour_text), int(minute_text))


def compute_review_date(moment: datetime, rollover_time: str) -> date:
    """此刻属于哪个复习日：到了切换点算今天，没到算昨天。

    默认 00:00 时恒等于自然日，与"按服务器本地日期"向后兼容。
    """
    if moment >= rollover_moment(moment.date(), rollover_time):
        return moment.date()
    return moment.date() - timedelta(days=1)


def review_date_of(rollover_time: str) -> date:
    """不传参就取当前复习日的唯一便捷入口。"""
    return compute_review_date(now(), rollover_time)


def is_due(due_date: str, review_date: date) -> bool:
    """到期判定 `due_date <= 复习日`。两边都是 YYYY-MM-DD，字典序即日期序，直接比字符串。"""
    return due_date <= review_date.isoformat()


def shift_days(day: date, days: int) -> date:
    return day + timedelta(days=days)


@dataclass(frozen=True)
class RolloverChange:
    """用户改切换时刻的决定：立即生效还是挂待生效。只描述，不写库。"""

    apply_immediately: bool
    effective_value: str
    pending_value: str | None
    pending_from: str | None


def decide_rollover_change(current: str, requested: str, moment: datetime) -> RolloverChange:
    """方案三-3：改的时刻还没过原时间点 → 当日立即生效；已过 → 次日生效。

    为什么要分：20:00 之后才改若立即生效，"今天"会退化成"昨天"，
    今天已刷完的题会再冒出来、记录也会掉进另一天的格子。

    ★ 默认 00:00 时"现在 < 今天 00:00"恒不成立，所以从没改过时间点的用户
      改设置一律次日生效，"当日生效"这条路一次都走不到。不是 bug，但要写进
      README 和测试，否则第一个测试就以为它坏了。
    """
    requested = parse_hhmm(requested)
    current = parse_hhmm(current)
    if moment.time() < rollover_moment(moment.date(), current).time():
        return RolloverChange(True, requested, None, None)
    return RolloverChange(False, current, requested,
                          (moment.date() + timedelta(days=1)).isoformat())


@dataclass(frozen=True)
class EffectiveRollover:
    """当前该用哪个切换时刻，以及要不要清掉待生效值。"""

    rollover_time: str
    should_clear_pending: bool


def resolve_rollover(current: str, pending: str | None, pending_from: str | None,
                     moment: datetime) -> EffectiveRollover:
    """待生效的时间点到了没有。`pending_from` 存日期不存时刻（方案三-3 那条 ⚠️）。"""
    if pending and pending_from and moment.date().isoformat() >= pending_from:
        return EffectiveRollover(parse_hhmm(pending), should_clear_pending=True)
    return EffectiveRollover(parse_hhmm(current), should_clear_pending=False)


# ---------------------------------------------------------------- 时区
#
# ★ 本期"只存不算"，但这一层必须先存在，而且**全站只在这一处判**。
#   二期启用换算时，只改 `now()` 和本函数，别处一行不动。
#   现在把判定立起来，是为了防止"某个页面自己 try/except 了一下 ZoneInfo"
#   这种第二份判据长出来。


def resolve_timezone(value: str | None):
    """把用户存的时区串换成 tzinfo。空值或认不出来一律返回 None = 用本机时间。

    回落而不是报错：时区是个"存了也暂时不生效"的偏好项，为一个暂时不生效的字段
    把整个设置页打回错误页，用户会以为程序坏了。
    """
    if not value or not value.strip():
        return None
    try:
        return ZoneInfo(value.strip())
    except (KeyError, ValueError, OSError):
        # ZoneInfoNotFoundError 是 KeyError 的子类；Windows 上注册表读不到时可能是 OSError。
        return None
