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
    "outputimage",
    "inputtext",
    "内容安全",
    "敏感内容",
    "敏感信息",
    "版权",
)


def is_output_policy_error(error: str) -> bool:
    lowered = (error or "").lower()
    return "outputimage" in lowered or "输出图片" in lowered or "输出图像" in lowered


def is_content_policy_error(error: str) -> bool:
    lowered = (error or "").lower()
    return any(marker in lowered for marker in _POLICY_MARKERS)


def format_content_policy_hint(error: str) -> str:
    output_blocked = is_output_policy_error(error)
    target = "生成的图片" if output_blocked else "提示词"
    return (
        f"{error}\n\n"
        f"图片服务认为{target}可能涉及敏感或版权内容。\n"
        "系统已自动尝试：① 清洗提示词 ② AI 矫正提示词 后重试。\n"
        "若仍失败，建议：\n"
        "· 背景改为更中性的原创身份（如「边境佣兵」「雾港调查员」）\n"
        "· 避免血腥、惊悚、裸露、知名 IP/名人等描述\n"
        "· 修改后再次点击生成"
    )


def format_image_generation_error(error: str) -> str:
    """将图片 API 原始错误转为用户可读说明（避免重复包装）。"""
    text = (error or "").strip()
    if not text:
        return "出图失败，请稍后重试。"
    if "系统已自动尝试" in text:
        return text
    if is_content_policy_error(text):
        return format_content_policy_hint(text)
    return text


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
