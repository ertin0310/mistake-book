"""自定义异常类型。

只放类型，不放中文文案——文案一律在 `config/prompts.py`（方案二-3）。
业务层抛这些，`src/app.py` 的错误处理器统一翻译成人话（方案二-8），
所以这里不许出现 `print`、不许出现 `flash`，也不许 import flask。
"""


class AppError(Exception):
    """可预期错误的基类。

    `message` 由抛出方传入（已经是中文），`status_code` 决定 HTTP 响应码。
    """

    status_code = 400

    def __init__(self, message: str = ""):
        super().__init__(message)
        self.message = message


class ValidationError(AppError):
    """输入不合法：必填为空、越界、格式不对、类型错误（题目 S4 点名的四类）。"""

    status_code = 400


class NotFoundError(AppError):
    """记录不存在，或者存在但不属于当前用户。

    ★ 两种情况都走 404，不给 403：告诉用户"它存在但不是你的"本身就是泄露（方案七-1）。
    """

    status_code = 404


class PermissionDeniedError(AppError):
    """需要管理员才做得到的操作。"""

    status_code = 403


class RestoreConflictError(AppError):
    """回收站还原会与现有活跃行撞唯一约束（方案三-12a）。"""

    status_code = 409


class AiUnavailableError(AppError):
    """AI 接口不可用：没配 Key、超时、429、返回内容不是合法 JSON。"""

    status_code = 503
