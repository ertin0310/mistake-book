-- 错题本 + 间隔重复复习系统 · 全部 19 张表
-- 由 src/data/db.py 在库文件不存在时自动执行，不需要手工命令。
-- 时间统一存 ISO-8601 文本；`due_date`/`reviewed_on` 这类"复习日"只存 YYYY-MM-DD，不带时刻。

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- 账号与资料

CREATE TABLE user (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,      -- 存归一化后的值（去空格、转小写），唯一性靠它
    password_hash TEXT    NOT NULL,             -- bcrypt，绝不明文
    role          TEXT    NOT NULL DEFAULT 'member' CHECK (role IN ('member', 'admin')),
    created_at    TEXT    NOT NULL
);

-- 有校验规则的正式资料。加字段走 migrations/00X.sql，不动 user 表。
CREATE TABLE user_profile (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL UNIQUE REFERENCES user(id),
    display_name TEXT    NOT NULL DEFAULT '',
    avatar_path  TEXT,
    school       TEXT    NOT NULL DEFAULT ''
);

-- 偏好开关：一行一个 key，加设置不改表。
-- key 清单：review_time / review_time_pending / review_time_pending_from / daily_review_cap / mode / time_zone
CREATE TABLE user_setting (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES user(id),
    key     TEXT    NOT NULL,
    value   TEXT    NOT NULL,
    UNIQUE (user_id, key)
);

-- ---------------------------------------------------------------- 条款与同意

-- version 是给人看的串（SHARE-1、SITE-1），判断新旧一律用 seq：
-- 字符串比较会得出 'SHARE-2' > 'SHARE-10'，同意过第 10 版的用户会被误判成旧版而不再重弹。
CREATE TABLE agreement (
    version        TEXT    PRIMARY KEY,
    seq            INTEGER NOT NULL UNIQUE,
    title          TEXT    NOT NULL,
    content        TEXT    NOT NULL,
    effective_from TEXT    NOT NULL,
    created_at     TEXT    NOT NULL
);

CREATE TABLE user_agreement (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL REFERENCES user(id),
    version   TEXT    NOT NULL REFERENCES agreement(version),
    agreed_at TEXT    NOT NULL
);

-- ---------------------------------------------------------------- 共享字典

-- 全站共享、所有人只读，写入仅管理员。被题目引用，故永不物理删。
CREATE TABLE subject (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'hidden')),
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL,
    deleted_at  TEXT                              -- 只有管理员/系统能置位；回收站里没有这一项
);

-- 提交即入池（approved），管理员事后审。policy scope：可见性由 domain/visibility.py 判。
CREATE TABLE knowledge_point (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id          INTEGER NOT NULL REFERENCES subject(id),
    name                TEXT    NOT NULL,
    name_normalized     TEXT    NOT NULL,
    status              TEXT    NOT NULL DEFAULT 'approved'
                        CHECK (status IN ('approved', 'hidden', 'rejected')),
    reviewed_by         INTEGER REFERENCES user(id),   -- NULL = 管理员还没看过
    reviewed_at         TEXT,
    review_note         TEXT,                          -- 驳回原因，作者可见
    created_by_user_id  INTEGER REFERENCES user(id),   -- NULL = 管理员直建
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,
    deleted_at          TEXT
);

-- 私人笔记：一条知识点可追加多条，看得见自己理解的演进。
CREATE TABLE knowledge_note (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id            INTEGER NOT NULL REFERENCES user(id),
    knowledge_point_id INTEGER NOT NULL REFERENCES knowledge_point(id),
    content            TEXT    NOT NULL,
    created_at         TEXT    NOT NULL,
    updated_at         TEXT    NOT NULL,
    deleted_at         TEXT
);

-- ---------------------------------------------------------------- 题目

-- named scope：读取只走 mine / shared_pool 两个具名读法，不套 user 过滤。
-- user_id 为 NULL 表示归属软件本身（官方题）。被复习记录引用，永不物理删。
CREATE TABLE question_bank (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER REFERENCES user(id),
    subject_id    INTEGER NOT NULL REFERENCES subject(id),
    type          TEXT    NOT NULL CHECK (type IN ('choice', 'blank', 'essay')),
    stem          TEXT    NOT NULL,
    options_json  TEXT    NOT NULL DEFAULT '[]',
    answer_json   TEXT    NOT NULL DEFAULT 'null',
    explanation   TEXT    NOT NULL DEFAULT '',
    source        TEXT    NOT NULL DEFAULT '',
    visibility    TEXT    NOT NULL DEFAULT 'private' CHECK (visibility IN ('private', 'shared')),
    shared_at     TEXT,
    image_path    TEXT,
    copied_from_question_id INTEGER REFERENCES question_bank(id),  -- 「另存为我自己的」幂等靠它
    deleted_by    INTEGER REFERENCES user(id),   -- 这次删除是谁按的按钮：回收站只放用户自己扔的
    delisted_by   INTEGER REFERENCES user(id),   -- 管理员收起标记，不写 deleted_at，作者翻不掉
    delist_note   TEXT,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL,
    deleted_at    TEXT
);

