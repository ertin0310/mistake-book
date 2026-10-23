"""协议种类（方案三-16a）。

**加一类协议 = 这里加一项，不改业务代码**：`version` 前缀决定它是哪一类，
`gate=True` 表示"登录后必须先同意才能继续用"（站点协议），
`gate=False` 表示"用到那个功能时才弹"（共享须知，步 19）。

版本号（`SITE-1`）是给人看的串，判断新旧一律用 `agreement.seq` 那个整数：
字符串比较会得出 `SITE-2 > SITE-10`，同意过第 10 版的人会被误判成旧版而反复弹窗。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AgreementKind:
    key: str
    prefix: str
    label: str
    gate: bool = False


KINDS = {
    "site": AgreementKind("site", "SITE", "站点协议", gate=True),
    "share": AgreementKind("share", "SHARE", "共享须知"),
}

# 当前生效的版本。升版就改这里，并把新正文写进 seed（旧版本行留在库里做历史）。
CURRENT = {"site": "SITE-1", "share": "SHARE-1"}


def kind_of(version: str) -> str | None:
    for key, spec in KINDS.items():
        if version.startswith(spec.prefix + "-"):
            return key
    return None
