"""应用工厂。启动顺序就写在这儿，别处不重复：

    建目录 → 建表 → （第 5 步起）灌演示数据 → 挂路由

前三步是"评审 clone 下来一条命令就能跑"的物理前提：`var/` 进了 .gitignore，
GitHub 上根本没有这个文件夹（空文件夹 Git 也不提交），只能靠程序自己建。
"""

from flask import Flask, g

from config import menu, permissions, prompts, settings
from src.data import db, seed
from src.web import csrf, decorators
from src.web.blueprints import auth_blueprint, main, study_blueprint

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
    _register_connection(app)
    _register_template_globals(app)
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