-- 知识点关联"谁标的归谁看"，所以主键必须含 user_id：
-- 否则 A 标过 (题, 知识点) 之后 B 再标同一个就撞主键报错。
-- 筛共享题时走 shared_links 只读法，随题目元数据公开。
CREATE TABLE question_knowledge_point (
    question_id        INTEGER NOT NULL REFERENCES question_bank(id),
    knowledge_point_id INTEGER NOT NULL REFERENCES knowledge_point(id),
    user_id            INTEGER NOT NULL REFERENCES user(id),
    created_at         TEXT    NOT NULL,
    PRIMARY KEY (question_id, knowledge_point_id, user_id)
);

-- ---------------------------------------------------------------- 复习与做题

-- 复习队列里的一行 = 某人对某道题的排期。一道题对同一人最多一条活跃记录，
-- partial 条件只看未删除的，否则「撤销删除」会撞约束。永不物理删（review_log 指着它）。
CREATE TABLE mistake (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL REFERENCES user(id),
    question_id      INTEGER NOT NULL REFERENCES question_bank(id),
    entry_reason     TEXT    NOT NULL CHECK (entry_reason IN ('marked_wrong', 'manual_add')),
    step_index       INTEGER NOT NULL DEFAULT 0,
    interval_days    INTEGER NOT NULL DEFAULT 0,
    due_date         TEXT    NOT NULL,           -- 只存日期，比较用 compute_review_date 的结果
    last_reviewed_at TEXT,
    review_count     INTEGER NOT NULL DEFAULT 0,
    lapse_count      INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL,
    deleted_by       INTEGER REFERENCES user(id),
    deleted_at       TEXT,
    purged_at        TEXT                        -- 到期"过期封存"，行留着，流水账仍可追溯
);

-- 学习模式的做题信号。只用于统计，不进回收站；改判就地更新。
CREATE TABLE study_attempt (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL REFERENCES user(id),
    question_id      INTEGER NOT NULL REFERENCES question_bank(id),
    subject_id       INTEGER NOT NULL REFERENCES subject(id),
    result           TEXT    NOT NULL CHECK (result IN ('wrong', 'right')),
    grade_source     TEXT    NOT NULL CHECK (grade_source IN ('auto', 'user_override', 'manual')),
    answer_submitted TEXT    NOT NULL DEFAULT '',
    recorded_on      TEXT    NOT NULL,           -- 复习日，与 review_log 同一个日历口径
    created_at       TEXT    NOT NULL
);

-- 追加式流水账：禁止 UPDATE、没有 deleted_at。统计与"这条日期为什么这么跳"的可追溯性全靠它。
CREATE TABLE review_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL REFERENCES user(id),
    mistake_id       INTEGER NOT NULL REFERENCES mistake(id),
    reviewed_on      TEXT    NOT NULL,           -- 复习日
    reviewed_at      TEXT    NOT NULL,
    rating           INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 4),
    rating_source    TEXT    NOT NULL CHECK (rating_source IN ('duration_default', 'user_override')),
    duration_seconds INTEGER NOT NULL,
    algorithm_version TEXT   NOT NULL,
    interval_before  INTEGER NOT NULL,
    interval_after   INTEGER NOT NULL,
    due_date_before  TEXT    NOT NULL,
    due_date_after   TEXT    NOT NULL,
    step_before      INTEGER NOT NULL,
    step_after       INTEGER NOT NULL
);

-- ---------------------------------------------------------------- 私人分类与收藏

CREATE TABLE tag (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES user(id),
    name       TEXT    NOT NULL,
    color      TEXT    NOT NULL DEFAULT '#6b7280',
    created_at TEXT    NOT NULL,
    deleted_at TEXT
);

CREATE TABLE tag_link (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES user(id),
    tag_id      INTEGER NOT NULL REFERENCES tag(id),
    target_type TEXT    NOT NULL,
    target_id   INTEGER NOT NULL,
    created_at  TEXT    NOT NULL,
    UNIQUE (tag_id, target_type, target_id)
);

