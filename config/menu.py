"""侧边栏菜单定义。加页面 = 新蓝图挂路由 + 这里加一行，模板不动。

mode 决定在哪个模式下显示（学习 / 复习 / 都显示），role 决定谁能看见。
菜单只管导航不管权限（方案二-12、二-14）：真正拦住越权的是路由上的
`require_login()` / `require_admin()` 和数据层的 user_id 过滤。
visible=False 的条目表示功能还没做，先占位不显示，避免点过去 404。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MenuItem:
    key: str
    group: str
    label: str
    url: str
    mode: str = "both"          # study / review / both
    role: str = "member"        # member（人人可见）/ admin（仅管理员）
    icon: str = ""
    badge: str = ""             # 角标数据来源的键名，空表示无角标
    prefix: str = ""            # 高亮匹配前缀，子页面靠它保住高亮；空则用 url
    visible: bool = True


# 侧边栏从上到下的分组顺序。空组也要出现（见 `menu_groups`）。
GROUP_ORDER: tuple[str, ...] = ("学习", "复习", "账户", "管理")

# 哪些组是"模式专属"的：切到复习模式就不该再看见学习组那一栏（哪怕它是空的），
# 否则两行"这里还没有能用的功能"同时挂着，等于没告诉用户切换有没有生效。
GROUP_MODE = {"学习": "study", "复习": "review"}

MENU = [
    # ---------------------------------------------------------- 学习模式
    MenuItem("study_home", "学习", "我的题目", "/study/", mode="study", icon="book",
             prefix="/study", visible=True),
    MenuItem("study_new", "学习", "手动录题", "/study/new", mode="study", icon="pen",
             prefix="/study/new", visible=True),
    MenuItem("study_drill", "学习", "题库刷题", "/study/drill", mode="study", icon="layers",
             prefix="/study/drill", visible=True),
    MenuItem("knowledge", "学习", "知识点", "/knowledge/", mode="study", icon="tag",
             prefix="/knowledge", visible=True),
    MenuItem("knowledge_appeal", "学习", "我的知识点申请", "/knowledge/mine", mode="study",
             icon="clock", prefix="/knowledge/mine", visible=True),
    MenuItem("import", "学习", "导入", "/import/", mode="study", icon="upload", visible=True),
    MenuItem("favorite", "学习", "收藏", "/favorite/", mode="both", icon="star", visible=False),
    MenuItem("tag", "学习", "标签", "/tag/", mode="study", icon="hashtag", visible=False),

    # ---------------------------------------------------------- 复习模式
    MenuItem("review_today", "复习", "今日复习", "/review/today", mode="review", icon="sun",
             prefix="/review", badge="due_count", visible=True),
    MenuItem("review_invalid", "复习", "已失效的题目", "/review/invalid", mode="review",
             icon="warning", badge="invalid_count", visible=False),
    MenuItem("stats", "复习", "统计", "/review/stats", mode="review", icon="chart",
             visible=True),
    MenuItem("trash", "复习", "回收站", "/review/trash", mode="review", icon="trash",
             visible=True),

    # ---------------------------------------------------------- 账户（两种模式都显示）
    MenuItem("home", "账户", "首页", "/", mode="both", icon="home"),
    MenuItem("settings", "账户", "设置", "/settings/", mode="both", icon="gear",
             prefix="/settings", visible=True),
    MenuItem("appeal", "账户", "申诉与反馈", "/appeal/", mode="both", icon="chat", visible=False),

    # ---------------------------------------------------------- 管理（仅 admin）
    # ★ 后台路由还没写，先全部 visible=False 占位：否则 admin 一登录就看到一排 404 链接。
    #   每做完一页就把对应的 False 去掉，别一次全开。
    MenuItem("admin_subject", "管理", "科目", "/admin/subject", role="admin", icon="book",
             visible=False),
    MenuItem("admin_knowledge", "管理", "知识点审核", "/admin/knowledge", role="admin",
             icon="check", visible=False),
    MenuItem("admin_question", "管理", "题目收起", "/admin/question", role="admin", icon="eye",
             visible=False),
    MenuItem("admin_archive", "管理", "隐藏库", "/admin/archive", role="admin", icon="box",
             visible=False),
    MenuItem("admin_import", "管理", "官方导入", "/admin/import", role="admin", icon="upload",
             visible=False),
    MenuItem("admin_appeal", "管理", "申诉队列", "/admin/appeal", role="admin", icon="chat",
             visible=False),
    MenuItem("admin_user", "管理", "用户与角色", "/admin/user", role="admin", icon="users",
             visible=False),
]


def visible_menu(mode: str, role: str) -> list[MenuItem]:
    """按当前模式和角色过滤菜单。分组顺序沿用定义顺序。"""
    items = []
    for item in MENU:
        if not item.visible:
            continue
        if item.role == "admin" and role != "admin":
            continue
        if item.mode not in (mode, "both"):
            continue
        items.append(item)
    return items


def menu_groups(mode: str, role: str) -> list[tuple[str, list[MenuItem]]]:
    """分组后的菜单，**空组也返回**（配 `prompts.MENU_GROUP_EMPTY` 显示一行说明）。

    为什么要返回空组：切到复习模式时如果那一组一条都没有，页面就是一片空白，
    用户会以为程序坏了；给一句"今日复习在第 9 步"才是诚实的样子。
    """
    groups: list[tuple[str, list[MenuItem]]] = []
    for name in GROUP_ORDER:
        if name == "管理" and role != "admin":
            continue
        if GROUP_MODE.get(name) not in (None, mode):
            continue
        groups.append((name, [item for item in visible_menu(mode, role) if item.group == name]))
    return groups


def is_active(item: MenuItem, path: str) -> bool:
    """当前页高亮。子页面靠前缀保住高亮，所以比较的是 `prefix or url`。"""
    return path == item.url or (item.prefix and path.startswith(item.prefix))
