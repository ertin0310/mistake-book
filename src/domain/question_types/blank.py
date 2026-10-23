"""填空题处理器（方案三-2、三-14 ⚠️）。

库里的 `answer_json` 永远是"每空一个数组"：`[["连续","continues"],["不可导"]]`。
录入与作答都用**一行一个空**，同一个空的多种可接受写法用竖线隔开。

★ 竖线只切"同一个空的不同写法"，**斜杠永远不切**。
  把 `1/2` 劈成 `1` 和 `2`，填 `1` 就会被判对——那是判分错误，不是显示错误。
"""

from config import prompts
from src.domain import grading, normalize
from src.domain.question_types.base import MAX_ANSWER, MAX_STEM, TypeHandler, text_of

MAX_BLANKS = 10


class BlankHandler(TypeHandler):
    type = "blank"
    label = "填空题"
    auto_gradable = True

    def validate(self, form: dict) -> list[str]:
        errors = []
        stem = text_of(form, "stem")
        answer = text_of(form, "answer")
        lines = [line for line in answer.splitlines() if line.strip()]
        if not stem:
            errors.append("题干" + prompts.FIELD_REQUIRED)
        elif len(stem) > MAX_STEM:
            errors.append(f"题干太长了，{MAX_STEM} 字以内。")
        if not lines:
            errors.append("参考答案" + prompts.FIELD_REQUIRED + "一行写一个空，同一空有多种写法用竖线隔开")
        elif len(lines) > MAX_BLANKS:
            errors.append(f"空最多 {MAX_BLANKS} 个。")
        elif len(answer) > MAX_ANSWER:
            errors.append(f"参考答案太长了，{MAX_ANSWER} 字以内。")
        return errors

    def parse(self, form: dict) -> tuple[str, str]:
        """填空题没有选项；答案交给列内规范化收成"每空一个数组"。"""
        return "[]", normalize.to_canonical_json("answer", text_of(form, "answer"), self.type)

    def grade(self, answer_json: str, submitted: str):
        return grading.grade_blanks(answer_json, submitted)

    def render_widget(self, place: str, value: str = "") -> str:
        tip = ("一行写一个空；同一空的多种可接受写法用竖线隔开，例：光滑|无摩擦"
               if place == "form" else "一行填一个空，顺序要和题干里的空对上")
        name = "answer" if place == "form" else "submitted"
        return (f'<textarea name="{name}" rows="3" placeholder="{tip}">'
                f"{_esc(value)}</textarea>")


blank = BlankHandler()


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
