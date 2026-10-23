"""演示数据：库为空时由 create_app() 自动跑一次（方案三-21）。

四条硬规矩写在这一个文件里：
1. 幂等——`user` 表有行就直接返回，绝不覆盖用户自己刷出来的数据。
2. `review_log` 必须由 `ladder.next_state()` 真算出来。随机编的间隔一眼就假
   （"选了没记住、间隔却从 7 天涨到 15 天"），会把 S6 和 S7 一起拉低。
3. 随机数一律用固定种子的 `random.Random`：同一份代码在任何机器上灌出的数据一致，
   测试才能对数字下断言。
4. 内容用考研数学/英语/政治/专业课的真实题型风格写，不要"题目1/答案1"。
"""

import csv
import json
import random
from datetime import date, datetime, timedelta

from config import csv_spec, schedule, settings, tags
from src.data import db
from src.data.repository.user_repo import UserRepo
from src.services import auth_service
from src.domain import normalize
from src.domain.scheduling import registry
from src.domain.scheduling.base import ReviewState

RNG = random.Random(20261021)

ADMIN = ("admin", "admin12345")
DEMO = ("demo", "demo12345")
EXTRA = [("stu1", "stu12345"), ("stu2", "stu12345")]

SUBJECTS = ["数学", "英语", "政治", "专业课"]

KNOWLEDGE = {
    "数学": ["牛顿第二定律", "摩擦力做功", "函数连续性", "中值定理", "级数收敛"],
    "英语": ["非谓语动词", "定语从句", "虚拟语气", "词根词缀"],
    "政治": ["剩余价值", "商品二因素", "矛盾的同一性"],
    "专业课": ["进程与线程", "数据库范式", "死锁四条件", "操作系统中断"],
}

# (科目, 知识点, 题干, 选项, 答案字母, 解析)
CHOICE = [
    ("数学", ["牛顿第二定律", "摩擦力做功"],
     "质量 m 的物块从粗糙斜面顶端由静止下滑，斜面高 h、斜面长 L。关于各力做功，说法正确的是（　）",
     ["重力做的功为 mgh，与路径无关", "支持力对物块做正功",
      "摩擦力做的功为 -fL，f 为滑动摩擦力", "合力做的功等于动能增加量减去摩擦产生的热"],
     "AC",
     "重力做功只看高度差，A 对；支持力与位移垂直不做功，B 错；摩擦力沿斜面向上、位移向下，"
     "做负功 -fL，C 对；合力做功就等于动能增量，不必再减摩擦生热，D 错。"),
    ("数学", ["函数连续性"],
     "设 f(x) 在 x=0 处连续，且 lim(x→0) f(x)/x 存在，则（　）",
     ["f(0)=0", "f(0)=1", "f(0) 可为任意值", "f(0) 不存在"],
     "A", "分母趋于 0 而极限存在，分子必须也趋于 0；连续把极限值交给 f(0)，所以 f(0)=0。"),
    ("数学", ["中值定理"],
     "下列定理中，要求函数在闭区间连续、开区间可导的是（　）",
     ["介值定理", "罗尔定理", "零点存在定理", "一致连续定义"],
     "B", "罗尔定理三条前提：闭区间连续、开区间可导、两端点函数值相等。"),
    ("数学", ["级数收敛"],
     "若正项级数收敛，则其通项一定（　）",
     ["单调递减", "趋于零", "有界但不趋于零", "交错变号"],
     "B", "级数收敛的必要条件是通项趋于零；单调性不是必要条件，这是最常错的一处。"),
    ("英语", ["非谓语动词"],
     "___ from the top of the tower, the south side of the hill is very beautiful.",
     ["Seen", "Seeing", "To see", "See"],
     "A", "逻辑主语是 the south side，与 see 是被动关系，用过去分词；选 B 是当成主动了。"),
    ("英语", ["虚拟语气"],
     "If the weather had been fine, we ___ the picnic as planned.",
     ["would have", "would have had", "had had", "will have"],
     "B", "与过去事实相反：条件句 had done，主句 would have done。"),
    ("英语", ["定语从句"],
     "The reason ___ he gave for being late was unconvincing.",
     ["why", "which", "where", "when"],
     "B", "he gave ___ 中给的是 reason，作宾语用 which/that；why 只能作状语，是本题陷阱。"),
    ("政治", ["商品二因素"],
     "商品的使用价值与价值的关系是（　）",
     ["二者相互独立", "使用价值是价值的物质承担者", "价值决定使用价值", "二者可以互相转化"],
     "B", "价值是抽象的，必须寄存在有用的物上，所以使用价值是价值的物质承担者。"),
    ("政治", ["剩余价值"],
     "剩余价值的真正来源是（　）",
     ["资本家的经营管理", "雇佣工人的剩余劳动", "流通领域的贱买贵卖", "生产资料的折旧"],
     "B", "可变资本购买的活劳动才创造新价值，其中超过劳动力价值的部分就是剩余价值。"),
    ("专业课", ["进程与线程"],
     "同一进程内的多个线程共享（　）",
     ["栈空间", "寄存器组", "地址空间与打开文件表", "调度上下文"],
     "C", "线程共享进程的地址空间与文件描述表，独享栈、寄存器和调度上下文。"),
    ("专业课", ["死锁四条件"],
     "破坏下列哪个条件可以预防死锁（　）",
     ["互斥", "请求与保持", "循环等待", "以上任一均可"],
     "D", "四个条件同时成立才会死锁，破坏任一个即可预防——只是互斥条件通常破坏不了。"),
    ("专业课", ["数据库范式"],
     "满足第三范式的关系模式一定（　）",
     ["消除非主属性对码的传递依赖", "消除多值依赖", "消除主属性对码的部分依赖", "已是最高范式"],
     "A", "3NF 是在 2NF 基础上消除非主属性对码的传递依赖，再往上还有 BCNF、4NF。"),
]

