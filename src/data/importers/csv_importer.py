"""CSV 解析：给人用的那条通道，**允许列内写简写**（一行一空、同空多答案用竖线）。

引号里的换行不会劈行（`csv` 模块本身处理），列数不符、表头缺列都报到行号。
"""

import csv
from io import StringIO

from config import prompts
from src.data.importers.base import FormatImporter, ParsedRow


class CsvImporter(FormatImporter):
    format = "csv"
    label = "CSV"

    def parse(self, text: str, columns: tuple[str, ...]) -> list[ParsedRow]:
        reader = csv.reader(StringIO(text))
        try:
            header = next(reader)
        except StopIteration:
            return [ParsedRow(line=1, errors=[prompts.IMPORT_EMPTY_FILE])]
        header = [name.strip().lstrip("﻿") for name in header]
        missing = [name for name in columns if name not in header]
        if missing:
            return [ParsedRow(line=1, errors=[f"表头少了列：{', '.join(missing)}"])]

        rows = []
        for offset, values in enumerate(reader, start=2):
            if not any(value.strip() for value in values):
                continue                       # 空行不算数据，也不报错
            if len(values) != len(header):
                rows.append(ParsedRow(line=offset,
                                      errors=[f"这一行有 {len(values)} 列，表头是 {len(header)} 列"]))
                continue
            rows.append(ParsedRow(line=offset, data=dict(zip(header, values))))
        return rows


csv_importer = CsvImporter()
