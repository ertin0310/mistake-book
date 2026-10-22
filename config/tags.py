"""标签白名单（方案三-8）。

`tag_link.target_type` 只允许这几类，写进配置而不是散在代码里：
新增一种可打标签的东西 = 这里加一个名字，业务代码不动。
`none` 是收藏页两个 Tab 之外留的空值，不给打标签。
"""

TARGET_TYPES: tuple[str, ...] = ("question", "knowledge_point")

# seed 打标签、导入页给建议都用这一份；名字本身没有语义约束，只是别到处硬编码。
STARTER_TAGS: tuple[str, ...] = ("易错", "要重做", "考前看")
