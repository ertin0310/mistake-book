"""防冒名签（方案二-15 ★）：从步 3 挪过来的，因为那一步一个表单都没有。

做法就十几行：会话里存一张手写小签 → 表单里藏一行 → 请求回来比一次。
★ **只对 POST 判，GET 不判**——GET 不该改任何东西，给它加签只会让分享链接、
书签、刷新全变成"页面放得太久了"。
"""

import hmac
import secrets

from flask import session

from config import prompts
from src.domain.errors import ValidationError

TOKEN_KEY = "csrf_token"
FORM_FIELD = "csrf_token"


def token() -> str:
    value = session.get(TOKEN_KEY)
    if not value:
        value = secrets.token_urlsafe(24)
        session[TOKEN_KEY] = value
    return value


def input_tag() -> str:
    """模板里用 `{{ csrf_input() | safe }}` 贴一行隐藏输入。"""
    return f'<input type="hidden" name="{FORM_FIELD}" value="{token()}">'


def validate(presented: str | None) -> None:
    """比签；不对就抛 `ValidationError`，由统一异常出口翻成中文提示页。

    用 `hmac.compare_digest` 而不是 `==`：短的比较会提前返回，
    理论上能被计时试探——本项目是本地应用，但这条规则写一次就该写对。
    """
    expected = session.get(TOKEN_KEY)
    if not expected or not presented or not hmac.compare_digest(expected, presented):
        raise ValidationError(prompts.CSRF_FAILED)
