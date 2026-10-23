"""导入页：上传 → 预览 → 确认（方案三-14 的两步式防误操作）。

★ 预览页逐行报到**文件里的真实行号**；缺失知识点给一张清单 + 一颗「顺手一起建了」。
★ 本批结果先落 `import_session(status='pending')`，用户走掉回来还能一键确认。
"""

from flask import (Blueprint, Response, abort, flash, g, redirect, render_template,
                   request, url_for)

from config import csv_spec, prompts, settings
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
        return _render(None, error=prompts.IMPORT_NO_FILE)
    raw = file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        return _render(None, error=prompts.IMPORT_TOO_LARGE)
    try:
        text, _encoding = sanitize.decode(raw)
        result = import_service.preview(g.conn, target, fmt, text)
    except ValueError as exc:
        return _render(None, error=str(exc))
    result["session_id"] = import_service.stage(g.conn, decorators.current_user_id(),
                                                target, fmt, file.filename, result)
    return _render(result)


@bp.post("/paste")
@decorators.require_login
def paste():
    """粘贴通道：AI 输出的文本与上传的文件走同一条校验链，只是来源不同。

    ★ 不因为"是模型给的"就免检——模型会蒙错答案、把正确项写反、把 1/2 写成 0.5，
      人看一眼预览能发现，代码发现不了，所以它必须和文件同等待遇。
    """
    csrf.require_valid_token()
    text = request.form.get("text", "")
    if not text.strip():
        return _render(None, error=prompts.IMPORT_EMPTY_FILE)
    try:
        result = import_service.preview(g.conn, "question", "jsonl", text)
    except ValueError as exc:
        return _render(None, error=str(exc))
    result["session_id"] = import_service.stage(g.conn, decorators.current_user_id(),
                                                "question", "jsonl", "粘贴内容", result)
    return _render(result)


@bp.get("/template/<kind>")
@decorators.require_login
def template(kind):
    """模板下载。文件在仓库里，但用户看不见仓库，所以这里给一个鉴权后的下载入口。"""
    path = _TEMPLATES.get(kind)
    if path is None or not path.exists():
        abort(404)
    return Response(path.read_bytes(), mimetype="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=\"{path.name}\""})


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


_TEMPLATES = {"csv": settings.SAMPLE_CSV_PATH, "jsonl": settings.SAMPLE_JSONL_PATH}


def _render(result, error=None, pending=()):
    """预览页和空表单页共用同一个模板：变量名固定，模板不必判"这是第几次进来"。

    列说明、示例、AI 提示词都在这儿备齐——**页面上必须自带这些信息**，
    因为用户看不到仓库，让他"去仓库里抄表头"等于没说。
    """
    return render_template("import/index.html", result=result, error=error, pending=pending,
                           targets=csv_spec.SPECS, formats=registry.formats(),
                           column_docs=csv_spec.COLUMN_DOCS,
                           example_csv=_head(settings.SAMPLE_CSV_PATH, 4),
                           example_jsonl=_head(settings.SAMPLE_JSONL_PATH, 2),
                           ai_prompt=_text(settings.AI_PROMPT_PATH))


def _head(path, lines):
    """取样例文件前几行当示例：与样例文件同一份，不另抄一遍。"""
    return chr(10).join(_text(path).splitlines()[:lines])


def _text(path):
    if not path.exists():
        return ""
    try:
        text, _encoding = sanitize.decode(path.read_bytes())
    except ValueError:
        return ""
    return text.strip()
