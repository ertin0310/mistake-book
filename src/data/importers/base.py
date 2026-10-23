"""导入格式抽象：一种格式一个实现类，产出统一的 `ParsedRow` 列表（方案三-14）。

链路固定是 **上传 → 清洗 → 解析 → 逐行校验 → 预览 → 确认入库**。
★ 报错必须带**原始行号**（第 1 行是表头的话，数据从第 2 行起算），
  不许一句"格式错误"打发人——题目 S4 直接在这儿给分。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParsedRow:
    line: int                                  # 文件里的真实行号，从 1 开始
    data: dict = field(default_factory=dict)
    payload: dict = field(default_factory=dict)   # 校验通过后算出的"将要写入库的内容"
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class FormatImporter(ABC):
    format: str = ""
    label: str = ""

    @abstractmethod
    def parse(self, text: str, columns: tuple[str, ...]) -> list[ParsedRow]:
        """把文本解析成一批带行号的行；解析不动的行直接带 error 返回，不抛异常。"""
