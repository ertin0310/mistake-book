"""调度策略接口（方案二-2、三-4）。

**加一种算法 = 新增一个实现类 + 注册一行，调用方一行不改。** 本期只有自研阶梯
`ladder` 一个实现：`sm2.py` 不写、`mistake.ef` 不建、设置页没有算法选项。

★ 这一层是纯函数：不查库、不读墙上时钟，"今天"由调用方传进来。
  测试能把今天捏成任何一天，seed 也能把 45 天的序列原样重放一遍。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ReviewState:
    """一道错题在复习前/后的状态。三个值都是 `mistake` 表里的列。"""

    step_index: int
    interval_days: int
    due_date: date


@dataclass(frozen=True)
class Move:
    """一次自评造成的移动。`review_log` 的 before/after 六列就是从这里落的。"""

    before: ReviewState
    after: ReviewState
    rating: int
    lapsed: bool
    algorithm_version: str


class SchedulingStrategy(ABC):
    name: str = ""
    algorithm_version: str = ""

    @abstractmethod
    def next_state(self, before: ReviewState, rating: int, today: date) -> Move:
        """算出评完这一档之后到哪一级、隔多久、哪天到期。"""