# (科目, 知识点, 题干, 答案二维数组, 解析)
BLANK = [
    ("数学", ["摩擦力做功"],
     "摩擦力做功的公式 W=______，式中 s 指的是______。",
     [["-fs", "-f s"], ["相对滑动的路程", "路程"]],
     "这里的 s 是相对滑动的路程，不是位移，这是最容易错的地方。"),
    ("数学", ["函数连续性"],
     "函数 f 在 x0 连续的三个条件：有定义、极限存在、______。",
     [["极限值等于函数值", "lim f(x)=f(x0)"]],
     "三者缺一不可，只有前两条只能说明极限存在。"),
    ("数学", ["函数连续性"],
     "|x| 的分段写法是：x≥0 时为 x，x<0 时为______；|x| 的图像呈______形。",
     [["-x"], ["V", "V 字"]],
     "题干里就带竖线 |x|，专门用来验证竖线不会把存储与表格劈坏。"),
    ("数学", ["级数收敛"],
     "几何级数 ∑ar^n 收敛的充要条件是 |r|______，其和为______。",
     [["<1", "小于 1"], ["a/(1-r)"]],
     "答案 a/(1-r) 含斜杠，用来验证斜杠不会被当成分隔符拆成两半。"),
    ("英语", ["词根词缀"],
     "-tion 这一后缀通常把动词变成______词，例如 creation 表示______。",
     [["名"], ["创造", "创作"]],
     "构词法是阅读理解的兜底能力。"),
    ("英语", ["定语从句"],
     "限制性定语从句可以用 that，非限制性定语从句______用 that，且前面必须有______。",
     [["不能", "不可"], ["逗号"]],
     "两个空，第二空漏了逗号就算错。"),
    ("政治", ["商品二因素"],
     "商品的两个因素是使用价值和______；生产商品的劳动二重性是具体劳动和______。",
     [["价值"], ["抽象劳动"]],
     "劳动二重性决定商品二因素，这一问是背漏点。"),
    ("专业课", ["进程与线程"],
     "操作系统资源分配的基本单位是______，CPU 调度的基本单位通常是______。",
     [["进程"], ["线程"]],
     "概念题，答错说明还没分清两者。"),
    ("专业课", ["数据库范式"],
     "2NF 要求消除非主属性对码的______依赖，3NF 再消除______依赖。",
     [["部分"], ["传递"]],
     "两个词顺序不能颠倒，一颠倒整条链就错。"),
    ("专业课", ["死锁四条件"],
     "死锁的四个必要条件是互斥、请求与保持、不可剥夺和______。",
     [["循环等待"]],
     "四个条件缺一则不构成死锁。"),
]

