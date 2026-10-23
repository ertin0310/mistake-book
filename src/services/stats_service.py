"""统计（方案三-19、二-7）：四张图要的数字全在这一层算，模板只负责摆。

★ 三条口径写死在这儿，改口径只改配置：
  - 掌握度一律按 `mistake.step_index` 分四格，边界在 `config/schedule.py`；
    **不引入第二个"掌握度"字段**（二-7 零状态优先，能从已有列推出来的就不新建列）。
  - 热力图、近 30 天、今日，全部按复习日 `reviewed_on`（三-3），代码里没有第二个日历概念。
  - 排行与统计只算"当前能用"的知识点（approved 且没软删），已下架的不参与也不报错（三-6）。
  - 取数一律走 repo 的具名读法，SQL 不越过数据层（二-4）。
"""

from collections import Counter
from datetime import date, timedelta

from config import schedule
from src.data.repository.knowledge_repo import KnowledgeRepo, USABLE
from src.data.repository.mistake_repo import MistakeRepo
from src.data.repository.question_repo import QuestionRepo
from src.data.repository.study_attempt_repo import ReviewLogRepo, StudyAttemptRepo
from src.data.repository.subject_repo import SubjectRepo
from src.domain import clock

BAD_RATINGS = (3, 4)             # 「一般般」和「没记住」都算没掌握住（1/2 才是记住了）
TREND_DAYS = 30
HEATMAP_DAYS = 45
WEAK_LIST_SIZE = 8


def overview(conn, user_id: int) -> dict:
    review_date = clock.review_date_of("00:00")
    mistakes = MistakeRepo(conn, user_id).rows_active()
    logs = ReviewLogRepo(conn, user_id).rows()
    attempts = StudyAttemptRepo(conn, user_id).rows()
    cells = heatmap(logs, review_date)
    series = trend(logs, review_date)
    mastery = mastery_distribution(mistakes)
    weak = weak_points(conn, user_id, logs, attempts)
    return {
        "review_date": review_date,
        "mastery": mastery,
        "mastery_max": max([item["count"] for item in mastery] + [1]),
        "heatmap": cells,
        "heatmap_weeks": heatmap_weeks(cells),
        "heatmap_max": max([cell["count"] for cell in cells] + [1]),
        "trend": series,
        "trend_shapes": trend_shapes(series),
        "weak_points": weak,
        "weak_max": max([item["count"] for item in weak] + [1]),
        "today": today_counts(review_date, mistakes, logs, attempts),
    }


# ---------------------------------------------------------------- 一、掌握度分布

def mastery_distribution(mistakes) -> list:
    """四格计数。`[下界, 上界)` 左闭右开；台阶到 7 就是顶格，不再往上加字段。

    ★ 四格必须**分完且不重叠**：选「完全没记住」会把台阶打回 0，而 `review_count` 已经
      不是 0 了。这种"动过手又退回原点"的行如果按原文那句话谁都不进，柱子加起来就等于
      少了若干道，图开始骗人。所以这里把它抬进"刚上手"——它确实开始过。
      格名与边界一律读 `schedule.MASTERY_BANDS`，改口径只改配置。
    """
    counts = Counter()
    for row in mistakes:
        reviewed = int(row["review_count"] or 0)
        step = max(int(row["step_index"] or 0), 1) if reviewed else int(row["step_index"] or 0)
        for key, _label, low, high in schedule.MASTERY_BANDS:
            if low <= step < high:
                counts[key] += 1
                break
    return [{"key": key, "label": label, "count": counts[key]}
            for key, label, _low, _high in schedule.MASTERY_BANDS]


# ---------------------------------------------------------------- 二、复习热力图

def heatmap(logs, review_date: date) -> list:
    """最近 45 个复习日，每格记那天评了几道。

    ★ 没数据的日子也照样出格：热力图的价值恰恰在"哪几天是空的"，
      只返回有数据的那几天会画出一条骗人的直线。
    """
    by_day = Counter(clock.parse_date(row["reviewed_on"]) for row in logs)
    start = review_date - timedelta(days=HEATMAP_DAYS - 1)
    return [{"date": start + timedelta(days=offset), "count": by_day[start + timedelta(days=offset)]}
            for offset in range(HEATMAP_DAYS)]


# ---------------------------------------------------------------- 三、近 30 天趋势

def trend(logs, review_date: date) -> list:
    """近 30 天逐日：评了几道、其中几道没记住。"""
    recent = [row for row in logs
              if clock.parse_date(row["reviewed_on"]) > review_date - timedelta(days=TREND_DAYS)]
    total = Counter(clock.parse_date(row["reviewed_on"]) for row in recent)
    missed = Counter(clock.parse_date(row["reviewed_on"]) for row in recent
                     if int(row["rating"]) in BAD_RATINGS)
    return [{"date": day, "total": count, "missed": missed[day]}
            for day, count in sorted(total.items())]


