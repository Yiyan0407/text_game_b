"""世界观规则包配置。"""

WORLD_OPTIONS: dict[str, str] = {
    "modern": "现代都市",
    "cyberpunk": "赛博朋克",
    "xianxia": "修仙",
    "fantasy": "低魔奇幻",
}

DEFAULT_WORLD_ID = "modern"

THEME_HINTS: dict[str, list[str]] = {
    "modern": ["都市悬疑", "职场秘辛", "校园事件", "公路逃亡", "谍战行动", "完全随机"],
    "cyberpunk": ["企业阴谋", "地下赛跑", "AI叛逃", "义体手术", "完全随机"],
    "xianxia": ["秘境探险", "宗门恩怨", "丹劫奇遇", "散修崛起", "完全随机"],
    "fantasy": ["迷雾调查", "dungeon探索", "王国阴谋", "完全随机"],
}

GENERATION_MODES = {
    "full": "完整剧本（含任务、节点、结局）",
    "world": "仅世界观设定（背景与基调，开场由 KP 即兴）",
}