# (科目, 知识点, 题干, 参考答案, 解析)
ESSAY = [
    ("数学", ["中值定理"],
     "叙述拉格朗日中值定理的条件与结论，并说明罗尔定理与它的关系。",
     "闭区间连续、开区间可导，则存在 ξ 使 f'(ξ)=(f(b)-f(a))/(b-a)。罗尔定理是 f(a)=f(b) 的特例。",
     "条件少一条结论就不成立，这是简答题最常扣的分。"),
    ("数学", ["牛顿第二定律"],
     "为什么在非惯性系里不能直接用 F=ma？举一个引入惯性力的例子。",
     "非惯性系中牛顿定律不成立，需要加上一个与参考系加速度反向的惯性力才能保持原有形式，"
     "例如加速前进的车厢里物体会向后倾。",
     "把惯性力写成「真实的力」就是概念错。"),
    ("英语", ["虚拟语气"],
     "用一句话说明 wish 后接宾语从句时，对现在、过去、将来分别用什么形式。",
     "对现在用过去式，对过去用过去完成式，对将来用 would do。",
     "三种时间一套形式，混用就整句错。"),
    ("政治", ["剩余价值"],
     "简述绝对剩余价值与相对剩余价值的区别。",
     "前者靠延长工作日，后者靠缩短必要劳动时间、提高全社会劳动生产率。",
     "两者都建立在雇佣劳动基础上，区别在生产方法。"),
    ("专业课", ["进程与线程"],
     "为什么引入线程？它比进程「轻」在哪里？",
     "为了减少并发开销。线程切换不必更换地址空间与页表，且共享进程资源，"
     "创建、撤销和通信都比进程便宜。",
     "答「共享地址空间」才算说到点上。"),
    ("专业课", ["操作系统中断"],
     "说明中断与轮询的区别，以及为什么实时系统更依赖中断。",
     "轮询由软件反复主动查询状态，浪费 CPU；中断由硬件事件驱动，发生时才占用 CPU，响应及时。"
     "实时性要求高的场合必须用中断。",
     "把「轮询更快」当成优点是常见误解。"),
    ("数学", ["函数连续性"],
     "举例说明「可导必连续、连续未必可导」。",
     "|x| 在 x=0 处连续但不可导；而可导时增量比值的极限存在，必然连续。",
     "|x| 是最省事的反例，考场上别现想。"),
    ("专业课", ["数据库范式"],
     "范式越高一定越好吗？说明反规范化的适用场景。",
     "不一定。范式越高、关系越碎，查询时的连接开销越大；读多写少的报表场景常故意保留冗余字段，"
     "换取查询速度。",
     "这一问考的是权衡，不是背定义。"),
]

# (科目, 题型, 题干, 选项, 答案, 解析)
OFFICIAL = [
    ("数学", "choice", "下列极限等于 1 的是（　）",
     ["lim(x→0) sin x / x", "lim(x→∞) sin x / x", "lim(x→0) x / sin x 的平方", "lim(x→∞) (1+1/x)^{2x}"],
     "A", "第一个是重要极限；最后一个等于 e 的平方，别把两个重要极限搞混。"),
    ("英语", "essay", "说明 It was not until midnight that he finished the report. 中 not until 的强调结构怎么构成。",
     [], {"text": "强调句型 It is/was + 被强调部分 + that；not until 整体被强调时，主句不再倒装。"},
     "把 not until 拆开强调是错的。"),
    ("政治", "blank", "马克思主义的三个来源是德国古典哲学、英国古典政治经济学和______。",
     [], [["空想社会主义"]], "三个来源对应三个组成部分，最容易混。"),
    ("专业课", "choice", "下列不属于进程间通信机制的是（　）",
     ["管道", "共享内存", "信号量", "寄存器"], "D",
     "寄存器属于 CPU 内部存储，不是 IPC 机制。"),
    ("数学", "blank", "设 f 在 [a,b] 上连续且 f(a)f(b)<0，则至少存在一点 ξ 使______。",
     [], [["f(ξ)=0"]], "零点存在定理，注意前提里必须有连续。"),
]


def load(force: bool = False) -> bool:
    """灌演示数据。已有账号就跳过，返回是否真的写了。"""
    conn = db.connect()
    try:
        if UserRepo(conn).count() > 0 and not force:
            return False
        if force:
            conn.execute("DELETE FROM review_log")
            conn.execute("DELETE FROM mistake")
            conn.execute("DELETE FROM study_attempt")
            conn.execute("DELETE FROM question_knowledge_point")
            conn.execute("DELETE FROM question_bank")
            conn.execute("DELETE FROM knowledge_note")
            conn.execute("DELETE FROM knowledge_point")
            conn.execute("DELETE FROM tag_link")
            conn.execute("DELETE FROM tag")
            conn.execute("DELETE FROM favorite")
            conn.execute("DELETE FROM appeal")
            conn.execute("DELETE FROM user_agreement")
            conn.execute("DELETE FROM agreement")
            conn.execute("DELETE FROM user_setting")
            conn.execute("DELETE FROM user_profile")
            conn.execute("DELETE FROM user")
            conn.execute("DELETE FROM subject")
            conn.execute("DELETE FROM import_session_row")
            conn.execute("DELETE FROM import_session")
            conn.commit()
        _seed_all(conn)
        _write_sample_files()
        conn.commit()
        return True
    finally:
        conn.close()


def _stamp(day: date, hour: int = 20, minute: int = 0) -> str:
    return datetime(day.year, day.month, day.day, hour, minute).isoformat(timespec="seconds")


