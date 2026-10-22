"""首页与（第 5 步起）模式开关。

第 2 步的首页是**公开占位页**；第 4 步（本轮）加上登录门槛，第 5 步换成带侧边栏的真首页。
自检内容先留着：评审一条命令就能看见库建没建对。
"""

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from config import prompts, settings
from src.data import db
from src.data.repository.profile_repo import SettingRepo
from src.domain import clock
from src.domain.errors import ValidationError
from src.web import csrf, decorators

bp = Blueprint("main", __name__)

EXPECTED_TABLES = 19


@bp.get("/")
@decorators.require_login
def home():
    tables = db.table_names()
    rows = [(name, int(g.conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]))
            for name in tables]
    return render_template(
        "home.html",
        db_path=settings.DB_PATH,
        tables=tables,
        rows=rows,
        expected=EXPECTED_TABLES,
        ok=len(tables) == EXPECTED_TABLES,
        review_date=clock.review_date_of("00:00"),
        ai_on=settings.ai_enabled(),
    )


@bp.post("/mode/<mode>")
@decorators.require_login
def switch_mode(mode):
    """切换学习/复习：只留这一条路径（方案三-18）。

    存两处——会话一份（每请求都读，不为它查库）+ `user_setting.mode` 一份
    （换浏览器还记住）。⚠️ 模式不是权限：这里只改菜单跟着切的东西。
    """
    try:
        csrf.validate(request.form.get(csrf.FORM_FIELD))
    except ValidationError as exc:
        # 切模式是个小按钮，弹一整页错误太难看：贴一句提示回到原页就行。
        # 这不是"吞异常"——提示照样给用户，步 10 的统一出口管没被表单接住的那些。
        flash(exc.message, "warning")
        return redirect(_safe_next(request.form.get("next")))
    if mode not in prompts.MODE_LABELS:
        abort(404)
    decorators.set_mode(mode)
    SettingRepo(g.conn, decorators.current_user_id()).set("mode", mode)
    g.conn.commit()
    return redirect(_safe_next(request.form.get("next")))


def _safe_next(target: str | None) -> str:
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("main.home")
