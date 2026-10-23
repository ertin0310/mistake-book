"""回收站与隐藏库的实体注册表（方案三-24 ★）。

**为什么是一张注册表而不是四套代码**：知识点、科目、标签、错题、题目这五样
都要"软删 → 能看见 → 能还原 → 还原可能撞唯一约束"，逻辑一模一样，只有
「哪一列算删除」「什么算在用」「撞了提示哪句话」不同。第四种东西要进库房
= 这里加一个注册项，不重写一套——这是"封装"最实的证据。

★ `in_use_where` 必须与 `schema.sql` 里 partial unique 索引的 WHERE 条件
  **逐字一致**（三-12a）。两边一旦不一致，就会出现"预检说没有、插入却报重复"
  这种最难查的错。`tests/test_archive_registry.py` 拿 schema 文本比对钉住它。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EntitySpec:
    key: str
    table: str
    label: str
    title_column: str                    # 列表页显示用的那一列
    in_use_where: str                    # "什么算在用"——与 partial unique 条件逐字一致
    conflict_prompt_key: str             # config/prompts.py 里 RESTORE_CONFLICT 的键名
    deleted_column: str = "deleted_at"
    owner_column: str | None = "user_id"  # None = 没有归属人（字典表）
    purge_column: str | None = None       # 只有 mistake 有"过期封存"这一说
    unique_columns: tuple[str, ...] = ()  # 撞名字的那几列——还原预检按它比对（必须放最后：前面有带默认值的字段）


ENTITIES: dict[str, EntitySpec] = {
    "mistake": EntitySpec(
        key="mistake", table="mistake", label="错题", title_column="question_id",
        in_use_where="deleted_at IS NULL",
        conflict_prompt_key="mistake", purge_column="purged_at",
        unique_columns=("user_id", "question_id")),
    "tag": EntitySpec(
        key="tag", table="tag", label="标签", title_column="name",
        in_use_where="deleted_at IS NULL",
        conflict_prompt_key="tag", unique_columns=("user_id", "name")),
    "knowledge_point": EntitySpec(
        key="knowledge_point", table="knowledge_point", label="知识点", title_column="name",
        in_use_where="deleted_at IS NULL AND status = 'approved'",
        conflict_prompt_key="knowledge_point", owner_column="created_by_user_id",
        unique_columns=("subject_id", "name_normalized")),
    "subject": EntitySpec(
        key="subject", table="subject", label="科目", title_column="name",
        in_use_where="deleted_at IS NULL AND status = 'active'",
        conflict_prompt_key="subject", owner_column=None, unique_columns=("name",)),
    # 题目进的是隐藏库那一格，判据是 `delisted_by`（管理员收起），**不是 deleted_at**：
    # 管理员从不写别人的删除标记，否则那条删除会落进作者自己的回收站（三-23）。
    "question": EntitySpec(
        key="question", table="question_bank", label="题目", title_column="stem",
        in_use_where="deleted_at IS NULL AND delisted_by IS NULL",
        conflict_prompt_key="question"),
}

# 隐藏库的三格（方案三-24 表）：管理员才进得来，用户侧不出现"隐藏库"这个词
HIDDEN_COMPARTMENTS = ("subject", "knowledge_point", "question")

# 永不物理删的表（被引用过就一直留在库里）
NEVER_PHYSICALLY_DELETED = frozenset({"question_bank", "knowledge_point", "subject", "mistake"})
