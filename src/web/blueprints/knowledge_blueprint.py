"""知识点页（方案三-6）：浏览、提交、我的申请。

★ 提交即入池（所有人马上能用），审核队列只是 `reviewed_by IS NULL`；
★ 撞名不当场拒绝，而是**列出可选项 + 一颗「这不是同一个知识点」**——
  因为"同名但确实不是一回事"在教材里太常见（不同科目的「极限存在定理」）。
"""

from flask import (Blueprint, abort, flash, g, redirect, render_template, request,
                   url_for)

from config import prompts
from src.services import knowledge_service, subject_service
from src.web import csrf, decorators

bp = Blueprint("knowledge", __name__, url_prefix="/knowledge")


@bp.route("/", methods=["GET", "POST"])
@decorators.require_login
def index():
    """浏览某一科的知识点，同时就是提交入口。"""
    subject_id = request.args.get("subject", type=int) or request.form.get("subject_id", type=int)
    page = request.args.get("page", 1, type=int)
    if request.method == "POST":
        try:
            csrf.validate(request.form.get(csrf.FORM_FIELD))
        except Exception as exc:
            return _index(subject_id, [exc.message], request.form, page), 400
        result = knowledge_service.create(g.conn, decorators.current_user_id(), request.form)
        if result["duplicates"]:
            names = "、".join(row["name"] for row in result["duplicates"])
            return _index(subject_id, [prompts.KP_EXISTS.format(names=names)
                                       + prompts.KP_EXISTS_HINT], request.form, page), 400
        flash(prompts.KP_SUBMITTED, "success")
        return redirect(url_for("knowledge.mine"))
    return _index(subject_id, [], None, page)


@bp.get("/mine")
@decorators.require_login
def mine():
    rows = knowledge_service.mine(g.conn, decorators.current_user_id())
    return render_template("knowledge/mine.html", items=knowledge_service.describe(g.conn, rows),
                           empty_text=prompts.EMPTY_KP_MINE)


@bp.post("/rename/<int:point_id>")
@decorators.require_login
def rename(point_id):
    """作者改名重提：这条重新回到待审。不是他提交的那条 → 404（七-1）。"""
    csrf.require_valid_token()
    try:
        knowledge_service.rename(g.conn, decorators.current_user_id(), point_id,
                                 request.form.get("name", ""))
    except NotFoundError:
        abort(404)
    except ValidationError as exc:
        flash(exc.message, "warning")
        return redirect(url_for("knowledge.mine"))
    flash(prompts.KP_RESUBMITTED, "success")
    return redirect(url_for("knowledge.mine"))


def _index(subject_id, errors, form, page=1):
    """列表 + 表单。模板只摆数据，判重与状态文案都在 service 里。

    ★ 默认是"全部科目"而不是"下拉里的第一个"：`options()` 按名字排，
      中文按字节序排出来的第一个是「专业课」，用户提交完在列表里找不到自己的东西，
      只会以为没提交上。
    """
    subjects = subject_service.options(g.conn)
    return render_template("knowledge/index.html", subjects=subjects, subject_id=subject_id,
                           subject_names=dict(subjects),
                           page_obj=knowledge_service.pool(g.conn, subject_id, page),
                           errors=errors, form=form or {}, empty_text=prompts.EMPTY_KP_POOL)
