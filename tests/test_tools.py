from game.inventory import InventoryItem
from game.models import Character, GameState
from chain.tools import create_kp_tools


def test_no_tool_needed_tool():
    character = Character(name="测试")
    game_state = GameState()
    tools = create_kp_tools(character, game_state)
    noop = next(t for t in tools if t.name == "no_tool_needed")
    result = noop.invoke({"reason": "纯对话，无状态变更"})
    assert "可以开始叙事" in result


def test_create_kp_tools_excludes_combat_tools_when_requested():
    character = Character(name="测试")
    game_state = GameState()
    tools = create_kp_tools(
        character, game_state, exclude_roll_tools=True, exclude_combat_tools=True
    )
    names = {tool.name for tool in tools}
    assert "start_combat" not in names
    assert "player_attack" not in names
    assert "end_combat" in names


def test_create_kp_tools_excludes_roll_tools_when_requested():
    character = Character(name="测试")
    game_state = GameState()
    tools = create_kp_tools(character, game_state, exclude_roll_tools=True)
    names = {tool.name for tool in tools}
    assert "roll_dice" not in names
    assert "ability_check" not in names
    assert "update_inventory" in names


def test_create_kp_tools():
    character = Character(name="测试", strength=14)
    game_state = GameState()
    tools = create_kp_tools(character, game_state)
    names = {tool.name for tool in tools}
    assert names == {
        "no_tool_needed",
        "roll_dice",
        "ability_check",
        "update_scene",
        "record_npc",
        "update_quest",
        "start_combat",
        "player_attack",
        "end_combat",
        "update_inventory",
        "record_memory_fact",
        "update_skills",
    }


def test_ability_check_tool():
    character = Character(name="测试", intelligence=12)
    game_state = GameState()
    tools = create_kp_tools(character, game_state)
    check_tool = next(t for t in tools if t.name == "ability_check")
    result = check_tool.invoke({"ability": "int", "dc": 10})
    assert "智力检定" in result
    assert "DC 10" in result


def test_roll_dice_tool():
    character = Character(name="测试")
    game_state = GameState()
    tools = create_kp_tools(character, game_state)
    dice_tool = next(t for t in tools if t.name == "roll_dice")
    result = dice_tool.invoke({"notation": "d6"})
    assert "d6" in result


def test_roll_dice_tool_accepts_bare_100():
    character = Character(name="测试")
    game_state = GameState()
    tools = create_kp_tools(character, game_state)
    dice_tool = next(t for t in tools if t.name == "roll_dice")
    result = dice_tool.invoke({"notation": "100"})
    assert "d100" in result


def test_update_scene_tool():
    character = Character(name="测试")
    game_state = GameState()
    tools = create_kp_tools(character, game_state)
    scene_tool = next(t for t in tools if t.name == "update_scene")
    result = scene_tool.invoke({"scene_id": "harbor_dock", "scene_name": "灰港码头"})
    assert "灰港码头" in result
    assert game_state.scene_id == "harbor_dock"


def test_record_npc_tool():
    character = Character(name="测试")
    game_state = GameState()
    tools = create_kp_tools(character, game_state)
    npc_tool = next(t for t in tools if t.name == "record_npc")
    npc_tool.invoke({"name": "老水手", "attitude": "neutral", "notes": "知道雾夜秘密"})
    assert len(game_state.npcs) == 1
    assert game_state.npcs[0].name == "老水手"


def test_update_inventory_tool():
    character = Character(name="测试")
    game_state = GameState()
    tools = create_kp_tools(character, game_state)
    inv_tool = next(t for t in tools if t.name == "update_inventory")
    assert character.inventory == []

    add_result = inv_tool.invoke({"action": "add", "item": "手机"})
    assert "手机" in add_result
    assert character.inventory == [InventoryItem(name="手机", quantity=1, unit="个")]

    remove_result = inv_tool.invoke({"action": "remove", "item": "手机"})
    assert "移除" in remove_result
    assert character.inventory == []


def test_update_inventory_tool_with_quantity():
    character = Character(name="测试")
    game_state = GameState()
    tools = create_kp_tools(character, game_state)
    inv_tool = next(t for t in tools if t.name == "update_inventory")

    inv_tool.invoke({"action": "add", "item": "铜板", "quantity": 5, "unit": "枚"})
    assert character.inventory == [InventoryItem(name="铜板", quantity=5, unit="枚")]

    inv_tool.invoke({"action": "add", "item": "铜板", "quantity": 2, "unit": "枚"})
    assert character.inventory == [InventoryItem(name="铜板", quantity=7, unit="枚")]

    inv_tool.invoke({"action": "remove", "item": "铜板", "quantity": 3, "unit": "枚"})
    assert character.inventory == [InventoryItem(name="铜板", quantity=4, unit="枚")]


def test_character_starts_with_empty_inventory():
    character = Character(name="测试")
    assert character.inventory == []
    assert "空" in character.format_inventory()


def test_update_skills_tool():
    character = Character(name="测试")
    game_state = GameState()
    tools = create_kp_tools(character, game_state)
    skills_tool = next(t for t in tools if t.name == "update_skills")
    assert character.skills == []

    add_result = skills_tool.invoke({"action": "add", "skill": "观察"})
    assert "观察" in add_result
    assert character.skills == ["观察"]

    remove_result = skills_tool.invoke({"action": "remove", "skill": "观察"})
    assert "移除" in remove_result
    assert character.skills == []


def test_character_starts_with_empty_skills():
    character = Character(name="测试")
    assert character.skills == []
    assert "无" in character.format_skills()