# ---------------------------------------------------------------- 四、薄弱知识点

def weak_points(conn, user_id: int, logs, attempts, limit: int = WEAK_LIST_SIZE) -> list:
    """两个错源同权、错一次计一次（三-19）：学习模式做错 + 复习自评没记住。

    ★ 只数当前能用的那些知识点：题目被删/被收起不算，知识点被下架也不算，
      并且不弹任何错——统计页上出现"有东西看不见"的提示比少一根柱子更糟。
    """
    pool = PointPool(conn, user_id)
    mistakes = MistakeRepo(conn, user_id)
    tally = Counter()
    for row in attempts:
        if row["result"] == "wrong":
            tally.update(pool.keys_of_question(row["question_id"]))
    for row in logs:
        if int(row["rating"]) not in BAD_RATINGS:
            continue
        mistake = mistakes.get(row["mistake_id"])
        if mistake is not None:
            tally.update(pool.keys_of_question(mistake["question_id"]))
    subjects = SubjectRepo(conn).name_map()
    return [{"name": pool.name(key), "subject": subjects.get(key[0], ""), "count": count}
            for key, count in tally.most_common(limit)]


# ---------------------------------------------------------------- 今日四个数

def today_counts(review_date, mistakes, logs, attempts) -> dict:
    return {
        "queue": len(mistakes),
        "due": sum(1 for row in mistakes if clock.parse_date(row["due_date"]) <= review_date),
        "reviewed": sum(1 for row in logs
                        if clock.parse_date(row["reviewed_on"]) == review_date),
        "wrong_today": sum(1 for row in attempts
                           if row["result"] == "wrong"
                           and clock.parse_date(row["recorded_on"]) == review_date),
    }


# ---------------------------------------------------------------- 图的形状
#
# 把数据折成 SVG 坐标这件事放在这一层而不是模板里，有两个理由：
# 一、模板里写算式没人能测；二、坐标只有"一份算法"，图与数据才不会各说一套。

CHART_WIDTH, CHART_HEIGHT = 300, 80


def heatmap_weeks(cells) -> list:
    """把 45 天按周切成行，好让"哪几天空着"在竖着看时也对得上星期几。"""
    weeks, week = [], []
    for index, cell in enumerate(cells):
        if index == 0:
            week += [None] * (cell["date"].isoweekday() - 1)     # 第一行前面补空格
        week.append(cell)
        if len(week) == 7:
            weeks.append(week)
            week = []
    if week:
        weeks.append(week)
    return weeks


def trend_shapes(series) -> dict:
    """近 30 天折线的两组坐标，按最大值把高度归一到 `CHART_HEIGHT`。"""
    peak = max([row["total"] for row in series] + [1])
    def points(key):
        return " ".join(_point(index, row[key], peak) for index, row in enumerate(series))
    return {"total": points("total"), "missed": points("missed"), "peak": peak,
            "area": _area(series)}


def _point(index, value, peak) -> str:
    x = index * CHART_WIDTH / max(1, 29)
    y = CHART_HEIGHT - value * CHART_HEIGHT / peak
    return f"{x:.1f},{y:.1f}"


def _area(series) -> str:
    """折线下面那一片的面积坐标（含底边两个端点），用来填色。"""
    if not series:
        return ""
    peak = max(row["total"] for row in series) or 1
    top = [_point(index, row["total"], peak) for index, row in enumerate(series)]
    bottom = [f"{(len(series) - 1) * CHART_WIDTH / max(1, 29):.1f},{CHART_HEIGHT:.1f}",
              f"0.0,{CHART_HEIGHT:.1f}"]
    return " ".join(top + bottom)


# ---------------------------------------------------------------- 知识点名单缓存

class PointPool:
    """`(科目id, 归一化名) -> 展示名` 的查表器，外加"这道题挂了哪几个"。

    统计页要在几百行流水里反复查同一批知识点，所以一次把两份名单读进内存；
    两份都只装 `USABLE` 通过的行，口径与导入预检、回收站完全一致。
    """

    def __init__(self, conn, user_id: int):
        self.knowledge = KnowledgeRepo(conn, user_id)
        self.questions = QuestionRepo(conn, user_id)
        self._titles = {self._key(row): row["name"] for row in self.knowledge.usable_rows()}
        self._links: dict = {}

    def keys_of_question(self, question_id: int) -> set:
        if question_id not in self._links:
            visible = self.questions.any_visible(question_id) is not None
            keys = set()
            if visible:
                keys = {self._key(row) for row in self.knowledge.points_of_question(question_id)
                        if self._key(row) in self._titles}
            self._links[question_id] = keys
        return self._links[question_id]

    def name(self, key) -> str:
        return self._titles.get(key, "")

    @staticmethod
    def _key(row) -> tuple:
        return (row["subject_id"], row["name_normalized"])
