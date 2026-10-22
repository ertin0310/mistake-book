"""admin 清单：哪些路由、哪些菜单项需要管理员。

权限只有两层（方案二-14）：`require_login()` 与 `require_admin()`。
判"是不是 admin"的地方全站只此一份清单，模板里不许写散判的 `if admin`。

★ `require_admin()` 只挡**写操作和后台页面**，绝不让 admin 跳过 `user_id` 过滤——
管理员读不到任何私有记录（三-23 四条禁令），所以这里列的全是"动作"，没有"数据"。
"""

# 需要管理员的蓝图端点（步 23 的后台七页会往这里加）。
ADMIN_ENDPOINTS: frozenset[str] = frozenset({
    "auth.nothing_yet",      # 占位：本步还没有 admin 路由，清单先存在才有地方加
})

# 需要管理员才显示的菜单分组键（`config/menu.py` 用同一份判断）。
ADMIN_MENU_GROUPS: frozenset[str] = frozenset({"admin"})

ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"


def is_admin_endpoint(endpoint: str | None) -> bool:
    return endpoint in ADMIN_ENDPOINTS


def is_admin_role(role: str | None) -> bool:
    return role == ROLE_ADMIN
