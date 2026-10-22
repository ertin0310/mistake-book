"""自研分级表 `ladder`：本期唯一的调度实现（方案三-4）。

台阶序列与四档动作全在 `config/schedule.py`，**改台阶不动这个文件**。

四档：1 升两级 / 2 升一级 / 3 退一级 / 4 归零并记一次 lapse。
★ 两条夹住：级数夹在 `0 ~ 顶格`；**评完之后的间隔至少 1 天**（否则第 0 级会让
  到期日等于今天，当天刷完立刻回队，见 `config/schedule.py` 那条注释）。
"""

from datetime import date, timedelta

from config import schedule
from src.domain.scheduling.base import Move, ReviewState, SchedulingStrategy

TOP_STEP = len(schedule.LADDER_INTERVALS) - 1
RESET = "reset"


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


class LadderStrategy(SchedulingStrategy):
    name = "ladder"
    algorithm_version = schedule.ALGORITHM_VERSION

    def next_state(self, before: ReviewState, rating: int, today: date) -> Move:
        if rating not in schedule.LADDER_STEPS:
            raise ValueError(f"未知的自评档位：{rating!r}")
        move = schedule.LADDER_STEPS[rating]
        lapsed = move == RESET
        if lapsed:
            step = 0
        else:
            step = _clamp(before.step_index + move, 0, TOP_STEP)

        interval = max(schedule.LADDER_INTERVALS[step], schedule.MIN_INTERVAL_AFTER_REVIEW)
        after = ReviewState(step_index=step, interval_days=interval,
                            due_date=today + timedelta(days=interval))
        return Move(before=before, after=after, rating=rating, lapsed=lapsed,
                    algorithm_version=self.algorithm_version)


ladder = LadderStrategy()


def next_state(step_index: int, due_date: date, rating: int, today: date) -> Move:
    """给 service 与 seed 用的便捷入口：不想自己拼 `ReviewState` 时调这个。"""
    before = ReviewState(step_index=step_index, interval_days=0, due_date=due_date)
    return ladder.next_state(before, rating, today)
