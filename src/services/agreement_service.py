"""协议业务层（方案三-16a）：谁该弹哪一版、同意了没有。

★ 判新旧一律用 `agreement.seq` 那个整数，不比版本号字符串。
★ 本层只管"站点协议登录后必须先同意"这一道门；共享须知（`gate=False`）
  是步 19 点「共享」按钮时才弹，走的是同一套表与记录，不另建机制。
"""

from config import agreement
from src.data.repository.agreement_repo import AgreementRepo, UserAgreementRepo


def pending_version(conn, user_id: int):
    """这个账号现在必须先同意哪一版；没有则 None。"""
    repo = UserAgreementRepo(conn, user_id)
    for key, spec in agreement.KINDS.items():
        if not spec.gate:
            continue
        version = agreement.CURRENT[key]
        if not repo.agreed(version):
            return version
    return None


def viewable(conn, user_id: int, version: str) -> bool:
    """这一版能不能给这个人看：当前生效的那一版，或他自己同意过的历史版本。

    ★ 不这么限就等于 `/agreement/SITE-99` 也能开出一个空壳页，
      看着像"协议丢了"，其实是被随便编的版本号钓出来的。
    """
    if version in agreement.CURRENT.values():
        return True
    return UserAgreementRepo(conn, user_id).agreed(version)


def body(conn, version: str) -> dict:
    """取正文。库里没有这一版就是部署漏了 seed——给一句实话，不编一份默认文本出来。"""
    row = AgreementRepo(conn).by_version(version)
    if row is None:
        return {"version": version, "title": version, "content": "（这一版的正文还没入库。）",
                "effective_from": ""}
    return {"version": row["version"], "title": row["title"], "content": row["content"],
            "effective_from": row["effective_from"]}


def accept(conn, user_id: int, version: str) -> None:
    UserAgreementRepo(conn, user_id).record(version)
