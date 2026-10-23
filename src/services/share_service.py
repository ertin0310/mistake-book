"""共享开关与《共享须知》三态（方案三-10、三-16a）。

★ 默认私有：`visibility` 的默认值是 private，共享必须用户主动点，且**点的第一下
  先弹须知**，不是直接共享出去。三颗按钮各有不同后果：
    仅本次同意   → 只共享这一道，不记长期授权（下次还会弹）
    同意并长期授权 → 记一条 user_agreement，绑当前版本号，之后不再弹
    取消暂不共享  → 什么都不做
★ 须知升版（`agreement.CURRENT["share"]` 一改）弹过旧版的人必须再弹一次。
"""

from config import agreement
from src.data.repository.agreement_repo import UserAgreementRepo
from src.data.repository.question_repo import QuestionRepo
from src.domain.errors import NotFoundError
from config import prompts
from src.services import agreement_service

DECISIONS = ("once", "always", "cancel")


def needs_terms(conn, user_id: int) -> bool:
    """这个人现在需不需要先看须知：长期授权没绑在当前生效版本上就要弹。"""
    version = agreement.CURRENT["share"]
    return not UserAgreementRepo(conn, user_id).agreed(version)


def terms(conn, user_id: int) -> dict:
    version = agreement.CURRENT["share"]
    doc = agreement_service.body(conn, version)
    doc["always"] = not needs_terms(conn, user_id)
    return doc


def decide(conn, user_id: int, question_id: int, decision: str) -> str:
    """按三态之一处理，返回给用户看的结论词。"""
    if decision not in DECISIONS:
        raise ValueError(f"未知的决定：{decision}")
    if decision == "cancel":
        return "cancel"
    if decision == "always":
        UserAgreementRepo(conn, user_id).record(agreement.CURRENT["share"])
    _require_mine(conn, user_id, question_id)
    QuestionRepo(conn, user_id).set_visibility(question_id, shared=True)
    return "shared_always" if decision == "always" else "shared"


def unshare(conn, user_id: int, question_id: int) -> None:
    _require_mine(conn, user_id, question_id)
    QuestionRepo(conn, user_id).set_visibility(question_id, shared=False)


def require_mine(conn, user_id: int, question_id: int) -> None:
    """路由在弹须知之前就要问过这道题是不是他的。"""
    _require_mine(conn, user_id, question_id)


def _require_mine(conn, user_id: int, question_id: int) -> None:
    """不是自己的（或不存在）一律 404——共享按钮不该成为探别人题号的探针。"""
    if QuestionRepo(conn, user_id).mine_one(question_id) is None:
        raise NotFoundError(prompts.NOT_FOUND)