def _seed_all(conn) -> None:
    today = date.today()
    users = _make_users(conn, today)
    subjects = _make_subjects(conn, today)
    points = _make_knowledge(conn, subjects, users, today)
    questions = _make_questions(conn, subjects, points, users, today)
    _make_queue_and_logs(conn, questions, users, today)
    _make_private_stuff(conn, users, points, questions, today)
    _make_agreement(conn, users, today)
    _make_appeals(conn, users, questions, points, today)


def _make_users(conn, today) -> dict[str, int]:
    """演示账号。密码哈希走 `auth_service.hash_password`——全站只有一处会算哈希，
    seed 不该有第二处，否则步 4 换了 cost 这里就悄悄不一致了。"""
    repo = UserRepo(conn)
    ids: dict[str, int] = {}
    created = _stamp(today - timedelta(days=60))
    for name, pwd in [ADMIN, DEMO, *EXTRA]:
        role = "admin" if name == "admin" else "member"
        uid = repo.register(name, auth_service.hash_password(pwd), role)
        conn.execute("UPDATE user SET created_at = ? WHERE id = ?", (created, uid))
        display = {"admin": "管理员", "demo": "演示账号"}.get(name, name)
        conn.execute("INSERT INTO user_profile (user_id, display_name, school) VALUES (?,?,?)",
                     (uid, display, "某某大学"))
        for key, value in {"review_time": "00:00", "daily_review_cap": "30",
                           "mode": "study", "time_zone": ""}.items():
            conn.execute("INSERT INTO user_setting (user_id, key, value) VALUES (?,?,?)",
                         (uid, key, value))
        ids[name] = uid
    return ids


def _make_subjects(conn, today) -> dict[str, int]:
    ids: dict[str, int] = {}
    created = _stamp(today - timedelta(days=60))
    for name in SUBJECTS:
        ids[name] = conn.execute(
            "INSERT INTO subject (name, status, created_at, updated_at) VALUES (?, 'active', ?, ?)",
            (name, created, created)).lastrowid
    # 隐藏库「已下架」格
    conn.execute("INSERT INTO subject (name, status, created_at, updated_at) "
                 "VALUES ('艺术鉴赏', 'hidden', ?, ?)", (created, _stamp(today)))
    return ids


def _make_knowledge(conn, subjects, users, today) -> dict[tuple[str, str], int]:
    """每科 3–5 个已通过的知识点，另留两条待审、一条下架、一条已删除。"""
    ids: dict[tuple[str, str], int] = {}
    reviewer = users["admin"]
    for subject, names in KNOWLEDGE.items():
        for index, name in enumerate(names):
            reviewed = index != 4          # 每科最后一条留作待审
            ids[(subject, name)] = conn.execute(
                "INSERT INTO knowledge_point (subject_id, name, name_normalized, status, "
                "reviewed_by, reviewed_at, created_by_user_id, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (subjects[subject], name, name, "approved",
                 reviewer if reviewed else None,
                 _stamp(today - timedelta(days=10)) if reviewed else None,
                 users["demo"], _stamp(today - timedelta(days=30)),
                 _stamp(today - timedelta(days=10)))).lastrowid
    for subject, name in [("数学", "斯托尔兹定理"), ("英语", "独立主格")]:
        conn.execute(
            "INSERT INTO knowledge_point (subject_id, name, name_normalized, status, "
            "created_by_user_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (subjects[subject], name, name, "approved", users["stu1"],
             _stamp(today - timedelta(days=1)), _stamp(today - timedelta(days=1))))
    conn.execute(
        "INSERT INTO knowledge_point (subject_id, name, name_normalized, status, reviewed_by, "
        "reviewed_at, review_note, created_by_user_id, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (subjects["数学"], "永动机原理", "永动机原理", "hidden", users["admin"],
         _stamp(today - timedelta(days=2)), "内容本身不成立，属错误概念",
         users["stu2"], _stamp(today - timedelta(days=6)), _stamp(today - timedelta(days=2))))
    conn.execute(
        "INSERT INTO knowledge_point (subject_id, name, name_normalized, status, "
        "created_by_user_id, created_at, updated_at, deleted_at) VALUES (?,?,?,?,?,?,?,?)",
        (subjects["政治"], "过时表述举例", "过时表述举例", "rejected", users["stu1"],
         _stamp(today - timedelta(days=20)), _stamp(today - timedelta(days=20)),
         _stamp(today - timedelta(days=3))))
    conn.commit()
    return ids


