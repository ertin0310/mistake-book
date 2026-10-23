"""管理后台（方案三-23）。

★ 每个路由第一行 `@decorators.require_admin()`：拦人的是这一层 + 数据层的归属过滤，
  菜单只是导航（二-12）。后台是**独立入口 + 独立布局**（他 2026-10-22 额外提的硬要求）：
  普通用户侧看不到，点进来先要登录且必须是管理员，页面用 `admin/base.html`。
★ 四条禁令：不真删、不改用户写的内容、不往别人数据里加东西、读不到私有记录。
  这里只有字典（科目、知识点）与申诉队列——没有任何一处能查别人的错题/记录/笔记。
"""

import sqlite3

from flask import (Blueprint, flash, g, redirect, render_template, request, url_for)

from config import prompts, settings
from src.data import db
from src.data.repository.knowledge_repo import KnowledgeRepo
from src.data.repository.subject_repo import SubjectRepo
from src.domain import clock
from src.services import appeal_service, knowledge_service, subject_service
from src.web import csrf, decorators

bp = Blueprint("admin", __name__, url_prefix="/admin")

# 建库自检用的期望表数（评审一条命令就能看见库建没建对，他 2026-10-23 要求挪进后台）。
EXPECTED_TABLES = 19


@bp.get("/")
@decorators.require_admin
def home():
    """后台首页：几项各挂一个待办数，一眼看出哪儿有活。"""
    return render_template("admin/index.html", counts={
        "subject": len(SubjectRepo(g.conn).browse()),
        "knowledge": len(KnowledgeRepo(g.conn).pending()),
        "appeal": len(appeal_service.queue(g.conn, "open")),
    })


@bp.get("/diagnostics")
@decorators.require_admin
def diagnostics():
    """建库自检：从首页挪进来的（他 2026-10-23 指出自检不该给用户看）。

    表名取自 `sqlite_master`，不是外部输入，所以拼进 COUNT 语句没有注入面。
    """
    tables = db.table_names()
    rows = [(name, int(g.conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]))
            for name in tables]
    ok = len(tables) == EXPECTED_TABLES
    return render_template(
        "admin/diagnostics.html",
        db_path=settings.DB_PATH,
        rows=rows,
        ok=ok,
        status=(prompts.ADMIN_DIAGNOSTICS_OK if ok else
                prompts.ADMIN_DIAGNOSTICS_COUNT.format(expected=EXPECTED_TABLES,
                                                       actual=len(tables))),
        review_date=clock.review_date_of("00:00"),
        ai_on=settings.ai_enabled(),
    )


@bp.route("/subject", methods=["GET", "POST"])
@decorators.require_admin
def subject():
    """科目：新建、改名、停用/恢复。**没有"删除"这个按钮**（科目永不物理删）。"""
    if request.method == "POST":
        csrf.require_valid_token()
        action = request.form.get("action")
        try:
            if action == "create":
                SubjectRepo(g.conn).create(request.form.get("name", ""))
                flash(prompts.ADMIN_SUBJECT_CREATED, "success")
            elif action == "rename":
                SubjectRepo(g.conn).rename(request.form.get("subject_id", type=int),
                                           request.form.get("name", ""))
                flash(prompts.ADMIN_SUBJECT_RENAMED, "success")
            elif action == "toggle":
                _toggle_subject(request.form.get("subject_id", type=int))
        except sqlite3.IntegrityError:
            flash(prompts.ADMIN_NAME_CLASH, "warning")
        return redirect(url_for("admin.subject"))
    return render_template("admin/subject.html", rows=SubjectRepo(g.conn).browse())


@bp.route("/knowledge", methods=["GET", "POST"])
@decorators.require_admin
def knowledge():
    """知识点审核队列：通过 / 驳回带原因 / 下架 / 直建。"""
    admin_id = decorators.current_user_id()
    if request.method == "POST":
        csrf.require_valid_token()
        action = request.form.get("action")
        point_id = request.form.get("point_id", type=int)
        repo = KnowledgeRepo(g.conn, admin_id)
        if action == "approve":
            repo.mark_reviewed(point_id, admin_id)
        elif action == "reject":
            repo.reject(point_id, admin_id, request.form.get("note", ""))
        elif action == "hide":
            repo.set_status(point_id, "hidden")
        elif action == "create":
            return _direct_create(admin_id)
        flash(prompts.ADMIN_POINT_DECIDED, "success")
        return redirect(url_for("admin.knowledge"))
    return render_template("admin/knowledge.html",
                           pending=_pending(), subjects=subject_service.options(g.conn))


@bp.route("/appeal", methods=["GET", "POST"])
@decorators.require_admin
def appeal():
    """申诉与反馈队列：收尾必须写回复（不写就报中文提示，不许默默关掉）。"""
    if request.method == "POST":
        csrf.require_valid_token()
        try:
            appeal_service.resolve(g.conn, decorators.current_user_id(),
                                   request.form.get("appeal_id", type=int),
                                   request.form.get("reply", ""))
            flash(prompts.ADMIN_DONE, "success")
        except Exception as exc:
            flash(exc.message, "warning")
        return redirect(url_for("admin.appeal"))
    return render_template("admin/appeal.html", open=appeal_service.queue(g.conn, "open"),
                           handled=appeal_service.queue(g.conn, "handled")[:20])


def _toggle_subject(subject_id):
    current = SubjectRepo(g.conn).browse_one(subject_id)["status"]
    SubjectRepo(g.conn).set_status(subject_id, "hidden" if current == "active" else "active")
    flash(prompts.ADMIN_SUBJECT_SWITCHED, "success")


def _pending():
    """待审队列 = `reviewed_by IS NULL`；显示时补上科目名与提交人。"""
    rows = KnowledgeRepo(g.conn).pending()
    subjects = SubjectRepo(g.conn).name_map()
    return [dict(row, subject=subjects.get(row["subject_id"], "")) for row in rows]


def _direct_create(admin_id: int):
    """管理员直建知识点：走的是用户提交同一条路（提交即入池），不另开一条写入口。"""
    from src.domain.errors import AppError
    try:
        knowledge_service.create(g.conn, admin_id, request.form)
    except AppError as exc:
        flash(exc.message, "warning")
    else:
        flash(prompts.KP_SUBMITTED, "success")
    return redirect(url_for("admin.knowledge"))
