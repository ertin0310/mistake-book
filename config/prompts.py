"""所有给用户看的中文。措辞改在这里，逻辑代码一行不动。

分四组：档位文案、预选映射、提示与报错、还原冲突。
"""

# --------------------------------------------------------------- 档位文案

# 复习自评：机器值 1–4，界面显示中文，也接受键盘数字。
RATING_LABELS = {
    1: "熟悉啦",
    2: "记住啦",
    3: "一般般",
    4: "没记住",
}

# 耗时判档：四个区间决定默认预选哪一档，绝不自动提交。
DURATION_BANDS = {
    1: "很简单",
    2: "会了",
    3: "模糊",
    4: "忘了",
}

# 耗时四档 → 自评档位的默认预选。两边都是 1–4，恒等映射；
# 单独写出来是因为这两套刻度语义上不等价，将来要错开只改这里。
PRESELECT_MAP = {1: 1, 2: 2, 3: 3, 4: 4}

SLOW_HINT = "这题花的时间偏长，是不是没吃透"

# 科目复习记录不足这个条数时，耗时判档不启用：样本太少，中位数没有意义。
MIN_DURATION_SAMPLES = 10

# --------------------------------------------------------------- 提示与报错

LOGIN_REQUIRED = "请先登录。"
NOT_FOUND = "这条记录不在你的错题本里。可能是链接串了，也可能它已经被移入回收站。"
FORBIDDEN = "你没有权限做这件事。"
CSRF_FAILED = "这个页面放得太久了，请刷新后重试。"
SERVER_ERROR = "程序出了点意外，已经记下来了，你可以退回上一页重试。"

USERNAME_TAKEN = "这个用户名已经被用了，换一个。"
CREDENTIALS_WRONG = "用户名或密码不对。"
PASSWORD_CONFIRM_MISMATCH = "两次输入的密码不一样。"
PASSWORD_TOO_SHORT = "密码太短了，至少 8 位。"
USERNAME_TOO_LONG = "用户名太长了，20 个字以内。"
FIELD_REQUIRED = "必填项不能空着。"
INVALID_TIME = "时间格式不对，请用 24 小时的 HH:MM。"
ROLLOVER_DEFERRED = "这个时间点今天已经过了，新设置从明天开始生效。"
OUT_OF_RANGE = "这个数值超出可用范围。"
SUBJECT_UNUSABLE = "这个科目不存在或已经停用，请重新选一个。"

# --------------------------------------------------------------- 还原冲突

RESTORE_CONFLICT = {
    "mistake": "这道题已经在你的复习队列里了，不用还原。",
    "tag": "你已经有一个同名标签了，还原会重复。",
    "knowledge_point": "这个知识点已经存在，请直接选用。",
    "subject": "科目名已经占用，请先改一个再还原。",
    "question": "这道题你已经有一份了，不用重复还原。",
}

KNOWLEDGE_DUPLICATE_HINT = "已经有了，请直接选用。"

# --------------------------------------------------------------- 模式与菜单

MODE_LABELS = {"study": "学习", "review": "复习"}
DEFAULT_MODE = "study"

# 施工单步 5 定的甲：还没做的页面不出现在菜单里，那一组先给一行空状态，
# 免得切到复习模式看到一片空白，以为程序坏了。
MENU_GROUP_EMPTY = {
    "学习": "这一组还没有能用的入口。",
    "复习": "这一组还没有能用的入口。",
    "账户": "这一组还没有能用的入口。",
    "管理": "后台还没有开通。",
}

# --------------------------------------------------------------- 空状态文案

EMPTY_QUESTIONS = "还没有题目。先录一道，复习才有东西排。"
EMPTY_POOL = "共享池暂时是空的——等有人共享题目，这里就会列出内容。"
EMPTY_QUEUE = "今天没有到期的错题。先去学习模式做几道题，做错的会自动排进来。"
EMPTY_TRASH = "回收站是空的。删掉的东西会在这儿留 30 天。"
EMPTY_TRASH_GROUP = "这一类还没有内容。"
EMPTY_IMPORT = "本次没有可导入的内容，请检查文件格式与列名。"
EMPTY_STATS_TREND = "这 30 天还没有复习记录。去「今日复习」刷几道，这张图就有了。"
EMPTY_STATS_WEAK = "暂时没有能统计的错题知识点（已下架的知识点不参与排行，也不报错）。"