-- 一张表管两类收藏：一个总入口，页内分「收藏的笔记」「收藏的知识点」。
CREATE TABLE favorite (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES user(id),
    target_type TEXT    NOT NULL CHECK (target_type IN ('note', 'knowledge_point')),
    target_id   INTEGER NOT NULL,
    created_at  TEXT    NOT NULL,
    UNIQUE (user_id, target_type, target_id)
);

-- ---------------------------------------------------------------- 导入会话

CREATE TABLE import_session (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL REFERENCES user(id),
    target           TEXT    NOT NULL CHECK (target IN ('question', 'knowledge_point', 'subject')),
    format           TEXT    NOT NULL CHECK (format IN ('csv', 'jsonl', 'ai')),
    source_filename  TEXT    NOT NULL DEFAULT '',
    owner            TEXT    NOT NULL DEFAULT 'self' CHECK (owner IN ('self', 'system')),
    default_visibility TEXT  NOT NULL DEFAULT 'private' CHECK (default_visibility IN ('private', 'shared')),
    status           TEXT    NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'committed', 'abandoned')),
    created_at       TEXT    NOT NULL
);

-- 预检失败也先留着：用户补完知识点回来一键重跑，不用重填重传。
CREATE TABLE import_session_row (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER NOT NULL REFERENCES import_session(id),
    line_no      INTEGER NOT NULL,
    payload_json TEXT    NOT NULL,
    error_code   TEXT    NOT NULL DEFAULT '',
    error_msg    TEXT    NOT NULL DEFAULT '',
    status       TEXT    NOT NULL DEFAULT 'ok' CHECK (status IN ('ok', 'blocked'))
);

-- ---------------------------------------------------------------- 申诉与反馈

-- 有处置权就必须有反驳的口子。提交人只在管理员侧可见，不向被处置的作者暴露。
CREATE TABLE appeal (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES user(id),
    category    TEXT    NOT NULL CHECK (category IN ('action', 'rejection', 'content', 'other')),
    target_type TEXT    NOT NULL CHECK (target_type IN ('question', 'knowledge_point', 'none')),
    target_id   INTEGER,
    reason      TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'handled')),
    admin_reply TEXT,
    handled_by  INTEGER REFERENCES user(id),
    handled_at  TEXT,
    created_at  TEXT    NOT NULL
);

-- ---------------------------------------------------------------- 索引

CREATE INDEX idx_mistake_queue      ON mistake(user_id, deleted_at, due_date);
CREATE INDEX idx_question_owner      ON question_bank(user_id, deleted_at);
CREATE INDEX idx_question_pool       ON question_bank(visibility, subject_id);
CREATE INDEX idx_review_log_range    ON review_log(user_id, reviewed_on);
CREATE INDEX idx_review_log_mistake  ON review_log(mistake_id);
CREATE INDEX idx_study_question      ON study_attempt(user_id, question_id);
CREATE INDEX idx_study_range         ON study_attempt(user_id, recorded_on);
CREATE INDEX idx_knowledge_status    ON knowledge_point(status, subject_id);
CREATE INDEX idx_note_owner          ON knowledge_note(user_id, knowledge_point_id, deleted_at);
CREATE INDEX idx_qkp_point           ON question_knowledge_point(knowledge_point_id);
CREATE INDEX idx_taglink_owner       ON tag_link(user_id, target_type, target_id);
CREATE INDEX idx_favorite_owner      ON favorite(user_id, target_type);
CREATE INDEX idx_subject_status      ON subject(status, deleted_at);
CREATE INDEX idx_import_resume       ON import_session(user_id, target, status);
CREATE INDEX idx_appeal_mine         ON appeal(user_id, status);
CREATE INDEX idx_appeal_target       ON appeal(target_type, target_id, status);

-- 防重复的锁一律带状态条件：隐藏库和回收站里的行不许白占名字，
-- 否则同名永远建不回来，查重还会提示"去选用一条对方根本看不见的记录"。
CREATE UNIQUE INDEX uq_subject_active   ON subject(name) WHERE deleted_at IS NULL AND status = 'active';
CREATE UNIQUE INDEX uq_kp_approved      ON knowledge_point(subject_id, name_normalized)
    WHERE deleted_at IS NULL AND status = 'approved';
CREATE UNIQUE INDEX uq_tag_active       ON tag(user_id, name) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX uq_mistake_active   ON mistake(user_id, question_id) WHERE deleted_at IS NULL;