def _insert_question(conn, owner_id, subject_id, qtype, stem, options, answer,
                     explanation, source, today, *, offset_days=25, shared=False):
    return conn.execute(
        "INSERT INTO question_bank (user_id, subject_id, type, stem, options_json, answer_json, "
        "explanation, source, visibility, shared_at, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (owner_id, subject_id, qtype, stem,
         # ★ 走导入链路同一个列内规范化函数：库里的 `options_json` / `answer_json`
         #   从此只有一种写法（`{"letters":"AC"}` 而不是 `{"letters": "AC"}`），
         #   步 13 的"导出再导回逐字节一致"才是真的成立。
         normalize.to_canonical_json("options", json.dumps(options, ensure_ascii=False), qtype),
         normalize.to_canonical_json("answer", json.dumps(answer, ensure_ascii=False), qtype),
         explanation, source, "shared" if shared else "private",
         _stamp(today - timedelta(days=offset_days - 1)) if shared else None,
         _stamp(today - timedelta(days=offset_days)),
         _stamp(today - timedelta(days=offset_days)))).lastrowid


def _link(conn, question_id, names, points, user_id, today) -> None:
    for subject, name in _resolve(names, points):
        conn.execute(
            "INSERT OR IGNORE INTO question_knowledge_point "
            "(question_id, knowledge_point_id, user_id, created_at) VALUES (?,?,?,?)",
            (question_id, points[(subject, name)], user_id, _stamp(today - timedelta(days=20))))


def _resolve(names, points) -> list[tuple[str, str]]:
    """知识点名到科目是唯一的，按 (科目, 名字) 找回归属。"""
    lookup = {name: subject for subject, name in points}
    return [(lookup[n], n) for n in names if n in lookup]


def _make_questions(conn, subjects, points, users, today) -> dict:
    """demo 名下 30 道（选择 12 / 填空 10 / 简答 8）+ 官方题 5 道（user_id 为 NULL）。"""
    demo = users["demo"]
    made: dict[str, list[tuple[int, int]]] = {"choice": [], "blank": [], "essay": [], "official": []}

    for subject, kp_names, stem, options, letters, explanation in CHOICE:
        qid = _insert_question(conn, demo, subjects[subject], "choice", stem, options,
                               {"letters": letters}, explanation, "练习题", today)
        _link(conn, qid, kp_names, points, demo, today)
        made["choice"].append((qid, subjects[subject]))

    for subject, kp_names, stem, answer, explanation in BLANK:
        qid = _insert_question(conn, demo, subjects[subject], "blank", stem, [],
                               answer, explanation, "讲义", today)
        _link(conn, qid, kp_names, points, demo, today)
        made["blank"].append((qid, subjects[subject]))

    for subject, kp_names, stem, answer_text, explanation in ESSAY:
        qid = _insert_question(conn, demo, subjects[subject], "essay", stem, [],
                               {"text": answer_text}, explanation, "错题本", today)
        _link(conn, qid, kp_names, points, demo, today)
        made["essay"].append((qid, subjects[subject]))

    for subject, qtype, stem, options, answer, explanation in OFFICIAL:
        payload = ({"letters": answer} if qtype == "choice"
                   else answer if qtype == "blank" else {"text": answer})
        qid = _insert_question(conn, None, subjects[subject], qtype, stem, options,
                               payload, explanation, "官方整理", today)
        made["official"].append((qid, subjects[subject]))

    shared = []
    for qid, _ in made["choice"][:6]:
        conn.execute("UPDATE question_bank SET visibility='shared', shared_at=? WHERE id=?",
                     (_stamp(today - timedelta(days=12)), qid))
        shared.append(qid)
    conn.commit()
    every = [item for group in ("choice", "blank", "essay") for item in made[group]]
    return {"by_type": made, "shared": shared, "all": every, "official": made["official"]}


def _make_queue_and_logs(conn, questions, users, today) -> None:
    """错题队列 + 45 天复习流水账。★ 间隔一律由 ladder.next_state() 真算。"""
    demo = users["demo"]
    pool = questions["all"]

    specials = {pool[0]: 0, pool[1]: -3, pool[2]: 30}   # 今天到期 / 逾期 3 天 / 已爬到第 5 级
    for (qid, subject_id), offset in specials.items():
        step = 5 if offset == 30 else 0
        conn.execute(
            "INSERT INTO mistake (user_id, question_id, entry_reason, step_index, interval_days, "
            "due_date, review_count, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (demo, qid, "marked_wrong", step, schedule.LADDER_INTERVALS[step],
             (today + timedelta(days=offset)).isoformat(),
             1 if step else 0, _stamp(today - timedelta(days=20)), _stamp(today - timedelta(days=2))))
        conn.execute(
            "INSERT INTO study_attempt (user_id, question_id, subject_id, result, grade_source, "
            "answer_submitted, recorded_on, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (demo, qid, subject_id, "wrong", "auto", "",
             (today - timedelta(days=20)).isoformat(), _stamp(today - timedelta(days=20))))

    for qid, subject_id in pool[3:20]:
        _replay_history(conn, demo, qid, subject_id, today)

    # 别人撤走：stu1 把 demo 的共享题加进了复习，demo 后来撤回共享
    if questions["shared"]:
        gone = questions["shared"][-1]
        conn.execute("UPDATE question_bank SET visibility='private', shared_at=NULL WHERE id=?",
                     (gone,))
        _manual_mistake(conn, users["stu1"], gone, 2, today - timedelta(days=1), 2)
        for qid in questions["shared"][:2]:
            _manual_mistake(conn, users["stu2"], qid, 1, today, 1)

    # 官方题被管理员收起：只写 delisted_by，绝不写别人的 deleted_at
    if questions["official"]:
        target, _ = questions["official"][0]
        conn.execute("UPDATE question_bank SET delisted_by=?, delist_note=? WHERE id=?",
                     (users["admin"], "不合规：配图含他人姓名与手写笔迹", target))
    conn.commit()


