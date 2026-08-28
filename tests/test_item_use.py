from chain.opening_integrator import OpeningIntegrator
from game.item_use import resolve_use_item
from game.models import Character
from game.scenario import Scenario


def test_opening_integrator_marks_fallback(monkeypatch):
    class BrokenLLM:
        def invoke(self, _inputs):
            raise RuntimeError("boom")

    integrator = OpeningIntegrator()
    monkeypatch.setattr(integrator, "llm", BrokenLLM())
    scenario = Scenario(id="test", title="测试", opening_prompt="起点")
    character = Character(name="测试", background="斥候")

    brief = integrator.generate(character, scenario)

    assert brief.used_fallback is True
    assert "测试" in brief.role_in_story


def test_opening_integrator_success_is_not_fallback(monkeypatch):
    integrator = OpeningIntegrator()
    mock_chain = type("Chain", (), {})()
    mock_chain.invoke = lambda _inputs: type(
        "Response",
        (),
        {
            "content": (
                '{"role_in_story":"外包顾问","why_at_scene":"修网络",'
                '"hook_alignment":"对齐模组"}'
            )
        },
    )()

    class FakePrompt:
        def __or__(self, _llm):
            return mock_chain

    monkeypatch.setattr(integrator, "prompt", FakePrompt())
    scenario = Scenario(id="test", title="测试", opening_prompt="起点")
    character = Character(name="测试", background="斥候")

    brief = integrator.generate(character, scenario)

    assert brief.used_fallback is False
    assert brief.role_in_story == "外包顾问"


def test_resolve_use_item_healing_potion():
    character = Character(name="测试", hp=5, max_hp=20, inventory=["治疗药水"])
    events = resolve_use_item(character, ["治疗药水"])
    assert any("使用" in event for event in events)
    assert character.hp > 5
    assert not character.has_inventory_item("治疗药水")
