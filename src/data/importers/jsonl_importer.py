"""JSONL 解析：给机器与 AI 用的那条通道，**一行一个 JSON 对象，不做简写转换**。

为什么要有它：CSV 单元格里放 JSON 要把每个双引号写成两个（`"[[""光滑""]]"`），
这是人和 AI 都最容易写错的地方。JSONL 原样写 JSON、没有逗号转义问题。
"""

import json

from src.data.importers.base import FormatImporter, ParsedRow


class JsonlImporter(FormatImporter):
    format = "jsonl"
    label = "JSONL"

    def parse(self, text: str, columns: tuple[str, ...]) -> list[ParsedRow]:
        rows = []
        for line_no, raw in enumerate(text.splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                data = json.loads(raw)
            except ValueError:
                rows.append(ParsedRow(line=line_no, errors=["这一行不是合法 JSON"]))
                continue
            if not isinstance(data, dict):
                rows.append(ParsedRow(line=line_no, errors=["这一行不是对象（应该是 {...}）"]))
                continue
            rows.append(ParsedRow(line=line_no,
                                  data={key: _as_text(value) for key, value in data.items()}))
        return rows


def _as_text(value) -> str:
    """JSONL 里的嵌套结构原样转回文本，交给下游的列内规范化去认。"""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


jsonl_importer = JsonlImporter()
