from game.models import Character, ChatMessage, GameState
from game.pdf_export import (
    _FONT_NAME,
    _markdown_to_paragraph,
    _strip_embedded_role_header,
    build_game_pdf,
    suggest_pdf_filename,
)
from game.scenario import Scenario


def test_build_game_pdf_contains_basic_sections():
    scenario = Scenario(
        id="midnight_archive",
        title="午夜档案",
        description="调查被删邮件。",
        world_id="modern",
    )
    character = Character(name="测试员", background="IT 外包")
    game_state = GameState(
        current_scene="报社·夜班工位",
        scene_id="newsroom",
        turn_count=2,
        story_summary="已收到匿名压缩包。",
    )
    messages = [
        ChatMessage(role="user", content="观察周围"),
        ChatMessage(role="assistant", content="空荡的编辑部里只有键盘声。"),
        ChatMessage(role="system", content="【智力检定】1d20[12]+0 = 12 vs DC 14 → 失败"),
    ]
    pdf_bytes = build_game_pdf(
        scenario=scenario,
        character=character,
        game_state=game_state,
        messages=messages,
    )
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 800


def test_build_game_pdf_with_long_summary():
    scenario = Scenario(id="test", title="午夜档案", world_id="modern")
    character = Character(name="测试员")
    long_summary = "剧情进展：" + ("这是一段很长的摘要。" * 400)
    game_state = GameState(turn_count=10, story_summary=long_summary)
    messages = [ChatMessage(role="assistant", content="短回复。")]
    pdf_bytes = build_game_pdf(
        scenario=scenario,
        character=character,
        game_state=game_state,
        messages=messages,
    )
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1500


def test_markdown_to_paragraph_renders_common_syntax():
    html = _markdown_to_paragraph("**重要线索**\n\n- 第一条\n- *第二条*")
    assert "<b>重要线索</b>" in html
    assert "• 第一条" in html
    assert "<i>第二条</i>" in html


def test_build_game_pdf_with_markdown_messages():
    scenario = Scenario(id="test", title="午夜档案", world_id="modern")
    character = Character(name="测试员")
    game_state = GameState(turn_count=1)
    messages = [
        ChatMessage(role="user", content="检查 **邮件**"),
        ChatMessage(role="assistant", content="## 发现\n\n有一封 `encrypted.zip`。"),
    ]
    pdf_bytes = build_game_pdf(
        scenario=scenario,
        character=character,
        game_state=game_state,
        messages=messages,
    )
    assert pdf_bytes.startswith(b"%PDF")


def test_inline_markdown_uses_cjk_font_for_chinese_code():
    html = _markdown_to_paragraph("文件夹 `内部邮件备份_2024`，压缩包 `anonymous_leak_0117.zip`。")
    assert f'name="{_FONT_NAME}"' in html
    assert "内部邮件备份_2024" in html
    assert 'face="Courier"' in html
    assert html.index(f'name="{_FONT_NAME}"') < html.index("内部邮件备份_2024")
    assert html.index('face="Courier"') < html.index("anonymous_leak_0117.zip")


def test_inline_markdown_does_not_break_on_underscore_filenames():
    html = _markdown_to_paragraph(
        "文件夹——`内部邮件备份_2024`，加上 `anonymous_leak_0117.zip`。"
    )
    assert "<i>" not in html
    assert "anonymous_leak_0117.zip" in html
    assert "内部邮件备份_2024" in html


def test_build_game_pdf_with_underscore_rich_narrative():
    scenario = Scenario(id="test", title="午夜档案", world_id="modern")
    character = Character(name="测试员")
    game_state = GameState(turn_count=1)
    narrative = (
        "你打开资源管理器，找到文件夹——`内部邮件备份_2024`，47封邮件，"
        "加上原始压缩包 `anonymous_leak_0117.zip`。"
    )
    messages = [ChatMessage(role="assistant", content=narrative)]
    pdf_bytes = build_game_pdf(
        scenario=scenario,
        character=character,
        game_state=game_state,
        messages=messages,
    )
    assert pdf_bytes.startswith(b"%PDF")


def test_strip_embedded_role_header():
    raw = "◆ 玩家\n问问这些邮件内容的影响"
    assert _strip_embedded_role_header(raw) == "问问这些邮件内容的影响"


def test_build_game_pdf_with_role_prefixed_content():
    scenario = Scenario(id="test", title="午夜档案", world_id="modern")
    character = Character(name="测试员")
    game_state = GameState(turn_count=1)
    messages = [
        ChatMessage(role="user", content="◆ 玩家\n问问这些邮件内容的影响"),
        ChatMessage(
            role="assistant",
            content='◆ KP\n"老周，"你开口，语气平静但直接，"这些东西如果属实，对报社意味着什么？"',
        ),
    ]
    pdf_bytes = build_game_pdf(
        scenario=scenario,
        character=character,
        game_state=game_state,
        messages=messages,
    )
    assert pdf_bytes.startswith(b"%PDF")


def test_suggest_pdf_filename():
    scenario = Scenario(id="test", title="午夜档案/分享版", world_id="modern")
    character = Character(name="阿 Oct")
    name = suggest_pdf_filename(scenario, character)
    assert name.endswith(".pdf")
    assert "午夜档案" in name
    assert "阿" in name
