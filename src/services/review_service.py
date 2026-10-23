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
from src.domain import clock, grading
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


def next_due(conn, user_id: int, exclude_id=None):
    """今天还剩哪一道该刷（用于"评完自动跳下一题"）。没有下一道就返回 None。"""
    review_date = clock.review_date_of(_rollover(conn, user_id))
    # ★ `due_page` 返回的是 (rows, total, page, pages) 四元组，不是 Page 对象：
    #   写 `.items` 时测试没断这条路的返回码，线上一点「评好了」就 500。
    for row in MistakeRepo(conn, user_id).due_page(review_date, page=1, limit=50)[0]:
        if exclude_id is None or row["id"] != exclude_id:
            return row["id"]
    return None


def reviewed_today(conn, user_id: int) -> int:
    """今天已经评了几道——今日复习页那句"继续第 N 道"靠它，不靠猜。"""
    review_date = clock.review_date_of(_rollover(conn, user_id))
    return ReviewLogRepo(conn, user_id).count_today(review_date)


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


def attempted_today(conn, user_id: int) -> set:
    """今天已经做过的题号，练习页靠它轮换。"""
    review_date = clock.review_date_of(_rollover(conn, user_id))
    return StudyAttemptRepo(conn, user_id).attempted_on(review_date)


def duration_preselect(conn, user_id: int, subject_id: int, seconds: int):
    """耗时 → 默认预选档位（三-2）。返回 `(档位或 None, 该科中位数秒数)`。

    ★ 只决定页面上**默认选中哪一档**，绝不自动提交：自动提交等于替用户撒谎，
      而且一次挂机就能把整条复习曲线带偏。样本不足 `DURATION_MIN_SAMPLES` 条不预选。
    """
    history = ReviewLogRepo(conn, user_id).durations_for_subject(subject_id)
    return grading.preselect_rating(seconds, history)


def retract_wrong(conn, user_id: int, mistake_id: int) -> bool:
    """改判「我其实答对了」：收回那道**自动入队且还没复习过**的错题（三-13）。

    ★ 两个条件缺一不可：复习过的（`review_count>0`）说明进度是真的，收了就丢历史；
      手动加进来的（`entry_reason != 'marked_wrong'`）是用户自己要排的，不该由这个按钮收。
      收 = 软删（进回收站），不物理删——`review_log.mistake_id` 还指着它。
    """
    repo = MistakeRepo(conn, user_id)
    row = repo.get(mistake_id)
    if row is None:
        raise ValidationError(prompts.NOT_FOUND)
    if int(row["review_count"] or 0) > 0 or row["entry_reason"] != "marked_wrong":
        return False
    repo.retire(mistake_id, user_id)
    return True


def record_attempt(conn, user_id: int, question_id: int, subject_id: int, result: str,
                   submitted: str = "", grade_source: str = "manual") -> int | None:
    """学习模式记一笔做题结果；**做错 → 当场进复习队列**（方案三-13 的闭环那一环）。

    已有活跃错题时**不重置台阶、不记 lapse**：进度只由复习自评驱动，
    再错一次不该把人家爬到第 6 级的成果清零。
    """
    StudyAttemptRepo(conn, user_id).record(question_id, subject_id, result, submitted,
                                           grade_source=grade_source)
    if result != "wrong":
        return None
    repo = MistakeRepo(conn, user_id)
    existing = repo.active_for(question_id)
    if existing is not None:
        return existing["id"]
    review_date = clock.review_date_of(_rollover(conn, user_id))
    return repo.add(question_id, review_date, entry_reason="marked_wrong")
