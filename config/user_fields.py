"""用户资料与偏好的字段声明。加一项资料 = 这里加一条，表单渲染与校验自动跟上。

source=profile 存 `user_profile` 的列（加列走 migrations）；
source=setting 存 `user_setting` 的 key（加 key 不动表）。
"""

from dataclasses import dataclass, field as _dc_field


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    source: str                       # profile / setting
    default: str = ""
    validators: tuple[str, ...] = ()   # 名字见 services/profile_service.py 的校验表
    maxlen: int = 0
    choices: tuple[str, ...] = ()
    hint: str = ""


USER_FIELDS: list[Field] = [
    Field("display_name", "昵称", "profile", maxlen=30),
    Field("school", "学校", "profile", maxlen=60),
    Field("review_time", "每日复习时间", "setting", default="00:00",
          validators=("hhmm",), hint="到点才刷出当天该复习的题；改动按方案三-3 的规则生效"),
    Field("daily_review_cap", "每日复习量上限", "setting", default="30",
          validators=("int_range:1-200",)),
    Field("mode", "默认模式", "setting", default="study", choices=("study", "review")),
    Field("time_zone", "时区", "setting", default="", hint="暂时不生效，当前按服务器所在机器时间"),
]


def field_by_key(key: str) -> Field | None:
    for item in USER_FIELDS:
        if item.key == key:
            return item
    return None


def defaults() -> dict[str, str]:
    """所有字段的默认值。新用户一个 setting 都不写也能正常跑。"""
    return {item.key: item.default for item in USER_FIELDS}
