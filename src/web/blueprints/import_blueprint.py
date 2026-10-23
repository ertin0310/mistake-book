"""导入页：上传 → 预览 → 确认（方案三-14 的两步式防误操作）。

★ 预览页逐行报到**文件里的真实行号**；缺失知识点给一张清单 + 一颗「顺手一起建了」。
★ 本批结果先落 `import_session(status='pending')`，用户走掉回来还能一键确认。
"""

from flask import (Blueprint, abort, flash, g, redirect, render_template, request,
                   url_for)

from config import csv_spec
from src.data.importers import registry
from src.data.importers import sanitize
from src.data.repository.import_session_repo import ImportSessionRepo
from src.services import import_service
from src.web import csrf, decorators

bp = Blueprint("importer", __name__, url_prefix="/import")
MAX_BYTES = 2 * 1024 * 1024


@bp.get("/")
@decorators.require_login
def index():
    pending = ImportSessionRepo(g.conn, decorators.current_user_id()).pending_for("question")
    return _render(None, pending=pending)


@bp.post("/")
@decorators.require_login
def upload():
    csrf.require_valid_token()
    target = request.form.get("target", "question")
    fmt = request.form.get("format", "csv")
    file = request.files.get("file")
    if file is None or not file.filename:
        return _render(None, error="先选一个文件。")
    raw = file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        return _render(None, error="文件太大了，单次最多 2 MB。")
    try:
        text, _encoding = sanitize.decode(raw)
        result = import_service.preview(g.conn, target, fmt, text)
    except ValueError as exc:
        return _render(None, error=str(exc))
    result["session_id"] = import_service.stage(g.conn, decorators.current_user_id(),
                                                target, fmt, file.filename, result)
    return _render(result)


@bp.post("/confirm")
@decorators.require_login
def confirm():
    csrf.require_valid_token()
    session_id = request.form.get("session_id", type=int)
    if not session_id:
        abort(404)
    counts = import_service.commit(g.conn, decorators.current_user_id(), session_id,
                                   create_missing=bool(request.form.get("create_missing")))
    flash(f"导入完成：题目 {counts['questions']} 道、知识点 {counts['knowledge_points']} 个"
          f"、科目 {counts['subjects']} 个。", "success")
    return redirect(url_for("study.my_questions"))


def _render(result, error=None, pending=()):
    """预览页和空表单页共用同一个模板：变量名固定，模板不必判"这是第几次进来"。"""
    return render_template("import/index.html", result=result, error=error, pending=pending,
                           targets=csv_spec.SPECS, formats=registry.formats())
