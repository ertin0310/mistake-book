"""时区下拉的数据（方案三-17）。

本期**只存不算**：选了什么都只写进 `user_setting`，所有计算仍按服务器本机时间。
但下拉要做全（`zoneinfo.available_timezones()`），免得将来启用换算时再改一遍页面。
"""

from zoneinfo import available_timezones

# 常用的一批配中文名，排在前面；其余按字母序排在后面，只显英文键名。
COMMON = (
    ("Asia/Shanghai", "中国 · 上海（北京时间）"),
    ("Asia/Hong_Kong", "中国 · 香港"),
    ("Asia/Taipei", "中国 · 台北"),
    ("Asia/Singapore", "新加坡"),
    ("Asia/Tokyo", "日本 · 东京"),
    ("Asia/Seoul", "韩国 · 首尔"),
    ("Asia/Kolkata", "印度 · 加尔各答"),
    ("Asia/Dubai", "阿联酋 · 迪拜"),
    ("Europe/London", "英国 · 伦敦"),
    ("Europe/Berlin", "德国 · 柏林"),
    ("Europe/Moscow", "俄罗斯 · 莫斯科"),
    ("America/New_York", "美国 · 纽约"),
    ("America/Chicago", "美国 · 芝加哥"),
    ("America/Los_Angeles", "美国 · 洛杉矶"),
    ("Australia/Sydney", "澳大利亚 · 悉尼"),
    ("Pacific/Auckland", "新西兰 · 奥克兰"),
)

_COMMON_KEYS = {key for key, _ in COMMON}


def options() -> tuple[tuple[str, str], ...]:
    """常用带中文名在前，其余按字母序跟在后面。"""
    rest = sorted(zone for zone in available_timezones() if zone not in _COMMON_KEYS)
    return tuple(COMMON) + tuple((zone, zone) for zone in rest)
