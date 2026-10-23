"""应用工厂。启动顺序就写在这儿，别处不重复：

    建目录 → 建表 → （第 5 步起）灌演示数据 → 挂路由

前三步是"评审 clone 下来一条命令就能跑"的物理前提：`var/` 进了 .gitignore，
GitHub 上根本没有这个文件夹（空文件夹 Git 也不提交），只能靠程序自己建。
"""

from flask import Flask, g, render_template

from config import menu, permissions, prompts, settings
from src.data import db, seed
from src.web import csrf, decorators
from src.web.blueprints import (auth_blueprint, import_blueprint, main, review_blueprint,
                                settings_blueprint, study_blueprint)

APP_NAME = "错题本 · 间隔重复复习"


def create_app() -> Flask:
    settings.init_environment()
    db.init_db()
    if not db.has_any_user():
        seed.load()          # 空库自动灌演示数据（方案三-21）：clone 下来一条命令就有内容

    app = Flask(__name__,
                template_folder=str(settings.SRC_DIR / "web" / "templates"),
                static_folder=str(settings.SRC_DIR / "static"))
    app.secret_key = settings.secret_key()
    app.config["MAX_CONTENT_LENGTH"] = settings.UPLOAD_MAX_BYTES

    app.register_blueprint(main.bp)
    app.register_blueprint(auth_blueprint.bp)
    app.register_blueprint(study_blueprint.bp)
    app.register_blueprint(review_blueprint.bp)
    app.register_blueprint(settings_blueprint.bp)
    app.register_blueprint(import_blueprint.bp)
    _register_connection(app)
    _register_template_globals(app)
    _register_error_pages(app)
    return app


def _register_template_globals(app: Flask) -> None:
    """模板能拿到的东西全在这一个函数里：防冒名签、当前登录者、按模式过滤好的菜单。

    模板不自己判角色、不自己拼菜单（二-9、二-14）——加页面只动 `config/menu.py`
    和新蓝图，`base.html` 一行不改。
    """

    @app.context_processor
    def _helpers():
        mode = decorators.current_mode()
        role = decorators.current_role()
        return {
            "app_name": APP_NAME,
            "prompts": prompts,          # 模板里所有中文都从这份文案取，不写死字面量
            "csrf_input": csrf.input_tag,
            "signed_in": decorators.current_user_id() is not None,
            "is_admin": role == permissions.ROLE_ADMIN,
            "username": decorators.current_username(),
            "mode": mode,
            "mode_labels": prompts.MODE_LABELS,
            "menu_groups": menu.menu_groups(mode, role),
            "is_active": menu.is_active,
            "menu_group_empty": lambda group: prompts.MENU_GROUP_EMPTY.get(group, ""),
            "badges": {},          # 角标数据（今日到期数、失效数）分别在第 9、20 步接上
        }


def _register_connection(app: Flask) -> None:
    """一条请求一条连接，请求结束就关。外键开关由 db.connect() 负责。"""

    @app.before_request
    def _open():
        if "conn" not in g:
            g.conn = db.connect()

    @app.teardown_appcontext
    def _close(_exc=None):
        conn = g.pop("conn", None)
        if conn is not None:
            conn.close()


def _register_error_pages(app: Flask) -> None:
    """统一异常出口（方案二-8）：自定义错误 → 中文提示页。

    ★ 不散着 `try/except` 吞异常，更不 `except` 之后静默——任何异常都要么被
      表单接住贴回原页（登录/录题那种），要么在这儿翻成人话给用户看。
    """
    from werkzeug.exceptions import HTTPException

    from src.domain.errors import AppError

    @app.errorhandler(AppError)
    def _app_error(exc: AppError):
        return render_template("error.html", code=exc.status_code,
                               message=exc.message or prompts.SERVER_ERROR), exc.status_code

    @app.errorhandler(HTTPException)
    def _http_error(exc: HTTPException):
        # 越权与不存在一律 404 同一句话：告诉用户"它存在但不是你的"本身就是泄露（七-1）
        message = prompts.NOT_FOUND if exc.code == 404 else (exc.description or prompts.SERVER_ERROR)
        return render_template("error.html", code=exc.code, message=message), exc.code

    @app.errorhandler(Exception)
    def _unexpected(exc: Exception):
        app.logger.exception("未预期的异常")
        return render_template("error.html", code=500, message=prompts.SERVER_ERROR), 500
