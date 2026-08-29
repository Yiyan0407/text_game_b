"""Chat UI rendering helpers."""

from ui.chat import _STORY_KP_AVATAR, _SYSTEM_AVATAR, _system_caption
from ui.system_events import compact_system_events, format_tool_event_content


def test_system_and_kp_use_different_avatars():
    assert _SYSTEM_AVATAR != _STORY_KP_AVATAR


def test_format_tool_event_strips_dice_prefix():
    assert format_tool_event_content("🎲 敏捷检定 成功") == "敏捷检定 成功"


def test_system_caption_for_settlement_router():
    assert "结算" in _system_caption("结算路由：inventory,time（观察）")


def test_system_caption_for_alert():
    assert _system_caption("⚠️ 行动无法执行") == "系统 · 提示"


def test_compact_settlement_batch():
    events = [
        "结算路由：time,world（KP叙事中玩家移动至力夫行）",
        "⏳ 时间推进 3 分（第1天 08:06） — 走向力夫行并进行简短问答",
        "已记录 NPC：力夫行工头（neutral）",
        "已记录关键事实：力夫行招工往山上背货，半天活可换两枚下品灵石，当日结清",
        "已记录关键事实：往秘境入口附近送补给的活儿价更高，但各派修士扎堆，需小心",
    ]
    view = compact_system_events(events)
    assert view.caption == "系统 · 结算"
    assert "08:06" in view.summary
    assert "NPC×1" in view.summary
    assert "记忆×2" in view.summary
    assert view.show_expander is True
    assert len(view.details) >= 3


def test_compact_check_stays_prominent():
    view = compact_system_events(["🎲 敏捷检定 14 vs DC12 成功"])
    assert view.highlights == ["敏捷检定 14 vs DC12 成功"]
    assert view.caption == "系统 · 检定/战斗"


def test_compact_mixed_check_and_settlement():
    events = [
        "🎲 敏捷检定 14 vs DC12 成功",
        "⏳ 时间推进 2 分（第1天 08:02）",
        "已记录关键事实：听到走廊脚步声",
    ]
    view = compact_system_events(events)
    assert view.caption == "系统 · 回合"
    assert view.highlights
    assert "记忆×1" in view.summary