# --------------------------------------------------------------- 复习页

HIDDEN_QUESTION_NOTICE = "有 {count} 道题暂时不能复习（作者已撤走或被官方收起），恢复可见后会自动回到队列里。"
CAP_OVERFLOW_NOTICE = "今日另有 {count} 道题到期，已到每日上限未安排。"
CAP_MORE_BUTTON = "再加 10 题"
ANSWER_HIDDEN_BUTTON = "看答案"
SHARED_MARK = "已共享"
DELISTED_MARK = "知识点已下架"
PURGED_NOTE = "已过期 {count} 条，不再出现在这里，也不影响你的复习。"


# --------------------------------------------------------------- 导入与导出

SUBJECT_UNUSABLE_TITLE = "这个科目用不了"
IMPORT_EMPTY_FILE = "所选文件没有内容，请确认后再导入。"

EXPORT_BUTTON = "导出 CSV"
EXPORT_KIND_LABELS = {"questions": "题目清单", "review_log": "复习记录"}
EXPORT_NOTICES = {
    "questions": "这一份可以直接再导回来（列名、答案格式和导入模板一模一样）。",
    "review_log": "复习流水只导出、不导回——它是历史，不是可编辑的数据。",
}


# --------------------------------------------------------------- 知识点（步 18）

KP_NAME_REQUIRED = "知识点名字不能空着。"
KP_NAME_LIMIT = 60
KP_NAME_TOO_LONG = "知识点名字太长了，最多 {limit} 个字。"
KP_EXISTS = "这一科下已经有同名知识点：{names}。"
KP_EXISTS_HINT = "如果这不是同一个知识点，勾上下面那颗「这不是同一个知识点」再提交。"
KP_SUBMITTED = "提交好了：现在全都能用，同时已进待审队列。"
KP_RESUBMITTED = "改好了，这一条重新回到待审。"
KP_PENDING_NOTE = "管理员还没看过。不影响你现在就用。"
KP_REJECTED_NOTE = "驳回原因：{note}"
KP_HIDDEN_NOTE = "已被下架，只有你看得见这一条。"
KP_NOT_SAME = "这不是同一个知识点"
KP_STATUS_LABELS = {"approved": "在用", "rejected": "被驳回", "hidden": "已下架"}
EMPTY_KP_POOL = "这一科下还没有知识点。提交一条，别人马上能用。"
EMPTY_KP_MINE = "你还没提交过知识点。"


# --------------------------------------------------------------- 协议（步 19 前置）

AGREEMENT_TITLE = "请先阅读并同意《{title}》"
AGREEMENT_VERSION_NOTE = "当前版本 {version} · {effective} 起生效"
AGREEMENT_BUTTON = "我已阅读并同意"
AGREEMENT_DECLINE = "不同意，退出登录"
AGREEMENT_DECLINE_NOTE = "不同意也可以退出，你已有的数据不会被删除。"
AGREEMENT_ACCEPTED = "已记录你的同意。"
AGREEMENT_GATE = "使用之前请先同意《站点协议》。"
KP_SAME_SUBJECT_CLASH = "同一科目下同名只能有一条：请换个更具体的名字，或者到别的科目下建。"

# --------------------------------------------------------------- 判分与改判（步 21）

