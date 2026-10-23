"""复习闭环（方案三-1、三-4、三-11、三-13）。

三件事在这儿，别处不再各写一份：
    取今天的题   —— 上限只管 LIMIT，**绝不为凑数去改 due_date**
    记一次自评   —— 调策略算出新状态 → 写回 mistake → 追加 review_log（同一事务）
    做错入队     —— 学习模式标记"做错了"→ upsert mistake，当天就进今日复习
"""

from config import prompts, schedule
from src.data.repository.mistake_repo import MistakeRepo
from src.data.repository.study_attempt_repo import ReviewLogRepo, StudyAttemptRepo
from src.data.repository.profile_repo import SettingRepo
from src.domain import clock
from src.domain.errors import ValidationError
from src.domain.scheduling import registry
from src.domain.scheduling.base import ReviewState

RATING_SOURCE_USER = "user_override"


def daily_cap(conn, user_id: int) -> int:
    """用户自定义的每日上限，脏值一律回落到默认 30。"""
    raw = SettingRepo(conn, user_id).all().get("daily_review_cap", "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return schedule.DAILY_CAP_DEFAULT
    return min(max(value, schedule.DAILY_CAP_MIN), schedule.DAILY_CAP_MAX)


def due_count(conn, user_id: int) -> int:
    """侧边栏角标用：今天到期多少道。与今日复习页同一个复习日、同一条查询。"""
    repo = MistakeRepo(conn, user_id)
    return repo.count_due(clock.review_date_of(_rollover(conn, user_id)))


def today_queue(conn, user_id: int, page: int = 1, extra: int = 0):
    """今日复习的一页 + 顶部提示要用的三个数。

    `extra` 是页面上「再加 10 题」按钮放宽的量——**只放宽本次 LIMIT，不落日期**。
    """
    review_date = clock.review_date_of(_rollover(conn, user_id))
    repo = MistakeRepo(conn, user_id)
    cap = daily_cap(conn, user_id) + max(0, extra)
    rows, total, current, pages = repo.due_page(review_date, page=page, limit=cap)
    return {"rows": rows, "total": total, "page": current, "pages": pages,
            "cap": cap, "review_date": review_date,
            "over": max(0, total - cap)}


def _rollover(conn, user_id: int) -> str:
    settings = SettingRepo(conn, user_id).all()
    return clock.resolve_rollover(settings.get("review_time"), settings.get("review_time_pending"),
                                  settings.get("review_time_pending_from"), clock.now()
                                  ).rollover_time


def rate(conn, user_id: int, mistake_id: int, rating: int, duration_seconds: int = 0,
         rating_source: str = RATING_SOURCE_USER) -> dict:
    """一次自评：算新状态 → 写回队列 → 追加流水。三件事要么都成，要么都不成。"""
    if rating not in schedule.LADDER_STEPS:
        raise ValidationError("自评只能选 1 到 4 档。")
    repo = MistakeRepo(conn, user_id)
    row = repo.get(mistake_id)
    if row is None:
        raise ValidationError(prompts.NOT_FOUND)
    review_date = clock.review_date_of(_rollover(conn, user_id))
    move = registry.get().next_state(
        ReviewState(row["step_index"], row["interval_days"], clock.parse_date(row["due_date"])),
        rating, review_date)
    repo.apply_move(mistake_id, move)
    ReviewLogRepo(conn, user_id).append(
        mistake_id=mistake_id, reviewed_on=review_date,
        reviewed_at=clock.now().strftime("%Y-%m-%d %H:%M:%S"), rating=rating,
        rating_source=rating_source, duration_seconds=duration_seconds, move=move)
    conn.commit()
    return {"move": move, "next_due": move.after.due_date}


def record_attempt(conn, user_id: int, question_id: int, subject_id: int, result: str,
                   submitted: str = "") -> int | None:
    """学习模式记一笔做题结果；**做错 → 当场进复习队列**（方案三-13 的闭环那一环）。

    已有活跃错题时**不重置台阶、不记 lapse**：进度只由复习自评驱动，
    再错一次不该把人家爬到第 6 级的成果清零。
    """
    StudyAttemptRepo(conn, user_id).record(question_id, subject_id, result, submitted)
    if result != "wrong":
        return None
    repo = MistakeRepo(conn, user_id)
    existing = repo.active_for(question_id)
    if existing is not None:
        return existing["id"]
    review_date = clock.review_date_of(_rollover(conn, user_id))
    return repo.add(question_id, review_date, entry_reason="marked_wrong")
