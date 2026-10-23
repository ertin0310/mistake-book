"""步 8 演示（页面层）：浏览器上真的录 5 道题、按科目筛、翻页。

用 Flask 的测试客户端跑真路由：会话、防冒名签、模板渲染、翻页 URL 全都真的走一遍，
不是只测函数。
"""

from config import prompts
from tests.conftest import csrf_token, sign_up

STEM = "为什么引入线程？它比进程轻在哪里？"


def post_question(client, stem=STEM, subject="1", answer="线程共享地址空间", explanation=""):
    return client.post("/study/new", data={
        "subject_id": subject, "type": "essay", "stem": stem,
        "answer": answer, "explanation": explanation,
        "csrf_token": csrf_token(client, "/study/new")})


def test_study_pages_require_login(client):
    assert client.get("/study/").status_code == 302
    assert client.get("/study/new").status_code == 302


def test_new_question_form_renders_and_sidebar_opens(client):
    sign_up(client, username="stu")
    body = client.get("/study/new").get_data(as_text=True)
    assert "录一道题" in body and "参考答案" in body
    sidebar = client.get("/study/").get_data(as_text=True)
    assert "我的题目" in sidebar and "刷我的题" in sidebar and "共享池刷题" in sidebar
    assert prompts.MENU_GROUP_EMPTY["学习"] not in sidebar      # 这一组不再是空的


def test_record_five_then_they_show_in_the_list(client):
    sign_up(client, username="stu")
    for n in range(5):
        assert post_question(client, stem=f"{STEM} 第 {n} 问").status_code == 302
    body = client.get("/study/").get_data(as_text=True)
    assert "第 0 问" in body and "第 4 问" in body
    assert "共 5 条" in body


def test_empty_stem_is_rejected_and_text_is_kept(client):
    sign_up(client, username="stu")
    response = client.post("/study/new", data={
        "subject_id": "1", "type": "essay", "stem": "", "answer": "有答案",
        "csrf_token": csrf_token(client, "/study/new")})
    body = response.get_data(as_text=True)
    assert response.status_code == 400 and "题干必填项不能空着。" in body
    assert 'name="stem"' in body                                 # 表单还在，不用重填


def test_missing_token_cannot_write_to_the_database(client):
    sign_up(client, username="stu")
    response = client.post("/study/new", data={"subject_id": "1", "type": "essay",
                                               "stem": "没签的题", "answer": "答案"})
    assert response.status_code == 400
    assert prompts.CSRF_FAILED in response.get_data(as_text=True)
    assert "没签的题" not in client.get("/study/").get_data(as_text=True)


def test_hidden_subject_cannot_be_picked(client):
    """fixture 里"英语"是下架科目：下拉里不该出现，硬提交也被拦。"""
    sign_up(client, username="stu")
    body = client.get("/study/new").get_data(as_text=True)
    assert "英语" not in body
    response = post_question(client, subject="2")
    assert response.status_code == 400
    assert prompts.SUBJECT_UNUSABLE in response.get_data(as_text=True)


def test_list_paginates_at_twenty_and_falls_back(client):
    sign_up(client, username="stu")
    for n in range(25):
        post_question(client, stem=f"题目 {n}")
    first = client.get("/study/").get_data(as_text=True)
    assert "共 25 条 · 每页 20" in first and "下一页" in first
    second = client.get("/study/?page=2").get_data(as_text=True)
    assert "题目 24" not in second          # 第二页只剩 5 条，最新的在第一页
    assert "题目 4" in second              # 第 21~25 条（编号 20..24 倒序）落在第二页
    assert client.get("/study/?page=999").status_code == 200


def test_subject_filter_narrows_the_list(client):
    sign_up(client, username="stu")
    post_question(client, stem="数学题", subject="1")
    post_question(client, stem="另一道数学题", subject="1")
    body = client.get("/study/?subject=1").get_data(as_text=True)
    assert "数学题" in body and "共 2 条" in body
    other = client.get("/study/?subject=2").get_data(as_text=True)
    assert prompts.SUBJECT_UNUSABLE in other or "共 0 条" in other or "还没有题目" in other


def test_shared_pool_page_lists_others_questions(client):
    """共享池里是"别人的共享题 + 官方题"；自己那道私有的绝不出现（共享默认关闭）。"""
    sign_up(client, username="owner")
    post_question(client, stem="要共享的题")
    client.post("/logout", data={"csrf_token": csrf_token(client, "/study/")})
    sign_up(client, username="guest")
    body = client.get("/study/drill").get_data(as_text=True)
    assert "题干 4" in body and "题干 6" in body       # u2 的共享题 + 官方题
    assert "要共享的题" not in body


def test_practice_own_bank_has_its_own_entry(client):
    """★ 刷自己的题库早就有（/study/practice），只是侧边栏没给入口——现在补上，
    并把原来那条含糊的"题库刷题"改叫"共享池刷题"，两条一眼分得开。"""
    sign_up(client, username="stu")
    post_question(client, stem="我自己录的一道题")
    bar = client.get("/study/").get_data(as_text=True)
    assert "/study/practice" in bar and "共享池刷题" in bar
    body = client.get("/study/practice").get_data(as_text=True)
    assert "我自己录的一道题" in body
