"""导出页：两个链接直接下载 CSV（方案三-13）。

★ 不做"先弹出预览再下载"：导出是读，读错 nothing 坏了，多一步只会挡路。
  真正要防误操作的是**写入**那一条链（导入），它才需要两步式。
"""

from urllib.parse import quote

from flask import Blueprint, Response, abort, g

from config import prompts
from src.services import export_service
from src.web import decorators

bp = Blueprint("exporter", __name__, url_prefix="/export")


@bp.get("/<kind>.csv")
@decorators.require_login
def download(kind):
    if kind not in export_service.KINDS:
        abort(404)                      # 认不出来的种类和"不存在"是同一件事，别多发信息
    text = export_service.build(g.conn, decorators.current_user_id(), kind)
    name = f"{prompts.EXPORT_KIND_LABELS[kind]}.csv"
    response = Response(text, mimetype="text/csv; charset=utf-8")
    # 中文文件名要按 RFC 5987 转义；同时留一份 ASCII 兜底名，老浏览器不认带 * 的那半句
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{kind}.csv"; filename*=UTF-8\'\'{quote(name)}')
    return response
