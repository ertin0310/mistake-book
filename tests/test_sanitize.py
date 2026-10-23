"""步 16 · `test_sanitize.py`：清洗层单独一份用例（方案三-15）。

清洗与校验是两件事：这一层只管"这堆字节/字符能不能读"，
内容对不对归 `test_import_validation.py`。分开的意义在于——
**洗的时候顺手记数**，用户能看见"程序替我改了几处"，不是被偷偷改。
"""

import pytest

from src.data.importers import sanitize

# ---------------------------------------------------------------- 编码嗅探

def test_utf8_bom_is_stripped_not_kept():
    """带 BOM 的 UTF-8（记事本、Excel 都爱加）读出来第一列不能挂着 \\ufeff。"""
    text, encoding = sanitize.decode(b"\xef\xbb\xbftype,subject\n")   # 字节层面的 EF BB BF
    assert text[0] == "t"                       # BOM 被吃掉，第一列不叫 "\ufefftype"
    assert encoding == "utf-8-sig"


def test_plain_utf8_and_gbk_both_recognised():
    assert sanitize.decode("牛顿定律".encode("utf-8"))[0] == "牛顿定律"
    assert sanitize.decode("牛顿定律".encode("gbk"))[0] == "牛顿定律"      # Excel 另存 CSV 常是这货


def test_garbage_bytes_raise_a_chinese_hint():
    with pytest.raises(ValueError) as excinfo:
        sanitize.decode(b"\xff\xff\xfe\x00\x01")
    assert "编码认不出来" in str(excinfo.value)


# ---------------------------------------------------------------- 排版级修补

@pytest.mark.parametrize("raw,expected", [
    ("“光滑”", '"光滑"'),          # 中文双引号 → JSON 里必须是半角
    ("‘光滑’", "'光滑'"),
    ("a\r\nb", "a\nb"),
    ("a\nb", "a\nb"),
])
def test_each_common_issue_is_fixed(raw, expected):
    assert sanitize.fix_common_issues(raw)[0] == expected


def test_fixes_are_counted_not_silent():
    """★ 改了几处要报数：预览页那句"已自动修正 N 处"就是从这儿来的。"""
    text, fixes = sanitize.fix_common_issues("“甲”\r\n“乙”\r\n")
    assert text == '"甲"\n"乙"\n'
    assert fixes == 6                            # 四个弯引号（两对）+ 两个 CRLF


def test_already_clean_text_reports_zero():
    assert sanitize.fix_common_issues('{"text":"答案"}\n') == ('{"text":"答案"}\n', 0)


# ---------------------------------------------------------------- AI 那三条常见毛病

def test_code_fence_is_stripped_and_counted():
    raw = "```json\n{\"a\": 1}\n```\n"
    text, marks = sanitize.strip_code_fences(raw)
    assert text == '{"a": 1}' and marks == 2


def test_split_lines_only_drops_blank_lines_and_never_eats_a_real_one():
    """AI 前面那句"好的，如下："**不偷偷丢**，留给解析器如实报错并带行号。

    被程序吃掉的行是找不回来的，报出来的行用户自己删得掉——所以这层只做"丢空行"一件事。
    """
    lines = sanitize.split_lines("好的，如下：\n\n{\"a\": 1}\n{\"b\": 2}\n")
    assert lines == ["好的，如下：", '{"a": 1}', '{"b": 2}']


def test_a_file_that_is_only_fences_leaves_nothing_to_parse():
    text, marks = sanitize.strip_code_fences("```\n```\n")
    assert sanitize.split_lines(text) == [] and marks == 2
