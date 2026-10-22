"""策略注册表（方案二-2）：调用方只认 `get()`，不认识具体实现。

将来加算法（FSRS、SM-2）= 在 `ladder.py` 旁边多一个文件 + 这里多注册一行，
`review_service` 与 `seed` 一行不改。本期只注册 `ladder` 一个。
"""

from src.domain.scheduling.base import SchedulingStrategy
from src.domain.scheduling.ladder import LadderStrategy, ladder

DEFAULT = ladder.name

_REGISTRY: dict[str, SchedulingStrategy] = {}


def register(strategy: SchedulingStrategy) -> None:
    if not strategy.name:
        raise ValueError("策略必须有 name")
    _REGISTRY[strategy.name] = strategy


def get(name: str | None = None) -> SchedulingStrategy:
    key = name or DEFAULT
    if key not in _REGISTRY:
        raise ValueError(f"没有注册过这个调度策略：{key!r}")
    return _REGISTRY[key]


register(ladder)
