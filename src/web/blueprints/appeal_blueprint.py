"""用户侧「申诉与反馈」（方案三-25）。

★ 不建站内信：这一页既是提交入口，也是结果页——下次打开就看到状态与回复。
★ 入口有四类，但表单只有一张：从别的页面点进来时预填 `category` 与 `target_id`。
"""

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from config import appeal, prompts
from src.domain.errors import AppError
from src.services import appeal_service
from src.web import csrf, decorators

bp = Blueprint("appeal", __name__, url_prefix="/appeal")


@bp.route("/", methods=["GET", "POST"])
@decorators.require_login
def index():
    if request.method == "POST":
        try:
            csrf.validate(request.form.get(csrf.FORM_FIELD))
            appeal_service.submit(g.conn, decorators.current_user_id(), request.form)
        except AppError as exc:
            return _render(exc.message, request.form), 400
        flash(prompts.APPEAL_SUBMITTED, "success")
        return redirect(url_for("appeal.index"))
    return _render(None, request.args)


def _render(error, form):
    return render_template("appeal/index.html", error=error, form=dict(form),
                           categories=appeal_service.categories(),
                           mine=appeal_service.mine(g.conn, decorators.current_user_id()))
