"""今日复习：出题 → 作答 → 看答案 → 四档自评（方案三-1）。

★ 答案一开始不出现；**没点「看答案」就没有自评按钮**——盲评没有意义，
  也会让耗时失去含义。计时起点=进入这道题，终点=按下「看答案」那一刻，
  之后阅读答案的时间不计入。
"""

import time

from flask import (Blueprint, abort, flash, g, redirect, render_template, request,
                   url_for)

from config import prompts
from src.data.repository.base import Page
from src.data.repository.mistake_repo import MistakeRepo
from src.domain.errors import ValidationError
from src.domain.errors import RestoreConflictError
from src.services import (question_service, review_service, stats_service,
                           trash_service)
from src.web import csrf, decorators

bp = Blueprint("review", __name__, url_prefix="/review")
MAX_SECONDS = 3 * 3600            # 超过 3 小时按 3 小时算：挂机不该污染耗时统计


@bp.get("/today")
@decorators.require_login
def today():
    extra = request.args.get("extra", 0, type=int)
    queue = review_service.today_queue(g.conn, decorators.current_user_id(),
                                       request.args.get("page", 1, type=int), extra=extra)
    # 翻页条是全站同一个组件：这里把队列包成和列表页一样的 Page 形状再交给模板
    page_obj = Page(items=queue["rows"], page=queue["page"], page_size=queue["cap"],
                    total=queue["total"], total_pages=queue["pages"])
    return render_template("review/today.html", queue=queue, page_obj=page_obj,
                           first=queue["rows"][0]["id"] if queue["rows"] else None)


@bp.get("/stats")
@decorators.require_login
def stats():
    """统计四图：数字全在 `stats_service` 里算，这一层只是取来摆。"""
    return render_template("review/stats.html", stats=stats_service.overview(g.conn,
                                                                             decorators.current_user_id()))


@bp.get("/trash")
@decorators.require_login
def trash():
    """回收站：只看自己扔进去的。还原撞名字时贴一句提示回本页，不弹错误页。"""
    return render_template("review/trash.html",
                           trash=trash_service.listing(g.conn, decorators.current_user_id()))


@bp.post("/trash/restore")
@decorators.require_login
def restore_from_trash():
    _require_token()
    entity = request.form.get("entity", "")
    row_id = request.form.get("row_id", type=int)
    try:
        trash_service.restore(g.conn, decorators.current_user_id(), entity, row_id)
    except RestoreConflictError as exc:
        flash(exc.message, "warning")
        return redirect(url_for("review.trash"))
    except ValidationError as exc:
        abort(404, description=exc.message)
    flash("已经放回原处了。", "success")
    return redirect(url_for("review.trash"))


@bp.get("/card/<int:mistake_id>")
@decorators.require_login
def card(mistake_id):
    row = _own_row(mistake_id)
    return render_template("review/card.html", row=row, started=int(time.time()))


@bp.post("/card/<int:mistake_id>/reveal")
@decorators.require_login
def reveal(mistake_id):
    """看答案：机器能判的题型顺手判一次，并按耗时给出**默认预选**档位。

    ★ 预选只是把某一档画成"当前选中"，提交仍由用户点（三-2）：
      自动提交等于替用户撒谎，而且一次挂机就能把整条复习曲线带偏。
    """
    _require_token()
    row = _own_row(mistake_id)
    seconds = _seconds(request.form.get("started"))
    submitted = request.form.get("submitted", "")
    question = row["question"]
    verdict = (question_service.grade(question, submitted)
               if question_service.auto_gradable(question) else None)
    preselect, baseline = review_service.duration_preselect(
        g.conn, decorators.current_user_id(), question["subject_id"], seconds)
    return render_template("review/answer.html", row=row, seconds=seconds,
                           started=request.form.get("started", ""),
                           answer_text=question_service.answer_text(question["answer_json"]),
                           options=question_service.options_of(question),
                           submitted=submitted, verdict=verdict, preselect=preselect,
                           baseline=baseline, ratings=prompts.RATING_LABELS,
                           retractable=(int(row["mistake"]["review_count"] or 0) == 0
                                        and row["mistake"]["entry_reason"] == "marked_wrong"))


@bp.post("/card/<int:mistake_id>/retract")
@decorators.require_login
def retract(mistake_id):
    """改判「我其实答对了」：把那道自动入队、还没复习过的错题收回去（三-13）。"""
    csrf.require_valid_token()
    retracted = review_service.retract_wrong(g.conn, decorators.current_user_id(), mistake_id)
    flash(prompts.RETRACTED if retracted else prompts.RETRACT_REFUSED,
          "success" if retracted else "warning")
    return redirect(url_for("review.today"))


@bp.post("/card/<int:mistake_id>/rate")
@decorators.require_login
def rate(mistake_id):
    _require_token()
    row = _own_row(mistake_id)
    seconds = _seconds(request.form.get("started"))
    rating = request.form.get("rating", type=int) or 0
    try:
        result = review_service.rate(g.conn, decorators.current_user_id(), mistake_id, rating,
                                     seconds, rating_source=_rating_source(
                                         g.conn, decorators.current_user_id(),
                                         row["question"]["subject_id"], seconds, rating))
    except ValidationError as exc:
        flash(exc.message, "warning")
        return redirect(url_for("review.today"))
    flash(f"评好了，下一次到期：{result['next_due']}", "success")
    return redirect(url_for("review.today"))


def _rating_source(conn, user_id: int, subject_id: int, seconds: int, rating: int) -> str:
    """这一档是耗时预选替用户选的，还是他自己改的？记下来才能统计"人改判率"。

    ★ 预选值在这儿**重算一遍**，不信表单里带的那个隐藏字段：表单是可以被人改的，
      而"改判率"这个统计的意义恰恰是拿人的选择跟机器的预选比。
    """
    preselect, _baseline = review_service.duration_preselect(conn, user_id, subject_id, seconds)
    return "duration_default" if preselect is not None and rating == preselect else "user_override"


def _require_token() -> None:
    csrf.require_valid_token()


def _own_row(mistake_id):
    row = MistakeRepo(g.conn, decorators.current_user_id()).get(mistake_id)
    if row is None:
        abort(404, description=prompts.NOT_FOUND)
    from src.data.repository.question_repo import QuestionRepo
    question = QuestionRepo(g.conn, decorators.current_user_id()).any_visible(row["question_id"])
    if question is None:
        abort(404, description=prompts.NOT_FOUND)
    return {"mistake": row, "question": question}


def _seconds(raw) -> int:
    try:
        value = int(time.time()) - int(raw)
    except (TypeError, ValueError):
        return 0
    return max(0, min(value, MAX_SECONDS))
