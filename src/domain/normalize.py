"""知识点名归一化：查重与"占名字"都按归一化后的值判（方案三-6）。

规则顺序不能换：先去空格再去全角，否则全角空格（U+3000）会先被算成"非标点"留下。

本模块还有第二件事：CSV / 表单里 `options`、`answer` 两列的"列内规范化"，
见文件下半截。两件事放一起是因为它们同属"进来的文字先整形再比对"这一层，
都是纯函数，不碰数据库。
"""

import json
import re
import unicodedata

# 步骤开关。方案二-3 要求"规则可配置"，第 1 步先把行为定下来；
# 真要做成配置时，这三个开关搬到 config/ 里的一份声明，本模块只留实现。
STRIP_INTERNAL_SPACES = True
LOWER = True
FULLWIDTH_TO_HALF = True
COLLAPSE_REPEATED_PUNCT = True

_PUNCT_CLASS = r"[。，、；：！？．,;:!?\-—_（）()\[\]【】「」“”\"'’‘·]"
_REPEATED_PUNCT = re.compile(rf"({_PUNCT_CLASS})\1+")
_ANY_SPACE = re.compile(r"\s+")


def normalize_name(raw: str) -> str:
    """把用户输入的知识点名转成用来比对的形态。"""
    value = (raw or "").strip()
    if FULLWIDTH_TO_HALF:
        value = unicodedata.normalize("NFKC", value)
    if STRIP_INTERNAL_SPACES:
        value = _ANY_SPACE.sub("", value)
    if COLLAPSE_REPEATED_PUNCT:
        value = _REPEATED_PUNCT.sub(r"\1", value)
    if LOWER:
        value = value.casefold()
    return value


def is_same_name(left: str, right: str) -> bool:
    """两个原始写法是否指向同一个知识点。"""
    a, b = normalize_name(left), normalize_name(right)
    return bool(a) and a == b


# ---------------------------------------------------------------- 列内规范化
#
# CSV 里 `options` / `answer` 两格可以写成标准 JSON，也可以写成简写。
# 简写**只在这一个入口被接受**，转成 JSON 之后才往下走；存储层和导出文件里
# 永远只有标准 JSON，一条规矩没松（方案三-13）。
#
# ★ 竖线 `|` 是"同一个空的多个可接受答案"的唯一分隔符；斜杠 `/` 明令禁用。
#   理由不是显示难看，是判分会错：`1/2` 当分隔符拆成 `1` 和 `2` 之后，
#   学生填 `1` 会被判对。


COLUMN_OPTIONS = "options"
COLUMN_ANSWER = "answer"

TYPE_CHOICE = "choice"
TYPE_BLANK = "blank"
TYPE_ESSAY = "essay"

BLANK_ANSWER_SEPARATOR = "|"
_LETTER_ONLY = re.compile(r"[A-Za-z]")


def to_canonical_json(column: str, raw: str, question_type: str | None = None) -> str:
    """把一格原始内容转成库里那两列的标准 JSON 文本。

    认得出的 JSON 就照收（重新序列化一遍，让输出形态唯一，导出再导回才可能逐字节一致）；
    认不出的当简写转。空值返回各列的空形态，"必填有没有填"归校验层管，这里不越权。
    """
    value = (raw or "").strip()
    parsed = _try_json(value)
    if parsed is not None and _shape_ok(column, parsed, question_type):
        return _dumps(_tidy(column, parsed, question_type))
    return _dumps(_from_shorthand(column, value, question_type))


def _tidy(column: str, parsed, question_type: str | None):
    """把两种都能写的合法 JSON 收成一种形态：填空题外层永远是"每空一个数组"。"""
    if column == COLUMN_ANSWER and question_type == TYPE_BLANK:
        return [[x] if isinstance(x, str) else x for x in parsed]
    return parsed


def _try_json(value: str):
    if not value or value[0] not in "[{":      # 简写不可能以方括号/花括号开头
        return None
    try:
        return json.loads(value)
    except ValueError:
        return None


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _shape_ok(column: str, parsed, question_type: str | None) -> bool:
    # 题型未知时不猜：能解析成 JSON 结构就当成标准 JSON 收下，
    # 因为简写永远写不出方括号/花括号开头的合法 JSON。
    if question_type is None:
        return True
    if column == COLUMN_OPTIONS:
        return isinstance(parsed, list) and all(isinstance(x, str) for x in parsed)
    if question_type == TYPE_CHOICE:
        return isinstance(parsed, dict) and isinstance(parsed.get("letters"), str)
    if question_type == TYPE_BLANK:
        return isinstance(parsed, list) and all(
            isinstance(x, str) or (isinstance(x, list) and all(isinstance(a, str) for a in x))
            for x in parsed)
    if question_type == TYPE_ESSAY:
        return isinstance(parsed, dict) and isinstance(parsed.get("text"), str)
    return False


def _from_shorthand(column: str, value: str, question_type: str | None):
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if column == COLUMN_OPTIONS:
        return lines
    if question_type == TYPE_CHOICE:
        letters = sorted({m.upper() for m in _LETTER_ONLY.findall(value)})
        return {"letters": "".join(letters)}
    if question_type == TYPE_BLANK:
        return [[alt.strip() for alt in line.split(BLANK_ANSWER_SEPARATOR) if alt.strip()]
                for line in lines]
    # 认不准题型时按简答整段收下：这是唯一不丢字符的读法。
    return {"text": value}
