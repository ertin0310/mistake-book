"""科目业务层（方案三-5）。本期科目由 seed 预置，**普通用户只能选用、不能新建**。

写操作（建/改名/停用）不在这里——那是步 23 后台 `/admin/subject` 的活，
必须先过 `require_admin()`。本文件只负责"读给下拉用"和"录题时校验选得对不对"。
"""

from config import prompts
from src.data.repository.subject_repo import SubjectRepo
from src.domain.errors import ValidationError


def options(conn) -> list:
    """下拉框数据：`[(id, 名称), ...]`，只含可见科目。"""
    return [(row["id"], row["name"]) for row in SubjectRepo(conn).options()]


def require_usable(conn, subject_id) -> int:
    """录题/筛选时校验科目。返回合法的 id；选到下架或不存在的科目给中文提示。"""
    try:
        key = int(subject_id)
    except (TypeError, ValueError):
        raise ValidationError(prompts.SUBJECT_UNUSABLE) from None
    if not SubjectRepo(conn).is_usable(key):
        raise ValidationError(prompts.SUBJECT_UNUSABLE)
    return key


def name_map(conn) -> dict:
    return SubjectRepo(conn).name_map()
