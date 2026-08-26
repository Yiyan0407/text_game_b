from chain.suggestions import ActionSuggester


def test_parse_suggestions_json():
    text = '["调查酒馆", "询问酒保", "观察门口"]'
    items = ActionSuggester._parse_suggestions(text)
    assert items == ["调查酒馆", "询问酒保", "观察门口"]


def test_parse_suggestions_lines():
    text = "- 搜索房间\n- 打开箱子\n- 离开"
    items = ActionSuggester._parse_suggestions(text)
    assert len(items) == 3
    assert "搜索房间" in items[0]


def test_load_world_prompts():
    from config.worlds import WORLD_OPTIONS
    from prompts.templates import load_world_prompt, load_kp_system_prompt

    for world_id in WORLD_OPTIONS:
        prompt = load_world_prompt(world_id)
        assert len(prompt) > 20

    system = load_kp_system_prompt("xianxia")
    assert "修仙" in system
