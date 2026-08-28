import json

from game.models import Character
from game.opening_brief import OpeningBrief
from game.orchestrator import _build_start_instruction
from game.scenario import Scenario


def test_opening_brief_format_for_kp():
    brief = OpeningBrief(
        role_in_story="科技公司 CEO，以股东代表身份到场",
        why_at_scene="匿名包牵涉其公司数据泄露",
        hook_alignment="保留报社夜班与匿名包调查，非普通记者",
        narrative_constraints=["不得写成实习记者", "不得否认 CEO 身份"],
    )
    text = brief.format_for_kp()
    assert "【开场入场逻辑】" in text
    assert "CEO" in text
    assert "不得写成实习记者" in text


def test_opening_brief_fallback():
    scenario = Scenario(
        id="midnight_archive",
        title="午夜档案",
        opening_scene_name="报社·夜班工位",
        opening_prompt="匿名账号发来压缩包，需在夜班编辑部调查。",
    )
    brief = OpeningBrief.fallback("张明", "某科技公司 CEO", scenario)
    assert "张明" in brief.role_in_story
    assert "CEO" in brief.role_in_story
    assert "矛盾" in brief.narrative_constraints[0]


def test_opening_brief_fallback_hacker_keeps_anonymity():
    scenario = Scenario(
        id="midnight_archive",
        title="午夜档案",
        opening_scene_name="报社·夜班工位",
        opening_prompt="匿名账号发来压缩包。",
    )
    brief = OpeningBrief.fallback("阿 Oct", "地下有名的黑客，常用 octopus 通道", scenario)
    text = brief.format_for_kp()
    assert brief.secrets_from_npcs
    assert "octopus" in text.lower() or "匿名" in text
    assert "NPC 此时还不应知道" in text


def test_opening_integrator_parse():
    from chain.opening_integrator import OpeningIntegrator

    payload = {
        "role_in_story": "IT 外包顾问在场",
        "why_at_scene": "维护网络",
        "hook_alignment": "匿名包已抵达编辑部",
        "public_setup": "octopus 渠道送来压缩包，来源不明",
        "secrets_from_npcs": ["陈薇不知道玩家就是 octopus"],
        "narrative_constraints": ["不要写成普通记者"],
    }
    brief = OpeningIntegrator._parse_response(json.dumps(payload))
    assert "IT" in brief.role_in_story
    assert brief.secrets_from_npcs == ["陈薇不知道玩家就是 octopus"]


def test_build_start_instruction_includes_brief(monkeypatch):
    scenario = Scenario(id="test", title="测试", opening_prompt="起点")
    character = Character(name="测试", background="CEO")

    class FakeIntegrator:
        def generate(self, _character, _scenario):
            return OpeningBrief(
                role_in_story="CEO 入场",
                why_at_scene="调查",
                hook_alignment="对齐模组",
            )

    text = _build_start_instruction(
        character,
        scenario,
        career_context="【长期角色履历】测试",
        integrator=FakeIntegrator(),
    )
    assert "【开场入场逻辑】" in text
    assert "CEO 入场" in text
    assert "【长期角色履历】" in text
    assert "一致性硬性要求" in text
