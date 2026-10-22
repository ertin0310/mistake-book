"""资料与偏好的校验表（方案三-17）。

`config/user_fields.py` 里每个字段声明的 `validators` 名字在这儿找实现；
**加一项资料 = 声明加一条 + 需要新规则时这里加一个函数**，页面代码不动。
"""

import re

from config import prompts, schedule
from src.domain import clock
from src.domain.errors import ValidationError

_RANGE = re.compile(r"^int_range:(\d+)-(\d+)$")


def _hhmm(value: str) -> str:
    raw = (value or "").strip()
    parsed = clock.parse_hhmm(raw, fallback=None)
    if parsed is None:
        raise ValidationError(prompts.INVALID_TIME)
    return parsed


def _int_range(value: str, low: int, high: int) -> str:
    try:
        number = int((value or "").strip())
    except ValueError:
        raise ValidationError(prompts.OUT_OF_RANGE) from None
    if not low <= number <= high:
        raise ValidationError(prompts.OUT_OF_RANGE)
    return str(number)


def clean(field, raw: str) -> str:
    """按声明跑校验，返回规范化后的值。"""
    value = (raw or "").strip()
    if not value:
        return ""                       # 空值交给默认值，不在这里报错
    if field.maxlen and len(value) > field.maxlen:
        raise ValidationError(f"{field.label}太长了，{field.maxlen} 字以内。")
    for name in field.validators:
        match = _RANGE.match(name)
        if match:
            value = _int_range(value, int(match.group(1)), int(match.group(2)))
        elif name == "hhmm":
            value = _hhmm(value)
        else:
            raise ValueError(f"未知的校验器：{name}")
    return value


def rollover_change(current: str, requested: str):
    """改每日复习时间点的规则（方案三-3）：没过原时间点当日生效，过了次日生效。"""
    from src.domain import clock as _clock
    return _clock.decide_rollover_change(current, requested, _clock.now())


CAP_RANGE = (schedule.DAILY_CAP_MIN, schedule.DAILY_CAP_MAX)
