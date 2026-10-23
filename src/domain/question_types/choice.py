"""选择题处理器（方案三-2、三-13）。

库里两份标准 JSON：`options_json` 是选项文本数组，`answer_json` 是 `{"letters":"AC"}`。
判分把两边都收成"字母集合"再比，**多选必须全对**（见 `domain/grading.grade_letters`）。
"""

import json
import string

from config import prompts
from src.domain import grading, normalize
from src.domain.question_types.base import (MAX_ANSWER, MAX_STEM, TypeHandler,
                                                             text_of)

_LETTERS = string.ascii_uppercase
MAX_OPTIONS = 8


class ChoiceHandler(TypeHandler):
    type = "choice"
    label = "选择题"
    auto_gradable = True

    def validate(self, form: dict) -> list[str]:
        errors = []
        stem = text_of(form, "stem")
        options = _lines(text_of(form, "options"))
        letters = _letters(text_of(form, "answer"))
        if not stem:
            errors.append("题干" + prompts.FIELD_REQUIRED)
        elif len(stem) > MAX_STEM:
            errors.append(f"题干太长了，{MAX_STEM} 字以内。")
        if len(options) < 2:
            errors.append("选择题至少要两个选项：一行写一个。")
        elif len(options) > MAX_OPTIONS:
            errors.append(f"选项最多 {MAX_OPTIONS} 个。")
        if not letters:
            errors.append("参考答案" + prompts.FIELD_REQUIRED + "填字母，多选直接连着写，例：AC")
        elif set(letters) - set(_LETTERS[:len(options) or MAX_OPTIONS]):
            errors.append(f"答案里有不存在的选项，只能是 A–{_LETTERS[len(options) - 1]}。")
        elif len(text_of(form, "answer")) > MAX_ANSWER:
            errors.append("参考答案太长了。")
        return errors

    def parse(self, form: dict) -> tuple[str, str]:
        options = json.dumps(_lines(text_of(form, "options")), ensure_ascii=False,
                             separators=(",", ":"))
        answer = normalize.to_canonical_json("answer", text_of(form, "answer"), self.type)
        return options, answer

    def grade(self, answer_json: str, submitted: str):
        return grading.grade_letters(answer_json, submitted)

    def render_widget(self, place: str, value: str = "") -> str:
        tip = "正确答案字母，多选连着写（例：AC）" if place == "form" else "把字母写上来，多选连着写"
        name = "answer" if place == "form" else "submitted"
        return f'<input name="{name}" maxlength="20" placeholder="{tip}" value="{_esc(value)}">'

    def render_options(self, place: str, value: str = "") -> str:
        """选项录入框：一行一个，顺序就是 A、B、C……"""
        if place != "form":
            return ""
        return ('<textarea name="options" rows="4" placeholder="一行一个选项，顺序就是 A、B、C…">'
                f"{_esc(value)}</textarea>")


choice = ChoiceHandler()


def _lines(text: str) -> list:
    """选项有两种来路，都得认：人手写的"一行一个"，与机器写的 JSON 数组文本。

    ★ 判"能不能录"之前先过一遍列内规范化，量的就是最终要入库的那份东西——
      否则会出现"CSV 能过、JSONL 不能过"这种两套规则漂移。
    """
    value = (text or "").strip()
    if not value:
        return []
    canonical = normalize.to_canonical_json("options", value, None)
    try:
        data = json.loads(canonical)
    except ValueError:
        return []
    return [str(item).strip() for item in data if str(item).strip()]         if isinstance(data, list) else []


def _letters(text: str) -> str:
    """答案字母有两种来路：人手写的 `AC`，与机器写的 `{"letters":"AC"}`。

    ★ JSON 那一路必须先取出 `letters` 字段再挑字母——直接在整段 JSON 上挑字母，
      会把 `letters` 这个键名里的 l、t、r、s 也当成选项，答案永远"超出范围"。
    """
    value = (text or "").strip()
    if value.startswith("{"):
        try:
            value = json.loads(value).get("letters", "")
        except ValueError:
            pass
    return "".join(sorted({ch.upper() for ch in value if ch.isalpha()}))


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
