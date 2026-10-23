"""导入注册表（方案三-14 ★）：按 `(target, format)` 两级取件。

AI 那条路（步 25）只是**多注册一行**：`(question, ai)` 复用同一份校验链，
差别仅在它先走 sanitize 再进 jsonl 解析。清洗、报行号、预览全共用。
"""

from src.data.importers.base import FormatImporter
from src.data.importers.csv_importer import csv_importer
from src.data.importers.jsonl_importer import jsonl_importer

_FORMATS: dict[str, FormatImporter] = {}


def register(importer: FormatImporter) -> None:
    _FORMATS[importer.format] = importer


def get(fmt: str) -> FormatImporter:
    if fmt not in _FORMATS:
        raise ValueError(f"没有登记过这个导入格式：{fmt}")
    return _FORMATS[fmt]


def formats() -> tuple[str, ...]:
    return tuple(_FORMATS)


register(csv_importer)
register(jsonl_importer)
