"""协议页（方案三-16a）：正文 + 同意按钮，同意记录落 `user_agreement`。

★ 这道门由 `src/app.py` 的 `before_request` 统一把，不在每个路由上各写一次
  `if 没同意` ——那样一百个路由要漏九个。
"""

from flask import (Blueprint, abort, flash, g, redirect, render_template, request,
                   url_for)

from config import agreement as agreement_config
from config import prompts
from src.services import agreement_service
from src.web import csrf, decorators

bp = Blueprint("agreement", __name__, url_prefix="/agreement")


@bp.get("/<version>")
@decorators.require_login
def page(version):
    _require_viewable(version)
    return render_template("agreement/page.html", doc=agreement_service.body(g.conn, version),
                           next_url=_safe_next(request.args.get("next")))


@bp.post("/<version>/accept")
@decorators.require_login
def accept(version):
    csrf.require_valid_token()
    _require_viewable(version)
    agreement_service.accept(g.conn, decorators.current_user_id(), version)
    flash(prompts.AGREEMENT_ACCEPTED, "success")
    return redirect(_safe_next(request.form.get("next")))


def _require_viewable(version) -> None:
    """认不出的版本一律 404：既不是当前生效的，也不是这个人同意过的。"""
    if agreement_config.kind_of(version) is None or not agreement_service.viewable(
            g.conn, decorators.current_user_id(), version):
        abort(404)


def _safe_next(target):
    """只允许回到本站相对路径——`?next=https://外部` 这种开放重定向不能跟着走。"""
    if not target or not target.startswith("/") or target.startswith("//"):
        return url_for("main.home")
    return target
