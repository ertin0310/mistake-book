"""可见性判断：全站只有这一份，页面、后台、统计、鉴权都调它（方案三-24）。

为什么必须收成一处：这类规则一旦散落，就会出现"某个页面忘了过滤隐藏库"——
它的表现不是报错，而是多显示几条不该显示的数据，是最难查的一类 bug。

约定：`status` / `deleted_at` 一律传库里的原始值（None 或字符串），本模块不碰数据库。
"""

KP_ACTIVE = "approved"
SUBJECT_ACTIVE = "active"
SHARED = "shared"


def knowledge_point_visible(status: str, deleted_at: str | None,
                            creator_user_id: int | None, viewer_user_id: int | None) -> bool:
    """审核通过的知识点人人可见；被驳回或下架的只有作者本人还看得见
    （看得见才能看见驳回理由，也才能改后重提）。

    ★ "本人还看得见"只救状态，不救删除：软删掉的知识点进了回收站，
      对谁都不该再出现在选用下拉里，否则回收站和选用池会同时列出两条同名。
    """
    if deleted_at is not None:
        return False
    if status == KP_ACTIVE:
        return True
    return creator_user_id is not None and creator_user_id == viewer_user_id


def subject_visible(status: str, deleted_at: str | None) -> bool:
    """科目是纯字典，没有归属人概念：下架或删除后对所有人不可见，只在后台看得见。"""
    return deleted_at is None and status == SUBJECT_ACTIVE


def question_visible(visibility: str, deleted_at: str | None, delisted_by: int | None,
                     owner_user_id: int | None, viewer_user_id: int) -> bool:
    """题目可见性 = 自己的题（含自己已共享的）+ 别人共享且没被官方收起的。

    ★ `delisted_by` 是管理员的收起标记，它**不是** `deleted_at`：管理员从不写别人的
      删除标记，否则那条删除会落进作者自己的回收站，作者点「撤销删除」就把处罚翻掉了
      （方案三-23）。所以官方收起对谁都不可见，**包括作者**——他只能在失效页看到原因并申诉。
    """
    if delisted_by is not None:
        return False
    if owner_user_id is not None and owner_user_id == viewer_user_id:
        return deleted_at is None
    if deleted_at is not None:
        return False
    return visibility == SHARED


def occupies_name(status: str, deleted_at: str | None, active_state: str) -> bool:
    """这行还占不占名字——必须与 schema 里 partial unique 的条件逐字一致。

    两边不一致就会出现"提示说没有、插入却报重复"这种最难查的错（方案三-12a）。
    """
    return deleted_at is None and status == active_state


# ---------------------------------------------------------------- 统一入口

ENTITY_KNOWLEDGE = "knowledge_point"
ENTITY_SUBJECT = "subject"
ENTITY_QUESTION = "question"


def is_visible(entity: str, status: str | None, deleted_at: str | None,
               viewer_user_id: int | None, owner_user_id: int | None = None,
               delisted_by: int | None = None) -> bool:
    """全站唯一的那个 `is_visible()`（方案三-24）。页面、后台、统计、鉴权都只调它。

    三种实体的判据本来就不同（知识点看 status、科目看 status、题目看
    visibility + delisted_by），所以底层拆成三个具名函数各管一条规则、各配单测；
    这里只做分发，**不含任何判断逻辑**——这样"只有一份"这句话是真的，
    而调用点也只需要记一个名字。

    传参约定：`status` 一律是这一行的状态列原值；题目表没有 `status`，
    把 `visibility` 传进来即可（两列在语义上是同一件事：这行对外算什么状态）。
    """
    if entity == ENTITY_KNOWLEDGE:
        return knowledge_point_visible(status or "", deleted_at, owner_user_id, viewer_user_id)
    if entity == ENTITY_SUBJECT:
        return subject_visible(status or "", deleted_at)
    if entity == ENTITY_QUESTION:
        return question_visible(status or "", deleted_at, delisted_by,
                                owner_user_id, viewer_user_id)
    raise ValueError(f"未知的实体类型：{entity}")

