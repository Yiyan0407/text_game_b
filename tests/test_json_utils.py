from chain.json_utils import extract_json, extract_json_dict, extract_json_list


def test_extract_json_dict_repairs_trailing_comma():
    text = '{"approved": true, "action_intent": "检查文件",}'
    data = extract_json_dict(text)
    assert data is not None
    assert data["approved"] is True
    assert data["action_intent"] == "检查文件"


def test_extract_json_dict_repairs_single_quotes():
    text = "{'approved': True, 'action_intent': '帮忙查看'}"
    data = extract_json_dict(text)
    assert data is not None
    assert data["approved"] is True
    assert data["action_intent"] == "帮忙查看"


def test_extract_json_dict_from_markdown_fence():
    text = '说明如下：\n```json\n{"approved": true, "action_intent": "测试"}\n```\n完毕'
    data = extract_json_dict(text)
    assert data is not None
    assert data["action_intent"] == "测试"


def test_extract_json_list_repairs_trailing_comma():
    text = '["观察周围", "和老周交谈",]'
    data = extract_json_list(text)
    assert data == ["观察周围", "和老周交谈"]


def test_extract_json_returns_none_for_garbage():
    assert extract_json("not json at all") is None
