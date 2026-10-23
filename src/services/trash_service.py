"""回收站（方案三-12）。用户只看自己扔进去的东西，"隐藏库"这个词不对用户出现。

★ 还原前一定先过 `ArchiveRepo` 的冲突预检；被拦下时抛 `RestoreConflictError`，
  由统一异常出口翻成中文，**绝不 `except` 后静默**。
★ 30 天清理是**查询时顺手做的懒清理**，不依赖后台常驻进程。
"""

from config import archive
from src.data.repository.archive_repo import ArchiveRepo
from src.data.repository.question_repo import QuestionRepo
from src.domain import clock

TRASH_ENTITIES = ("question", "mistake", "tag")


def listing(conn, user_id: int) -> dict:
    """三格内容 + 底部那句"已过期 N 条"。"""
    repo = ArchiveRepo(conn, user_id)
    repo.purge_expired()                       # 懒清理：打开回收站时顺手做
    groups = []
    for entity in TRASH_ENTITIES:
        spec = archive.ENTITIES[entity]
        rows = repo.list_trash(entity, user_id)
        groups.append({"label": spec.label, "key": entity,
                       "rows": [_describe(repo, entity, row) for row in rows]})
    return {"groups": groups, "expired": repo.count_expired(),
            "retention_days": 30, "today": clock.review_date_of("00:00").isoformat()}


def restore(conn, user_id: int, entity: str, row_id: int) -> None:
    if entity not in TRASH_ENTITIES:
        raise ValueError(f"{entity} 不进回收站")
    ArchiveRepo(conn, user_id).restore_from_trash(entity, row_id, user_id)


def _describe(repo: ArchiveRepo, entity: str, row) -> dict:
    """列表页要显示"这是什么"，但**不在模板里查库**：这里一次把标题取出来。"""
    spec = archive.ENTITIES[entity]
    title = row[spec.title_column]
    if entity == "mistake":
        question = QuestionRepo(repo.conn, repo.actor_id).any_visible(row["question_id"])
        title = question["stem"] if question else f"题目 #{row['question_id']}"
    return {"id": row["id"], "title": str(title)[:60],
            "deleted_at": (row[spec.deleted_column] or "")[:10]}
