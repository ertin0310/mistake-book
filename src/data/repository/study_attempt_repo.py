"""`study_attempt`（学习模式做题记录）与 `review_log`（复习流水账）。

两张表分工不同，别混：
    study_attempt —— 学习模式里"这道题我做对还是做错"，是错题入队的唯一触发源
    review_log    —— 复习模式里"这道错题我评了第几档、间隔怎么变的"，**只追加不改**
"""

import sqlite3

from config import prompts
from src.data.repository.base import SCOPE_USER, BaseRepo
from src.domain import clock
from src.domain.errors import ValidationError

RESULT_CORRECT = "right"        # 词表跟 schema 的 CHECK 一致，不自造第二套
RESULT_WRONG = "wrong"
RESULTS = (RESULT_CORRECT, RESULT_WRONG)


class StudyAttemptRepo(BaseRepo):
    table = "study_attempt"
    scope = SCOPE_USER

    def attempted_on(self, review_date) -> set:
        """今天已经做过的题号。练习页靠它轮换，不会逮着一道题反复出。"""
        rows = self.conn.execute(
            "SELECT question_id FROM study_attempt WHERE user_id=:viewer AND recorded_on=:on",
            {"viewer": self.viewer_id, "on": clock.to_date_str(review_date)}).fetchall()
        return {row["question_id"] for row in rows}

    def record(self, question_id: int, subject_id: int, result: str,
               submitted: str = "", grade_source: str = "manual") -> int:
        if result not in RESULTS:
            raise ValidationError(prompts.FIELD_REQUIRED)
        review_date = clock.review_date_of("00:00")
        cursor = self.conn.execute(
            "INSERT INTO study_attempt (user_id, question_id, subject_id, result,"
            " grade_source, answer_submitted, recorded_on, created_at)"
            " VALUES (:viewer, :q, :subject, :result, :source, :submitted, :on,"
            " datetime('now','localtime'))",
            {"viewer": self.viewer_id, "q": question_id, "subject": subject_id,
             "result": result, "source": grade_source, "submitted": submitted,
             "on": clock.to_date_str(review_date)})
        self.conn.commit()
        return int(cursor.lastrowid)


class ReviewLogRepo(BaseRepo):
    table = "review_log"
    scope = SCOPE_USER

    def append(self, *, mistake_id: int, reviewed_on, reviewed_at: str, rating: int,
               rating_source: str, duration_seconds: int, move) -> int:
        """★ 只追加，永不 UPDATE（方案六）：这既是"间隔重复的历史可追溯"，
        也是将来换算法时能区分新旧数据的唯一依据。"""
        before, after = move.before, move.after
        cursor = self.conn.execute(
            "INSERT INTO review_log (user_id, mistake_id, reviewed_on, reviewed_at, rating,"
            " rating_source, duration_seconds, algorithm_version, interval_before,"
            " interval_after, due_date_before, due_date_after, step_before, step_after)"
            " VALUES (:viewer, :mistake, :on, :at, :rating, :source, :seconds, :algo,"
            " :ib, :ia, :db, :da, :sb, :sa)",
            {"viewer": self.viewer_id, "mistake": mistake_id,
             "on": clock.to_date_str(reviewed_on), "at": reviewed_at, "rating": rating,
             "source": rating_source, "seconds": max(0, int(duration_seconds)),
             "algo": move.algorithm_version,
             "ib": before.interval_days, "ia": after.interval_days,
             "db": clock.to_date_str(before.due_date),
             "da": clock.to_date_str(after.due_date),
             "sb": before.step_index, "sa": after.step_index})
        self.conn.commit()
        return int(cursor.lastrowid)

    def durations_for_subject(self, subject_id: int, limit: int = 200) -> list:
        """这一科历史复习耗时（秒）。耗时预选的中位数就从这里算。

        ★ 只取这个人自己的流水（`user_id` 在 where 里写死），别人的速度不该影响我的预选；
          题被删了也不影响——流水是历史事实，join 不上就少一条样本，不报错。
        """
        rows = self.conn.execute(
            "SELECT log.duration_seconds AS seconds FROM review_log log"
            " JOIN mistake m ON m.id = log.mistake_id"
            " JOIN question_bank q ON q.id = m.question_id"
            " WHERE log.user_id=:viewer AND q.subject_id=:subject AND log.duration_seconds > 0"
            " ORDER BY log.id DESC LIMIT :limit",
            {"viewer": self.viewer_id, "subject": int(subject_id), "limit": int(limit)}).fetchall()
        return [row["seconds"] for row in rows]

    def count_today(self, review_date) -> int:
        return int(self.conn.execute(
            "SELECT COUNT(*) FROM review_log WHERE user_id=:viewer AND reviewed_on=:on",
            {"viewer": self.viewer_id, "on": clock.to_date_str(review_date)}).fetchone()[0])