def _manual_mistake(conn, user_id, question_id, step, due, reviews) -> None:
    conn.execute(
        "INSERT INTO mistake (user_id, question_id, entry_reason, step_index, interval_days, "
        "due_date, review_count, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (user_id, question_id, "manual_add", step, schedule.LADDER_INTERVALS[step],
         due.isoformat(), reviews, _stamp(due - timedelta(days=8)), _stamp(due - timedelta(days=1))))


def _replay_history(conn, user_id, question_id, subject_id, today) -> None:
    """从建队那天起，按 ladder 一题一题往前推，每一步落一条 review_log。

    ★ 走的是 `registry.get()` 拿到的策略接口，与步 9 的 service 同一条路：
      seed 不是在猜算法的结果，是在重放真实算法（方案三-21 第④条）。
    """
    created = today - timedelta(days=RNG.randint(30, 45))
    due, step, interval, reviews, lapses, logs = created, 0, 0, 0, 0, []
    strategy = registry.get()

    while due <= today and reviews < 12:
        reviewed_at = _stamp(due, hour=RNG.randint(8, 22), minute=RNG.randint(0, 59))
        rating = _pick_rating(reviews)
        move = strategy.next_state(ReviewState(step, interval, due), rating, due)
        step, interval = move.after.step_index, move.after.interval_days
        reviews += 1
        lapses += 1 if move.lapsed else 0
        logs.append((user_id, due.isoformat(), reviewed_at, rating,
                     "user_override" if RNG.random() < 0.5 else "duration_default",
                     RNG.randint(15, 260), move.algorithm_version,
                     move.before.interval_days, move.after.interval_days,
                     move.before.due_date.isoformat(), move.after.due_date.isoformat(),
                     move.before.step_index, move.after.step_index))
        due = move.after.due_date

    if not logs:                                  # 一天都没排上，就留一条"今天到期"的新错题
        due = today
    mistake_id = conn.execute(
        "INSERT INTO mistake (user_id, question_id, entry_reason, step_index, interval_days, "
        "due_date, last_reviewed_at, review_count, lapse_count, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (user_id, question_id, "marked_wrong", step, interval,
         due.isoformat(), logs[-1][2] if logs else None, reviews, lapses,
         _stamp(created), _stamp(today))).lastrowid

    conn.executemany(
        "INSERT INTO review_log (user_id, mistake_id, reviewed_on, reviewed_at, rating, "
        "rating_source, duration_seconds, algorithm_version, interval_before, interval_after, "
        "due_date_before, due_date_after, step_before, step_after) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(user_id, mistake_id) + row[1:] for row in logs])

    conn.execute(
        "INSERT INTO study_attempt (user_id, question_id, subject_id, result, grade_source, "
        "answer_submitted, recorded_on, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (user_id, question_id, subject_id, "wrong", "manual", "",
         created.isoformat(), _stamp(created)))


def _pick_rating(reviews_so_far: int) -> int:
    """前几次偏向"没记住"，之后逐步爬上台阶——四档都要出现，统计图才有形状。"""
    if reviews_so_far == 0:
        return RNG.choice([4, 3, 4, 2])
    if reviews_so_far < 3:
        return RNG.choice([2, 3, 1, 4])
    return RNG.choice([1, 2, 2, 3])


