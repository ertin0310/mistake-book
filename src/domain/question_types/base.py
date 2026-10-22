"""题型处理器接口（方案三-13）：一个题型 = 一个实现类，四个方法。

    validate(form)      → 返回中文错误列表（空列表=通过）
    parse(form)         → 转成库里那两份标准 JSON（options_json / answer_json）
    grade(stored, 用户答案) → 'correct' / 'wrong' / None（None=机器判不了，人来评）
    render_widget(where) → 渲染控件的 HTML 片段；**手动录入与复习作答共用同一份**

★ 拆竖线只发生在 `parse()` 这一处（列内规范化在 `domain/normalize.py`），
  存进库的永远是标准 JSON；`grade()` 是纯函数，不查库、不碰时间。
本期只做 `essay`；`choice` / `blank` 留到步 21。
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

    @abstractmethod
    def render_widget(self, place: str) -> str:
        """`place` 取 'form'（录题）或 'answer'（复习作答）。"""


def text_of(form: dict, key: str) -> str:
    return (form.get(key) or "").strip()
