"""导入的列规格（方案三-14）。

**加一个新目标 = 这里加一份列规格，清洗/校验/报行号/预览那一整条链全复用**；
加一个新格式 = `importers/` 里加一个实现类。两件事都不碰业务代码。

`required` 为空的列在预览里报"必填项不能空着"并给**行号**——
题目 S4 明写"报错精确到行"，一句"格式错误"是不得分的。
"""

# ---------------------------------------------------------------- 题目

QUESTION_COLUMNS = ("type", "subject", "stem", "options", "answer", "explanation",
                    "knowledge_points")
QUESTION_REQUIRED = ("type", "subject", "stem", "answer")
QUESTION_MAXLEN = {"stem": 1000, "answer": 2000, "explanation": 4000, "options": 4000}

# ---------------------------------------------------------------- 知识点

KNOWLEDGE_COLUMNS = ("subject", "name")
KNOWLEDGE_REQUIRED = ("subject", "name")
KNOWLEDGE_MAXLEN = {"name": 60}

# ---------------------------------------------------------------- 科目

SUBJECT_COLUMNS = ("name",)
SUBJECT_REQUIRED = ("name",)
SUBJECT_MAXLEN = {"name": 30}

SPECS = {
    "question": {"columns": QUESTION_COLUMNS, "required": QUESTION_REQUIRED,
                 "maxlen": QUESTION_MAXLEN, "label": "题目"},
    "knowledge_point": {"columns": KNOWLEDGE_COLUMNS, "required": KNOWLEDGE_REQUIRED,
                        "maxlen": KNOWLEDGE_MAXLEN, "label": "知识点"},
    "subject": {"columns": SUBJECT_COLUMNS, "required": SUBJECT_REQUIRED,
                "maxlen": SUBJECT_MAXLEN, "label": "科目"},
}

# 多值分隔：知识点一格里用分号隔开（★ 不用逗号，逗号是 CSV 自己的分隔符）
MULTI_VALUE_SEPARATOR = ";"

# 每列的中文名与写法说明。导入页那张"要哪些列、每列写什么"的表就是从这儿渲染的，
# 所以加一列只改这一处，页面与校验不会各说一套。
COLUMN_DOCS = (
    ("type", "题型", "必填。填 choice（选择）、blank（填空）、essay（简答）三个之一。"),
    ("subject", "科目", "必填。写科目全名，须是系统里已存在且未停用的科目。"),
    ("stem", "题干", "必填。题目正文，可含标点与换行；在 CSV 里整格用英文双引号包住即可换行。"),
    ("options", "选项", "选择题必填：一行写一个选项，顺序即 A、B、C……其余题型留空。"),
    ("answer", "参考答案", "必填。选择题写字母（多选连着写，如 AC）；填空题一行一个空，"
                          "同一空的多种可接受写法用竖线隔开；简答题直接写整段文字。"),
    ("explanation", "解析", "可空。这道题为什么这么做；共享出去时解析会随题目一并公开。"),
    ("knowledge_points", "知识点", "可空。多个知识点用分号隔开；系统里没有的会先列出来问你。"),
)

# ---------------------------------------------------------------- 复习记录（只导出不导回）

REVIEW_COLUMNS = ("reviewed_on", "reviewed_at", "stem", "rating", "rating_source",
                  "interval_before", "interval_after", "due_date_before", "due_date_after",
                  "duration_seconds")