def _make_private_stuff(conn, users, points, questions, today) -> None:
    demo = users["demo"]
    some_points = list(points.values())
    for text, ago in [("摩擦力的方向要按相对运动趋势判，不是相对运动", 40),
                      ("连续不等于可导，|x| 是最好用的反例", 18),
                      ("上一条写错了：判断依据是相对运动趋势，但摩擦力方向沿接触面，别写成「沿位移」", 6),
                      ("中值定理这三条前提我每次都漏第三条，做题先写端点相等", 1)]:
        conn.execute(
            "INSERT INTO knowledge_note (user_id, knowledge_point_id, content, created_at, updated_at) "
            "VALUES (?,?,?,?,?)",
            (demo, some_points[0], text, _stamp(today - timedelta(days=ago)),
             _stamp(today - timedelta(days=ago))))

    first_q = questions["all"][0][0]
    for name, color in zip(tags.STARTER_TAGS, ("#dc2626", "#2563eb", "#15803d")):
        tag_id = conn.execute("INSERT INTO tag (user_id, name, color, created_at) VALUES (?,?,?,?)",
                              (demo, name, color, _stamp(today - timedelta(days=20)))).lastrowid
        conn.execute("INSERT INTO tag_link (user_id, tag_id, target_type, target_id, created_at) "
                     "VALUES (?,?,?,?,?)",
                     (demo, tag_id, tags.TARGET_TYPES[0], first_q,
                      _stamp(today - timedelta(days=20))))
    # 收藏三类各一条：通过的知识点、**已下架的知识点**（用来演示"只显示灰标、不报错"）、
    # 以及一条私人笔记（知识点永不真删，所以收藏不会悬空——方案三-9）。
    hidden_point = conn.execute(
        "SELECT id FROM knowledge_point WHERE status='hidden' LIMIT 1").fetchone()
    first_note = conn.execute(
        "SELECT id FROM knowledge_note WHERE user_id=? ORDER BY id LIMIT 1", (demo,)).fetchone()
    favorites = [("knowledge_point", some_points[1], 4)]
    if hidden_point:
        favorites.append(("knowledge_point", hidden_point["id"], 12))
    if first_note:
        favorites.append(("note", first_note["id"], 2))
    for kind, target, ago in favorites:
        conn.execute("INSERT INTO favorite (user_id, target_type, target_id, created_at)"
                     " VALUES (?,?,?,?)",
                     (demo, kind, target, _stamp(today - timedelta(days=ago))))

    # 回收站：自己删的两道题（deleted_by 本人，一条 4 天前、一条 29 天前后到期）
    conn.execute("UPDATE question_bank SET deleted_at=?, deleted_by=? WHERE id=?",
                 (_stamp(today - timedelta(days=4)), demo, questions["all"][-1][0]))
    conn.execute("UPDATE question_bank SET deleted_at=?, deleted_by=? WHERE id=?",
                 (_stamp(today - timedelta(days=29)), demo, questions["all"][-2][0]))
    # 过期封存的一条 mistake：行留着，只打 purged_at
    conn.execute(
        "INSERT INTO mistake (user_id, question_id, entry_reason, due_date, deleted_at, "
        "deleted_by, purged_at, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (demo, questions["all"][3][0], "marked_wrong",
         (today - timedelta(days=40)).isoformat(), _stamp(today - timedelta(days=31)),
         demo, _stamp(today - timedelta(days=1)), _stamp(today - timedelta(days=45)),
         _stamp(today - timedelta(days=31))))
    conn.commit()


_SHARE_TEXT = (
    "一、公开范围　题目一经共享，其题干、选项、答案、解析及配图将对系统内全体注册用户可见，"
    "且其他用户可将其加入个人复习队列。\n"
    "二、管理与处置　为维护内容合规，管理方有权对已共享内容采取停止展示、下架等措施；"
    "采取措施时将载明具体理由，你可通过「申诉与反馈」提出异议。\n"
    "三、你的撤回权　你可以随时撤回共享，无需理由。撤回后其他用户的副本不受影响"
    "（已被另存为他人题目的内容归属该用户）。\n"
    "四、数据归属不变　内容始终归你所有，管理方不会代为修改、补充或再次发布。")


_SITE_TEXT = """一、这个站存什么　题目、错题、复习流水、导入批次与你自己写的笔记。全部存在服务器本地的一个 SQLite 文件里，不上传到任何第三方。
二、备份与恢复　数据库与图片都在 `var/` 目录，换机器或重装需要自己拷贝那个目录；仓库里不含它们，删掉 `var/` 等于从零开始。
三、内容归你　你录的题、你写的解析与笔记归你所有，管理方不会代为修改、补充或再次发布；管理员的处置（下架、驳回）一律附理由，且你可以申诉。
四、共享要你自己点　题目默认只有你能看见，只有你主动点「共享」并同意《共享须知》之后，别人才可能刷到它，答案解析与配图会一并公开。
五、公开部署请先改密码　演示账号（demo / stu1 / stu2 / admin）的密码写在 README 里，任何对外部署都必须先改掉，否则任何人都能进别人的错题本。"""


