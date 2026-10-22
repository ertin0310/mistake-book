"""第 1 步演示用：知识点名归一化 + options/answer 两列的列内规范化。

`1/2` 与 `|x|` 那两条是这一步真正要守住的规矩——它们防的是判分错误，不是显示难看。
"""

from src.domain import normalize as n


# ---------------------------------------------------------------- 名字归一化

def test_strip_all_spaces_and_lowercase():
    assert n.normalize_name("  牛 顿 第二 定律  ") == "牛顿第二定律"
    # 英文名里的空格也一起吃掉：归一化值只用来比对，界面显示的仍是用户原写法。
    assert n.normalize_name("Newton's 2nd Law") == "newton's2ndlaw"


def test_fullwidth_becomes_halfwidth():
    assert n.normalize_name("２０２６考研") == "2026考研"
    assert n.is_same_name("ｆ（ｘ）", "f(x)")


def test_repeated_punct_collapses_to_one():
    assert n.normalize_name("冲量。。定理") == "冲量。定理"
    assert n.normalize_name("动量---定理") == "动量-定理"


def test_same_name_and_empty():
    assert n.is_same_name("  泰勒公式 ", "泰勒公式")
    assert not n.is_same_name("", "")


# ---------------------------------------------------------------- 列内规范化

def test_options_canonical_json_is_kept():
    assert n.to_canonical_json("options", '["光滑","粗糙"]', "choice") == '["光滑","粗糙"]'


def test_options_shorthand_one_per_line():
    assert n.to_canonical_json("options", "光滑\n粗糙\n\n水", "choice") == '["光滑","粗糙","水"]'


def test_blank_one_line_per_gap():
    raw = "光滑|无摩擦\n水"
    assert n.to_canonical_json("answer", raw, "blank") == '[["光滑","无摩擦"],["水"]]'


def test_slash_is_never_a_separator():
    """★ 判分错误的源头：`1/2` 拆成 `1` 和 `2`，学生填 1 就判对。"""
    assert n.to_canonical_json("answer", "1/2", "blank") == '[["1/2"]]'
    assert "1/2" in n.to_canonical_json("answer", "光滑|1/2", "blank")


def test_vertical_bar_inside_content_survives_json():
    """`|x|` 这类绝对值写法：走 JSON 通道时原样收下，一个字符不丢。"""
    raw = '[["|x|"]]'
    assert n.to_canonical_json("answer", raw, "blank") == '[["|x|"]]'


def test_choice_letters_sorted_and_deduped():
    assert n.to_canonical_json("answer", "c、a", "choice") == '{"letters":"AC"}'
    assert n.to_canonical_json("answer", '{"letters":"AC"}', "choice") == '{"letters":"AC"}'


def test_essay_keeps_everything_including_commas_and_newlines():
    raw = "设光滑，\n则动量守恒。"
    assert n.to_canonical_json("answer", raw, "essay") == '{"text":"设光滑，\\n则动量守恒。"}'


def test_malformed_json_falls_to_shorthand():
    """写坏的中括号不算 JSON，按简写"一行一个选项"处理，不许报错。"""
    assert n.to_canonical_json("options", "[光滑, 粗糙]\n水", "choice") == '["[光滑, 粗糙]","水"]'


def test_blank_gap_list_is_always_list_of_lists():
    assert n.to_canonical_json("answer", '["光滑","水"]', "blank") == '[["光滑"],["水"]]'


def test_empty_gives_empty_shape():
    assert n.to_canonical_json("options", "", "choice") == "[]"
    assert n.to_canonical_json("answer", "", "blank") == "[]"
    assert n.to_canonical_json("answer", "", "essay") == '{"text":""}'


def test_idempotent():
    """规范化跑两次必须一模一样——导出再导回逐字节一致靠的就是这条。"""
    for raw, qtype in [("光滑|无摩擦\n水", "blank"), ("A 光滑\nB 粗糙", "choice"),
                       ('[["光滑"]]', "blank"), ("参考答案，见解析。", "essay")]:
        once = n.to_canonical_json("answer", raw, qtype)
        assert n.to_canonical_json("answer", once, qtype) == once
