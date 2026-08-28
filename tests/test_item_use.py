from chain.opening_integrator import OpeningIntegrator
from game.inventory import InventoryItem
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


def test_resolve_use_item_durable_equips_without_consume():
    character = Character(
        name="测试",
        inventory=[InventoryItem(name="头戴式手电筒", quantity=1, unit="个")],
    )
    events = resolve_use_item(character, ["头戴式手电筒"])
    assert any("持用" in event for event in events)
    assert character.has_inventory_item("头戴式手电筒")
    assert character.is_item_active("头戴式手电筒")
    assert character.format_active_gear() == "头戴式手电筒（照明中）"


def test_resolve_use_item_durable_toggle_unequip():
    character = Character(
        name="测试",
        inventory=[InventoryItem(name="军用多功能铁锹", quantity=1, unit="把")],
    )
    resolve_use_item(character, ["军用多功能铁锹"])
    assert character.is_item_active("军用多功能铁锹")
    events = resolve_use_item(character, ["军用多功能铁锹"])
    assert any("收起" in event for event in events)
    assert not character.is_item_active("军用多功能铁锹")
    assert character.has_inventory_item("军用多功能铁锹")


def test_resolve_use_item_document_not_consumed():
    character = Character(
        name="测试",
        inventory=[InventoryItem(name="加密文档副本", quantity=1, unit="份")],
    )
    events = resolve_use_item(character, ["加密文档副本"])
    assert any("查阅" in event for event in events)
    assert character.has_inventory_item("加密文档副本")


def test_resolve_use_item_consumable_food():
    character = Character(
        name="测试",
        inventory=[InventoryItem(name="压缩饼干", quantity=3, unit="包")],
    )
    events = resolve_use_item(character, ["压缩饼干"])
    assert any("使用" in event for event in events)
    assert character.inventory[0].quantity == 2

