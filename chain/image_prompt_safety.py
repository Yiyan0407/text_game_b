"""图片 API 提示词合规化：降低版权/敏感内容拦截概率。"""

from __future__ import annotations

import re

# 常见易触发版权检测的词（小写匹配）；命中则移除
_IP_TERMS: tuple[str, ...] = (
    "哈利波特",
    "霍格沃茨",
    "迪士尼",
    "漫威",
    "钢铁侠",
    "蜘蛛侠",
    "美国队长",
    "原神",
    "崩坏",
    "星穹铁道",
    "塞尔达",
    "林克",
    "马里奥",
    "皮卡丘",
    "/pokemon",
    "pokemon",
    "迪士尼",
    "米老鼠",
    "艾莎",
    "冰雪奇缘",
    "孙悟空",
    "西游记",
    "哪吒",
    "奥特曼",
    "哥斯拉",
    "星战",
    "星球大战",
    "达斯维达",
    "绝地武士",
    "龙与地下城",
    "dungeons & dragons",
    "dnd",
    "warhammer",
    "战锤",
    "魔兽",
    "world of warcraft",
    "wow",
    "最终幻想",
    "final fantasy",
    "鬼灭",
    "火影",
    "海贼王",
    "one piece",
    "naruto",
    "进击的巨人",
    "蝙蝠侠",
    "超人",
    "joker",
    "小丑",
)

_POLICY_MARKERS: tuple[str, ...] = (
    "sensitivecontent",
    "policyviolation",
    "copyright",
    "content policy",
    "内容安全",
    "敏感内容",
    "版权",
)


def is_content_policy_error(error: str) -> bool:
    lowered = (error or "").lower()
    return any(marker in lowered for marker in _POLICY_MARKERS)


def format_content_policy_hint(error: str) -> str:
    return (
        f"{error}\n\n"
        "图片服务认为提示词可能涉及版权或敏感内容。\n"
        "建议：\n"
        "· 角色名与背景避免现有作品人名、品牌或 IP（如迪士尼、原神、漫威角色等）\n"
        "· 改用原创身份描述（如「边境佣兵」「雾港调查员」）\n"
        "· 修改后点击「重新生成立绘」；若仍被拦截，系统会用清洗敏感词后的完整画风提示词自动重试"
    )


def sanitize_image_text(text: str, *, max_len: int = 200) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    for term in _IP_TERMS:
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        cleaned = pattern.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，,、;；")
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 1].rstrip() + "…"
    return cleaned


def generic_role_hint(background: str) -> str:
    text = sanitize_image_text(background, max_len=120)
    return text or "一位原创冒险者"


def build_safe_scene_prompt(scene_name: str, world: str, tone: str) -> str:
    from chain.image_style import SCENE_STYLE, SCENE_TAIL

    mood = sanitize_image_text(tone or "神秘", max_len=32) or "神秘"
    place = sanitize_image_text(scene_name, max_len=64) or "虚构场景"
    setting = sanitize_image_text(world, max_len=64) or "幻想世界"
    return (
        f"{SCENE_STYLE}"
        f"地点：{place}。世界设定：{setting}。基调：{mood}。"
        f"{SCENE_TAIL}"
    )
