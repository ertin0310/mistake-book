"""两个装饰器 + 会话里读当前登录者。权限只有这两层（方案二-14）。

`current_user_id()` 是全站唯一从会话里取"谁在看"的地方：repository 的 `viewer_id`
一律由它提供，**绝不允许从表单或 URL 传进来**——否则步 3 那套 scope 过滤等于没做。

★ `require_admin()` 只挡写操作和后台页面，**不让 admin 跳过 `user_id` 过滤**：
管理员读不到任何私有记录（三-23 四条禁令）。
"""

from functools import wraps

from flask import abort, flash, redirect, request, session, url_for

from config import permissions, prompts

USER_KEY = "uid"
ROLE_KEY = "role"
MODE_KEY = "mode"
NAME_KEY = "uname"


def current_user_id() -> int | None:
    return session.get(USER_KEY)


def current_role() -> str | None:
    return session.get(ROLE_KEY)


def current_mode() -> str:
    """当前模式只从会话取，**不为它查库**（方案三-18）。

    会话里没有（比如登录前）就退回配置默认值；登录时会把 `user_setting.mode`
    写进会话，所以"换浏览器还记住"和"每请求零成本"两件事各得其所。
    ⚠️ 模式不是权限（二-12）：复习模式下直敲学习网址照样进，只是菜单跟着切。
    """
    return session.get(MODE_KEY) or prompts.DEFAULT_MODE


def set_mode(mode: str) -> None:
    if mode not in prompts.MODE_LABELS:
        raise ValueError(f"未知的模式：{mode!r}")
    session[MODE_KEY] = mode


def current_username() -> str:
    """登录名存在会话里，侧边栏顶部显示它——**不为此查一次库**。"""
    return session.get(NAME_KEY, "")


def sign_in(user: dict, mode: str | None = None) -> None:
    session[USER_KEY] = user["id"]
    session[ROLE_KEY] = user["role"]
    session[NAME_KEY] = user["username"]
    if mode in prompts.MODE_LABELS:
        session[MODE_KEY] = mode
    session.permanent = False          # 关浏览器就掉登录态，本期不做"记住我"


def sign_out() -> None:
    session.pop(USER_KEY, None)
    session.pop(ROLE_KEY, None)
    session.pop(MODE_KEY, None)
    session.pop(NAME_KEY, None)


def require_login(view):
    @wraps(view)
    def _wrapped(*args, **kwargs):
        if current_user_id() is None:
            flash(prompts.LOGIN_REQUIRED, "warning")
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return _wrapped


def require_admin(view):
    @wraps(view)
    def _wrapped(*args, **kwargs):
        if current_user_id() is None:
            flash(prompts.LOGIN_REQUIRED, "warning")
            return redirect(url_for("auth.login", next=request.path))
        if not permissions.is_admin_role(current_role()):
            abort(403, description=prompts.FORBIDDEN)
        return view(*args, **kwargs)

    return _wrapped
