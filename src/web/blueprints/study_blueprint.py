"""学习模式：我的题目列表 + 录题。

这一层只收表单、调 service、渲染（方案二-1）——SQL 与业务判断都不许出现在这儿。
"""

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from src.services import question_service, subject_service
from src.web import csrf, decorators

bp = Blueprint("study", __name__, url_prefix="/study")


@bp.get("/")
@decorators.require_login
def my_questions():
    return render_template(
        "study/questions.html",
        page_obj=question_service.mine(g.conn, decorators.current_user_id(),
                                       request.args.get("page", 1, type=int),
                                       request.args.get("subject", type=int)),
        subjects=subject_service.options(g.conn),
        empty_text="还没有题目。先录一道，复习才有东西排。")


@bp.get("/drill")
@decorators.require_login
def shared_pool():
    """共享池：别人共享的 + 官方题。列表与翻页跟"我的题目"共用同一套组件。"""
    return render_template(
        "study/questions.html",
        page_obj=question_service.shared_pool(g.conn, decorators.current_user_id(),
                                              request.args.get("page", 1, type=int),
                                              request.args.get("subject", type=int)),
        subjects=subject_service.options(g.conn),
        empty_text="共享池暂时是空的。")


@bp.route("/new", methods=["GET", "POST"])
@decorators.require_login
def new_question():
    if request.method == "GET":
        return _form({}, [])
    try:
        csrf.validate(request.form.get(csrf.FORM_FIELD))
    except Exception as exc:
        return _form(request.form, [exc.message]), 400
    errors = question_service.new_errors(g.conn, request.form)
    if errors:
        return _form(request.form, errors), 400
    question_service.create(g.conn, decorators.current_user_id(), request.form)
    flash("录好了，已经放进你的题目列表。", "success")
    return redirect(url_for("study.my_questions"))


def _form(form, errors):
    """答案控件由题型处理器给，录题页与复习页共用同一份（方案三-13）。"""
    widgets = {key: question_service.widget(key, "form") for key, _ in
               question_service.available_types()}
    return render_template("study/new_question.html", form=form, errors=errors,
                           widgets=widgets,
                           subjects=subject_service.options(g.conn),
                           types=question_service.available_types())