MACHINE_RIGHT = "机器判分：对了。"
MACHINE_WRONG = "机器判分：错了。"
MACHINE_NONE = "这道题机器判不了（简答题），你自己看着评。"
PRESELECT_HINT = "按耗时算，这一档默认选中；觉得不对就点别的一档。"
PRESELECT_BASELINE = "该科历史中位耗时 {seconds} 秒（样本 {count} 条）"
PRESELECT_OFF = "这一科的复习记录还不到 {count} 条，先不按耗时预选。"
OPTIONS_TITLE = "选项"
RETRACT_BUTTON = "我其实答对了，收回这道错题"
RETRACTED = "已经收回，这道题不再排进复习队列了。"
RETRACT_REFUSED = "这道题已经复习过，或者不是自动排进来的，不能收回（历史要留着）。"

# --------------------------------------------------------------- 导入页说明文案

IMPORT_LEAD = "批量导入支持题目、知识点、科目三类对象，文件可以是 CSV 或 JSONL。"
IMPORT_HOWTO = "导入分两步：先上传预览，逐行核对无误后再确认入库。被拦下的行会标明行号与原因，其余行照常导入，不会整批失败。"
IMPORT_COLUMNS_TITLE = "每一列写什么"
IMPORT_EXAMPLE_TITLE = "可直接复制的示例"
IMPORT_EXAMPLE_CSV = "CSV 示例（表头 + 三行）"
IMPORT_EXAMPLE_JSONL = "JSONL 示例（一行一道题）"
IMPORT_PROMPT_TITLE = "让 AI 帮你把图片变成题目"
IMPORT_PROMPT_HOW = ("把下面这段提示词连同题目图片一起交给大模型，把它输出的整段文本粘贴回本页的「粘贴文本」框即可。识别结果不会直接入库，仍要经过逐行校验与你的确认。")
IMPORT_PASTE_LABEL = "粘贴模型输出的 JSONL 文本"
IMPORT_PASTE_BUTTON = "预览粘贴的内容"
IMPORT_TEMPLATE_BUTTON = "下载 CSV 模板文件"
IMPORT_TEMPLATE_JSONL_BUTTON = "下载 JSONL 模板文件"
IMPORT_IMAGE_NOTE = "图片类题目暂不支持批量导入：请先用占位文本导入题目正文，导入后在题目详情页手动补图。"
IMPORT_NO_FILE = "请先选择一个文件。"
IMPORT_TOO_LARGE = "文件超出大小限制（单个最大 2 MB），请拆分后再导入。"
IMPORT_TARGET_LABEL = "导入对象"
IMPORT_FORMAT_LABEL = "文件格式"
IMPORT_FILE_LABEL = "选择文件"
IMPORT_PREVIEW_BUTTON = "上传并预览"
IMPORT_COPY_HINT = "点右侧按钮可复制"
IMPORT_COPY_BUTTON = "复制"
IMPORT_COPIED = "已复制到剪贴板"
IMPORT_PASTE_PLACEHOLDER = "一行一道题，例如：{\"type\":\"essay\",\"subject\":\"数学\",\"stem\":\"...\",\"options\":[],\"answer\":{\"text\":\"...\"},\"explanation\":\"\",\"knowledge_points\":[\"...\"]}"

# --------------------------------------------------------------- 共享（步 19）

SHARE_BUTTON = "共享"
UNSHARE_BUTTON = "取消共享"
SHARE_TERMS_TITLE = "共享之前请先读一遍"
SHARE_TERMS_WILL = ("共享后会发生这些：答案解析与配图会随题目一并公开；别人可以把这道题存进自己的错题本；你之后改动题面，改动对已存题的人不生效（他们存的是当时那一份）。")
SHARE_ONCE_BUTTON = "仅本次同意并共享"
SHARE_ALWAYS_BUTTON = "同意并授予长期授权（以后不再弹）"
SHARE_CANCEL_BUTTON = "取消，暂不共享"
SHARED_ONCE = "已共享，别人在共享池里能刷到这道题了。"
SHARED_ALWAYS = "已共享，并记住了你的长期授权；须知正文升版后会再请你确认一次。"
SHARE_CANCELLED = "没有共享，这道题仍然只有你自己看得到。"
UNSHARED = "已取消共享。已经存了这道题的人不受影响。"