def _make_agreement(conn, users, today) -> None:
    conn.execute(
        "INSERT INTO agreement (version, seq, title, content, effective_from, created_at) "
        "VALUES (?,?,?,?,?,?)",
        ("SITE-1", 1, "站点协议", _SITE_TEXT,
         (today - timedelta(days=30)).isoformat(), _stamp(today - timedelta(days=30))))
    conn.execute(
        "INSERT INTO agreement (version, seq, title, content, effective_from, created_at) "
        "VALUES (?,?,?,?,?,?)",
        ("SHARE-1", 2, "共享须知", _SHARE_TEXT,
         (today - timedelta(days=30)).isoformat(), _stamp(today - timedelta(days=30))))
    # demo 选过"以后都同意"，stu1 没同意过 → 两种状态都能当场演示
    conn.execute("INSERT INTO user_agreement (user_id, version, agreed_at) VALUES (?,?,?)",
                 (users["demo"], "SHARE-1", _stamp(today - timedelta(days=12))))
    conn.commit()


def _make_appeals(conn, users, questions, points, today) -> None:
    target = questions["official"][0][0] if questions["official"] else questions["all"][0][0]
    conn.execute(
        "INSERT INTO appeal (user_id, category, target_type, target_id, reason, status, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (users["demo"], "action", "question", target,
         "配图我已经把姓名遮掉了，能不能重新公开？", "open", _stamp(today - timedelta(days=1))))
    conn.execute(
        "INSERT INTO appeal (user_id, category, target_type, target_id, reason, status, "
        "admin_reply, handled_by, handled_at, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (users["stu1"], "rejection", "knowledge_point", points[("数学", "中值定理")],
         "我提交的那个知识点被下架了，但教材里确有这一节",
         "handled", "已恢复，请再确认一次名称是否与教材一致",
         users["admin"], _stamp(today - timedelta(days=1)), _stamp(today - timedelta(days=2))))
    conn.commit()


def _write_sample_files() -> None:
    """写出当场就能用的导入样例（没配 AI Key 也能把导入这一条链演示完）。

    ★ 样例里的题型只用现在真认得了的那些（`question_types/registry`）：
      选择题、填空题的处理器在后面的步骤补，样例要是先写进去，导入页就会把它们
      当成"还不支持的题型"拦下——用户以为样例坏了，其实是进度没到。
    """
    rows = [
        {"subject": "数学", "knowledge_points": ["牛顿第二定律", "受力分析"], "type": "essay",
         "stem": "写出牛顿第二定律的表达式，并说明它为什么只在惯性系里成立。",
         "options": [],
         "answer": {"text": "F=ma；非惯性系里要额外引入惯性力，直接把合外力等于 ma 就不成立了。"},
         "explanation": "先判参考系，再列受力，是这类题的第一步。"},
        {"subject": "数学", "knowledge_points": ["函数连续性"], "type": "essay",
         "stem": "|x| 在 x=0 处连续吗？可导吗？说明理由。",
         "options": [], "answer": {"text": "连续但不可导：左右导数分别为 1 和 -1，不相等。"},
         "explanation": "题干里自带竖线，专门用来验证它不会被当成分隔符劈坏。"},
        {"subject": "数学", "knowledge_points": ["级数收敛"], "type": "essay",
         "stem": "∑(1/2)^n（n 从 1 起）收敛吗？若收敛求出它的和。",
         "options": [], "answer": {"text": "公比 1/2 的绝对值小于 1，故收敛，和为 1。"},
         "explanation": "答案含斜杠 1/2，走 CSV 也不许被劈开。"},
        {"subject": "英语", "knowledge_points": ["非谓语动词"], "type": "essay",
         "stem": "说明 seen 与 seeing 作状语的差别。", "options": [],
         "answer": {"text": "seen 表被动或完成，seeing 表主动或进行，判断依据是与主语的逻辑关系。"},
         "explanation": "非谓语的核心是先找逻辑主语。"},
    ]
    settings.IMPORT_TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    settings.SAMPLE_JSONL_PATH.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8", newline="\n")      # ★ 不写死换行符会被 Windows 换成 \r\n，导入页就白报"已修正 N 处"

    _write_csv(settings.SAMPLE_CSV_PATH, rows)
    dirty = [dict(rows[0]), dict(rows[1]), dict(rows[2]),
             {**rows[3], "stem": "", "answer": {"text": ""}},          # 必填为空
             {**rows[0], "type": "choice"},                            # 题型还没实现
             {"subject": "物理", "knowledge_points": [], "type": "essay",
              "stem": "科目不在可用列表里", "options": [], "answer": {"text": "答"}}]
    _write_csv(settings.SAMPLE_DIRTY_CSV_PATH, dirty)


def _write_csv(path, rows) -> None:
    """列顺序照 `config/csv_spec` 写；知识点一格里用分号隔开（逗号是 CSV 自己的分隔符）。"""
    columns = csv_spec.SPECS["question"]["columns"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([_sample_cell(row, column) for column in columns])


def _sample_cell(row, column):
    value = row.get(column, "")
    if column == "knowledge_points":
        return ";".join(value)
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)      # 单元格里的 JSON 由 csv 模块负责转义
    return value
