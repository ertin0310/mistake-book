"""判分与耗时预选（方案三-2、三-13 ★）。

★ 这一层是纯函数：不查库、不碰时间、不 import Flask。判分错了不是显示错，是**判分错**，
  所以它必须能被逐条断言钉住（见 `tests/test_grading.py`）。

三条口径全在 `config/schedule.py`，改口径不碰代码：
  - 忽略大小写 / 全半角 / 空格；**标点不忽略**（`1, 2` 与 `12` 是两回事）
  - 填空是否讲顺序（`BLANK_ORDER_MATTERS`）、是否部分给分（`BLANK_PARTIAL_CREDIT`）
  - 耗时只决定**默认预选**，绝不自动提交；样本不足 `DURATION_MIN_SAMPLES` 条就不预选
"""

import json
import statistics

from config import schedule

# 全角字符 → 半角：中文输入法里打出来的 `１２３（）：` 与半角是同一个答案
_FULLWIDTH_START, _FULLWIDTH_END = 0xFF01, 0xFF5E
_FULLWIDTH_SHIFT = 0xFEE0


def plain(text: str) -> str:
    """判分用的归一化：全角转半角、去所有空白、统一小写。

    ★ 只用于比较，**库里存的永远是原文**——判分口径改了不能把用户写的答案改掉。
    """
    chars = []
    for ch in (text or ""):
        code = ord(ch)
        if code == 0x3000:                      # 全角空格
            code = 32
        elif _FULLWIDTH_START <= code <= _FULLWIDTH_END:
            code -= _FULLWIDTH_SHIFT
        chars.append(chr(code))
    out = "".join(chars)
    if schedule.BLANK_IGNORE_SPACES:
        out = "".join(out.split())
    return out.lower() if schedule.BLANK_IGNORE_CASE else out


def decode(answer_json: str):
    """读库里的标准 JSON。读不懂返回 None，让调用方退回人自评，不崩。"""
    try:
        return json.loads(answer_json)
    except (ValueError, TypeError):
        return None


def grade_letters(answer_json: str, submitted: str):
    """选择题：把两边都收成"选项字母集合"再比。

    ★ 多选必须**全对才算对**：选 `AC` 与只选 `A` 是两种理解，部分给分会让人
      以为自己会了。少选、多选、错选一律判错。
    """
    stored = decode(answer_json)
    if not isinstance(stored, dict) or "letters" not in stored:
        return None
    expected = {ch.upper() for ch in plain(stored["letters"]) if ch.isalpha()}
    got = {ch.upper() for ch in plain(submitted or "") if ch.isalpha()}
    if not got:
        return {"right": False, "detail": "没作答"}
    if got == expected:
        return {"right": True, "detail": "、".join(sorted(expected))}
    missing = "、".join(sorted(expected - got)) or "—"
    extra = "、".join(sorted(got - expected)) or "—"
    return {"right": False, "detail": f"少选 {missing}；多选 {extra}"}


def grade_blanks(answer_json: str, submitted: str):
    """填空题：一行一个空，同一空的可接受答案在库里用竖线存着。

    ★ 竖线只切"同一个空的多种写法"，**斜杠永远不切**——`1/2` 被劈成 `1` 和 `2`
      会导致填 `1` 判对，那是判分错误，不是显示错误。
    """
    stored = decode(answer_json)
    if not isinstance(stored, list) or not stored:
        return None
    blanks = [line.strip() for line in (submitted or "").splitlines()]
    expected = [item if isinstance(item, list) else [item] for item in stored]
    results = []
    for index, alternatives in enumerate(expected):
        got = plain(blanks[index]) if index < len(blanks) else ""
        ok = any(got == plain(alt) for alt in alternatives)
        results.append({"index": index + 1, "right": ok,
                        "expect": "／".join(alternatives), "got": (blanks[index]
                                                                   if index < len(blanks) else "")})
    if not schedule.BLANK_ORDER_MATTERS:
        got_all = {plain(b) for b in blanks}
        want_all = {plain(alt) for alt in _flatten(expected)}
        for item in results:
            item["right"] = item["right"] or item["got"] in want_all
        del got_all, want_all
    right_count = sum(1 for item in results if item["right"])
    all_right = right_count == len(results)
    accepted = all_right or (schedule.BLANK_PARTIAL_CREDIT and right_count > 0)
    wrong = [f"第 {item['index']} 空（标准答案：{item['expect']}，你写：{item['got'] or '空'}）"
             for item in results if not item["right"]]
    return {"right": accepted, "full": all_right, "score": right_count / len(results),
            "detail": "全对" if all_right else "；".join(wrong)}


def median(values: list) -> float:
    return float(statistics.median(values)) if values else 0.0


def preselect_rating(seconds: int, history: list, cap_seconds: int = None):
    """耗时 → 默认预选档位。返回 `(档位, 中位数)`；样本不够时返回 `(None, 中位数)`。

    倍率带见 `schedule.DURATION_RATIO_BANDS`：`<0.6` 判"一下就想起来"，
    `>2` 判"完全没记住"。★ 这只决定页面上**默认选中哪一档**，用户点了别的就以别的为准。
    """
    cap = cap_seconds or schedule.DURATION_CAP_SECONDS
    samples = [min(cap, max(0, int(value))) for value in history if value is not None]
    if len(samples) < schedule.DURATION_MIN_SAMPLES:
        return None, 0
    baseline = median(samples)
    if baseline <= 0:
        return None, baseline
    ratio = min(cap, max(0, int(seconds))) / baseline
    for limit, rating in schedule.DURATION_RATIO_BANDS:
        if limit is None or ratio <= limit:
            return rating, baseline
    return 4, baseline


def _flatten(groups) -> list:
    out = []
    for group in groups:
        out.extend(group if isinstance(group, list) else [group])
    return out
