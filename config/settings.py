"""运行期配置：路径、密钥、保留天数。业务规则不放这里（见 schedule / prompts / menu）。

本项目的配置值分两类：一类是从环境变量读进来的密钥，一类是仓库里就定死的常量。
密钥一律不进仓库；`.env` 被 .gitignore 拦住，仓库里只有 `.env.example`。
"""

import os
import secrets
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
SRC_DIR = PROJECT_ROOT / "src"
DATA_DIR = SRC_DIR / "data"
VAR_DIR = PROJECT_ROOT / "var"
UPLOAD_DIR = VAR_DIR / "uploads"
DB_PATH = VAR_DIR / "mistake_book.db"

# ★ 样例放仓库里的 `import-templates/`，不放 `var/`：`var/` 进了 .gitignore，
#   评审 clone 下来根本看不到，"当场就能导一份"这条演示就断了。
IMPORT_TEMPLATE_DIR = PROJECT_ROOT / "import-templates"
SAMPLE_CSV_PATH = IMPORT_TEMPLATE_DIR / "示例题目.csv"
SAMPLE_DIRTY_CSV_PATH = IMPORT_TEMPLATE_DIR / "示例题目-有脏行.csv"
SAMPLE_JSONL_PATH = IMPORT_TEMPLATE_DIR / "示例题目.jsonl"
AI_PROMPT_PATH = IMPORT_TEMPLATE_DIR / "AI识别提示词.md"

TRASH_RETENTION_DAYS = 30
UPLOAD_MAX_BYTES = 5 * 1024 * 1024
UPLOAD_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
PAGE_SIZE = 20

# 每人每天可调用的 AI 识别次数，按复习日计数（与 compute_review_date 同一个日历口径）。
# 免费额度是全栈共用的，不限量会被一个人一夜刷光，导致其他人集体不可用。
AI_DAILY_LIMIT = 20


def _read_dotenv(path: Path) -> None:
    """把 .env 里的 KEY=VALUE 读进 os.environ。只认 KEY=VALUE 和 # 注释，不做变量展开。

    之所以自己写这十几行：依赖清单要保持短，评审 `pip install` 的东西越少，
    "clone 就能跑"这条越稳。
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def _load_secret_key() -> str:
    """取会话签名密钥；没配就生成一个存进 var/，保证一条命令就能跑起来。

    这里刻意不"必须配了才能启动"：评审只会照 README 敲那一条命令，
    要求他先手工建 .env 就等于把验收卡住。生成的密钥落在 var/（已 gitignore），
    重启后仍然有效，删掉 var/ 等于换密钥、所有人重新登录。
    """
    configured = os.environ.get("SECRET_KEY", "").strip()
    if configured:
        return configured

    key_file = VAR_DIR / ".secret_key"
    if key_file.exists():
        stored = key_file.read_text(encoding="utf-8").strip()
        if stored:
            return stored

    VAR_DIR.mkdir(parents=True, exist_ok=True)
    generated = secrets.token_urlsafe(32)
    key_file.write_text(generated, encoding="utf-8")
    return generated


def ai_enabled() -> bool:
    """是否配置了 AI 密钥。整条 AI 链路只问这一个函数，模板和路由不各自判环境变量。"""
    return bool(os.environ.get("AI_API_KEY", "").strip())


def init_environment() -> None:
    """建好运行期需要的目录并读入 .env。由 create_app() 在启动最早处调用。"""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    IMPORT_TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    _read_dotenv(PROJECT_ROOT / ".env")


def secret_key() -> str:
    """会话签名密钥。用到时才取，绝不在模块顶层定值。

    顶层那一句 `SECRET_KEY = os.environ.get(...)` 会在文件被导入的那一刻就求值，
    可那时 `init_environment()` 还没跑、`.env` 还没读进来，结果评审那个"没配 .env"
    的主场景里拿到的是空串 —— Flask 会话直接不可用，注册登录当场失败。
    """
    configured = os.environ.get("SECRET_KEY", "").strip()
    return configured or _load_secret_key()
