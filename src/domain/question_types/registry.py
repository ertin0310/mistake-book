"""题型注册表（方案二-2）：调用方只认 `get(type)`，不认识具体实现类。

加一个题型 = 旁边多一个文件 + 这里 `register()` 一行；录题页、复习页、导入链路
全都从这里取，**没有第二处 `if type == 'choice'` 的散判**。
"""

from src.domain.question_types.base import TypeHandler
from src.domain.question_types.essay import essay

_REGISTRY: dict[str, TypeHandler] = {}


def register(handler: TypeHandler) -> None:
    if not handler.type:
        raise ValueError("题型处理器必须有 type")
    _REGISTRY[handler.type] = handler


def get(type_name: str) -> TypeHandler:
    if type_name not in _REGISTRY:
        raise ValueError(f"没有登记过这个题型：{type_name!r}")
    return _REGISTRY[type_name]


def known() -> tuple[str, ...]:
    return tuple(_REGISTRY)


register(essay)
