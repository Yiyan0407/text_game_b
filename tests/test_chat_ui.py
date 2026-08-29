"""Chat UI rendering helpers."""

from ui.chat import _STORY_KP_AVATAR, _SYSTEM_AVATAR, _system_caption
from ui.system_events import (
    classify_event,
    compact_system_events,
    format_tool_event_content,
    tagged_line,
)


def test_system_and_kp_use_different_avatars():
    assert _SYSTEM_AVATAR != _STORY_KP_AVATAR


def test_format_tool_event_strips_dice_prefix():
    assert format_tool_event_content("🎲 敏捷检定 成功") == "敏捷检定 成功"


def test_system_caption_for_settlement_router():
    assert "结算" in _system_caption("结算路由：inventory,time（观察）")


def test_system_caption_for_alert():
    assert _system_caption("⚠️ 行动无法执行") == "系统 · 提示"


def test_tagged_line_for_check():
    line = tagged_line("【魅力检定】1d20[8]+3 = 11 vs DC 14 → 失败")
    assert line.startswith("[检定]")


def test_tagged_line_for_failure_consequence():
    tag, body = classify_event("📌 行动失败：去找工作人员交谈")
    assert tag == "后果"
    assert "工作人员" in body


def test_tagged_line_for_scene_and_bare_npc():
    assert tagged_line("场景已更新：B8层设备间（2020-nyc-b8-equipment-room）").startswith("[场景]")
    assert tagged_line("未知实体（hostile）").startswith("[NPC]")


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
    assert "[时间]" in view.summary
    assert "08:06" in view.summary
    assert "[NPC] ×1" in view.summary
    assert "[记忆] ×2" in view.summary
    assert view.show_expander is True
    assert all(line.startswith("[") for line in view.details)


def test_compact_check_stays_prominent():
    view = compact_system_events(["🎲 敏捷检定 14 vs DC12 成功"])
    assert view.highlights == ["[检定] 敏捷检定 14 vs DC12 成功"]
    assert view.caption == "系统 · 检定/战斗"


def test_compact_mixed_check_and_settlement():
    events = [
        "【魅力检定】1d20[8]+3 = 11 vs DC 14 → 失败",
        "📌 行动失败：去找找工作人员吧，我需要和人交谈一下",
        "⏳ 时间推进 5 分（第1天 09:06） — 从B12层返回B8层并探索设备间",
        "场景已更新：B8层设备间（2020-nyc-b8-equipment-room）",
        "未知实体（hostile）",
        "已记录关键事实：B8层设备间内发现一本笔记本，上面写着‘别去B20’",
    ]
    view = compact_system_events(events)
    assert view.caption == "系统 · 回合"
    assert view.highlights[0].startswith("[检定]")
    assert view.highlights[1].startswith("[后果]")
    assert "[时间]" in view.summary
    assert "[记忆]" in view.summary
