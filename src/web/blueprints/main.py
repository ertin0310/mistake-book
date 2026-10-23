"""首页与模式开关（第 5 步起）。

首页是**给用户看的那一面**（他 2026-10-23 指出：地基自检不该摆给用户）：
今日四个数、掌握度分布、薄弱点排行、快捷入口。建库自检挪进后台 `/admin/diagnostics`。
"""

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from config import menu, prompts
from src.data.repository.profile_repo import SettingRepo
from src.domain.errors import ValidationError
from src.services import stats_service
from src.web import csrf, decorators

bp = Blueprint("main", __name__)


@bp.get("/")
@decorators.require_login
def home():
    user_id = decorators.current_user_id()
    stats = stats_service.overview(g.conn, user_id)
    return render_template(
        "home.html",
        today=stats["today"],
        mastery=stats["mastery"],
        mastery_max=stats["mastery_max"],
        review_date=stats["review_date"],
        weak=stats["weak_points"][:5],
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
        return redirect(menu.MODE_HOME.get(mode, url_for("main.home")))
    if mode not in prompts.MODE_LABELS:
        abort(404)
    decorators.set_mode(mode)
    SettingRepo(g.conn, decorators.current_user_id()).set("mode", mode)
    g.conn.commit()
    return redirect(menu.MODE_HOME.get(mode, url_for("main.home")))
