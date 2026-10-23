"""题型处理器接口（方案三-13）：一个题型 = 一个实现类，四个方法。

    validate(form)      → 返回中文错误列表（空列表=通过）
    parse(form)         → 转成库里那两份标准 JSON（options_json / answer_json）
    grade(stored, 用户答案) → 'correct' / 'wrong' / None（None=机器判不了，人来评）
    render_widget(where) → 渲染控件的 HTML 片段；**手动录入与复习作答共用同一份**

★ 拆竖线只发生在 `parse()` 这一处（列内规范化在 `domain/normalize.py`），
  存进库的永远是标准 JSON；`grade()` 是纯函数，不查库、不碰时间。
★ `grade()` 返回 `None` 表示机器判不了（简答题），由复习页的四档自评接管；
  返回字典表示机器判过了，`{"right": bool, "detail": 人话}`，`detail` 直接贴给用户看。
"""

from abc import ABC, abstractmethod

MAX_STEM = 1000
MAX_ANSWER = 2000
MAX_EXPLANATION = 4000


class TypeHandler(ABC):
    type: str = ""
    label: str = ""
    auto_gradable = False

    @abstractmethod
    def validate(self, form: dict) -> list[str]:
        """返回要贴回表单的中文提示列表。"""

    @abstractmethod
    def parse(self, form: dict) -> tuple[str, str]:
        """返回 `(options_json, answer_json)` 两个标准 JSON 文本。"""

    @abstractmethod
    def grade(self, answer_json: str, submitted: str):
        """判对判错；机器判不了返回 `None`，由复习页的自评接管。"""

    def render_options(self, place: str, value: str = "") -> str:
        """选项录入框。只有选择题需要，其余题型返回空串——模板因此不必判题型。"""
        return ""

    @abstractmethod
    def render_widget(self, place: str, value: str = "") -> str:
        """`place` 取 'form'（录题/改题）或 'answer'（复习作答）；
        `value` 是编辑时回填的现值——**录题、改题、复习三处共用同一个控件**。"""


def text_of(form: dict, key: str) -> str:
    return (form.get(key) or "").strip()
