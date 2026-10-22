"""注册 / 登录 / 退出。这一层只收表单、调 service、渲染（方案二-1）。

★ 这里 `try/except ValidationError` 不是为了咽掉异常，是为了**把中文提示贴回原表单**
（用户不用重填用户名）。统一异常出口在步 10 建，管的是"没被表单接住"的那些。
"""

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from config import prompts
from src.data.repository.profile_repo import SettingRepo
from src.domain.errors import ValidationError
from src.services import auth_service
from src.web import csrf, decorators

bp = Blueprint("auth", __name__)


def _sign_in_with_mode(user: dict) -> None:
    """登录时把库里的默认模式搬进会话：换浏览器也还记得在哪个模式（方案三-18）。"""
    decorators.sign_in(user, SettingRepo(g.conn, user["id"]).all().get("mode"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("auth/register.html", error=None)
    try:
        _require_valid_form()
        user = auth_service.register(
            g.conn, request.form.get("username", ""),
            request.form.get("password", ""), request.form.get("confirm", ""))
    except ValidationError as exc:
        return render_template("auth/register.html", error=exc.message), 400
    _sign_in_with_mode(user)
    flash(f"欢迎，{user['username']}。", "success")
    return redirect(url_for("main.home"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("auth/login.html", error=None,
                               next=request.args.get("next", ""))
    try:
        _require_valid_form()
        user = auth_service.login(g.conn, request.form.get("username", ""),
                                  request.form.get("password", ""))
    except ValidationError as exc:
        return render_template("auth/login.html", error=exc.message,
                               next=request.form.get("next", "")), 400
    _sign_in_with_mode(user)
    return redirect(_safe_next(request.form.get("next")))


@bp.post("/logout")
def logout():
    _require_valid_form()
    decorators.sign_out()
    return redirect(url_for("main.home"))


def _require_valid_form() -> None:
    csrf.validate(request.form.get(csrf.FORM_FIELD))


def _safe_next(target: str | None) -> str:
    """只允许跳回站内相对路径，否则这个参数就成了钓鱼跳转的口子。"""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("main.home")
