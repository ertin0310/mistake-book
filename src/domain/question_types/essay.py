"""简答题处理器（本期唯一实现的题型）。

答案是一整段参考答案文本，机器判不了 → `grade()` 恒返回 `None`，
复习页走"看答案 → 四档自评"那条路（方案三-1）。
"""

from config import prompts
from src.domain import normalize
from src.domain.question_types.base import (MAX_ANSWER, MAX_EXPLANATION, MAX_STEM,
                                            TypeHandler, text_of)


class EssayHandler(TypeHandler):
    type = "essay"
    label = "简答题"
    auto_gradable = False

    def validate(self, form: dict) -> list[str]:
        errors = []
        stem = text_of(form, "stem")
        answer = text_of(form, "answer")
        if not stem:
            errors.append("题干" + prompts.FIELD_REQUIRED)
        elif len(stem) > MAX_STEM:
            errors.append(f"题干太长了，{MAX_STEM} 字以内。")
        if not answer:
            errors.append("参考答案" + prompts.FIELD_REQUIRED)
        elif len(answer) > MAX_ANSWER:
            errors.append(f"参考答案太长了，{MAX_ANSWER} 字以内。")
        if len(text_of(form, "explanation")) > MAX_EXPLANATION:
            errors.append(f"解析太长了，{MAX_EXPLANATION} 字以内。")
        return errors

    def parse(self, form: dict) -> tuple[str, str]:
        """简答题没有选项；答案整段交给列内规范化，出来就是 `{"text":"…"}`。"""
        return "[]", normalize.to_canonical_json("answer", text_of(form, "answer"), self.type)

    def grade(self, answer_json: str, submitted: str):
        return None                      # 简答只能人自评

    def render_widget(self, place: str, value: str = "") -> str:
        text = _escape(value)
        if place == "answer":
            return ('<textarea name="submitted" rows="4" placeholder="先自己回忆一遍再写下来，'
                    f'写不出就写\"想不起来\"">{text}</textarea>')
        return ('<textarea name="answer" rows="4" placeholder="参考答案，整段写就行，'
                f'不用管 JSON">{text}</textarea>')


essay = EssayHandler()


def _escape(text: str) -> str:
    """往 HTML 里塞用户文本前只处理这三个字符；库里存的是原文，不受影响。"""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
