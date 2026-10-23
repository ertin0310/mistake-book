"""申诉与反馈的四类（方案三-25）。**加一类不改业务代码**，只在这里加一行。

`target` 决定这一类挂在什么对象上：`question` / `knowledge_point` / `none`。
入口有四处（账户组常驻页、失效题下、被驳回知识点下、查重拦截旁），
但表单只有一张——预填类型与对象，不各写一份。
"""

CATEGORIES = (
    ("action", "对管理员的处置有异议", "question"),
    ("rejection", "知识点被驳回，我认为判错了", "knowledge_point"),
    ("content", "题目内容有问题", "question"),
    ("other", "其他反馈", "none"),
)

LABELS = {key: label for key, label, _target in CATEGORIES}
TARGET_OF = {key: target for key, _label, target in CATEGORIES}
