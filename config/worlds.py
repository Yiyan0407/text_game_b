"""世界观规则包配置。"""

WORLD_OPTIONS: dict[str, str] = {
    "modern": "现代都市",
    "cyberpunk": "赛博朋克",
    "scifi": "科幻未来",
    "post_apoc": "废土末世",
    "steampunk": "蒸汽朋克",
    "historical": "历史写实",
    "coc": "克苏鲁调查",
    "wuxia": "武侠江湖",
    "xianxia": "修仙",
    "fantasy": "低魔奇幻",
}

VALID_WORLD_IDS: tuple[str, ...] = tuple(WORLD_OPTIONS.keys())

DEFAULT_WORLD_ID = "modern"

THEME_HINTS: dict[str, list[str]] = {
    "modern": ["都市悬疑", "职场秘辛", "校园事件", "公路逃亡", "谍战行动", "完全随机"],
    "cyberpunk": ["企业阴谋", "地下赛跑", "AI叛逃", "义体手术", "完全随机"],
    "scifi": ["时空穿越", "星际殖民", "外星接触", "实验室逃亡", "完全随机"],
    "post_apoc": ["废土求生", "避难所阴谋", "变异兽潮", "拾荒车队", "完全随机"],
    "steampunk": ["飞艇劫案", "钟表工坊", "帝国谍报", "地下革命", "完全随机"],
    "historical": ["古代探案", "边疆战事", "朝堂权谋", "近代谍战", "完全随机"],
    "coc": ["禁忌档案", "孤岛疑云", "邪教复苏", "理智危机", "完全随机"],
    "wuxia": ["江湖恩怨", "镖局劫案", "门派争锋", "隐世奇侠", "完全随机"],
    "xianxia": ["秘境探险", "宗门恩怨", "丹劫奇遇", "散修崛起", "完全随机"],
    "fantasy": ["迷雾调查", "dungeon探索", "王国阴谋", "完全随机"],
}

GENERATION_MODES = {
    "full": "完整剧本（含任务、节点、结局）",
    "world": "仅世界观设定（背景与基调，开场由 KP 即兴）",
}
