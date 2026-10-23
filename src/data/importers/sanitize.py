"""进来的文本先洗一遍（方案三-14）。

清洗和校验是两件事：**清洗**只管"这堆字节/字符能不能读"（编码、BOM、换行、
AI 常见的排版毛病），**校验**才管"这一行的内容对不对"（必填、越界、类型）。
洗的时候顺手记"自动修正了几处"，透明地告诉用户，不偷偷改。
"""

import codecs

# 常见编码嗅探顺序：带 BOM 的 UTF-8 → UTF-8 → GBK（Excel 另存 CSV 常是 GBK）
_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030")

# AI 输出的常见排版毛病 → 直接修掉（方案三-15 的"修完标已自动修正 N 处"）
_FIXES = (
    ("﻿", ""),                       # 正文中间的 BOM
    ("“", "\""), ("”", "\""),    # 中文引号
    ("‘", "'"), ("’", "'"),      # 中文单引号
    ("\r\n", "\n"), ("\r", "\n"),                 # Windows 换行
)


def decode(raw: bytes) -> tuple[str, str]:
    """字节 → 文本。认不出来就报错，不许拿乱码继续往下跑。"""
    for encoding in _ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ValueError("这个文件的编码认不出来，请另存为 UTF-8 或 GBK 再导。")


def fix_common_issues(text: str) -> tuple[str, int]:
    """修掉排版级的小毛病，返回 `(修好的文本, 修了几处)`。"""
    fixes = 0
    for bad, good in _FIXES:
        count = text.count(bad)
        if count:
            text = text.replace(bad, good)
            fixes += count
    return text, fixes


def strip_code_fences(text: str) -> tuple[str, int]:
    """剥掉 AI 爱加的 ```json ... ``` 围栏。"""
    marks = text.count("```")
    if not marks:
        return text, 0
    lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
    return "\n".join(lines), marks


def split_lines(text: str) -> list[str]:
    """按行切，只丢空行。

    ★ 不猜"哪行是 AI 说的废话"：`好的，如下：` 这种行交给 JSONL 解析器如实报
      "这一行不是合法 JSON"并带真实行号，比在这里偷偷丢掉更可核对——
      用户删错了行数还能找回来，被程序吃掉的行是找不回来的。
    """
    return [line for line in text.split("\n") if line.strip()]
