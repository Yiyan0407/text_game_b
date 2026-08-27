"""角色背景合理性校验（创角用）。"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class BackgroundValidationResult:
    approved: bool
    rejection_reason: str = ""


# 高置信「开局超模」表述 —— 命中即直接驳回
_HARD_REJECT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"全知全能|无所不能|一念灭(?:世|国)|毁灭世界|修改现实|操纵时间|时间倒流"), "背景包含超出凡人/新手冒险者的权能设定。"),
    (re.compile(r"开局(?:即)?无敌|天下无敌|举世无双|独断万古|最强(?:存在|者)?|宇宙(?:之主|第一)"), "背景不应设定为开局即无敌或宇宙顶级存在。"),
    (
        re.compile(
            r"(?:我是|身为|已是|作为).{0,6}(?:仙帝|仙尊|道祖|创世神|天帝|神皇)"
            r"|(?:仙帝|仙尊|道祖).{0,6}(?:转世|重生|血脉|传承(?:者)?)"
        ),
        "背景不应设定为神话级顶层身份开局。",
    ),
    (re.compile(r"GM|游戏管理员|系统管理员|开挂|官方账号"), "背景不应包含元游戏/管理员式特权。"),
    (re.compile(r"(?:满级|等级\s*99|lv\s*99|level\s*99|MAX\s*LEVEL)", re.I), "背景不应声明已满级或超高等级。"),
    (re.compile(r"(?:系统|金手指).{0,8}(?:满|顶级|SSS|终极|无敌|全开)"), "背景不应携带满配/终极系统外挂。"),
    (re.compile(r"(?:全|各)属性\s*[12]?\d{2,}|[Hh][Pp]\s*(?:∞|无限|9999)"), "背景不得自行声明超出掷骰规则的属性或生命。"),
    (re.compile(r"(?:元婴|化神|合体|大乘|渡劫|真仙|金仙|大罗|太乙).{0,6}(?:期|境|修士|真人)"), "修仙背景开局境界过高，请从低阶修士/凡人写起。"),
    (re.compile(r"(?:随身|开局|自带|拥有).{0,10}(?:仙器|神器|先天灵宝|混沌至宝|至尊法宝)"), "背景不应开局持有顶级神器/仙器。"),
    (re.compile(r"(?:亿|万亿|千百?万)\s*(?:灵石|金币|资产|财富)"), "背景不应开局拥有破坏经济平衡的巨额资源。"),
    (re.compile(r"齐天大圣|斗战胜佛|如来|上帝|宙斯|奥丁(?=.*(?:附身|上身|我是))"), "背景不应直接扮演或附身顶级神话原型。"),
)


def validate_background_quick(
    background: str,
    *,
    world_id: str = "",
) -> BackgroundValidationResult:
    text = background.strip()
    if not text:
        return BackgroundValidationResult(approved=True)

    if len(text) > 500:
        return BackgroundValidationResult(
            approved=False,
            rejection_reason="背景过长（最多 500 字），请精简。",
        )

    normalized = re.sub(r"\s+", "", text.lower())
    for pattern, reason in _HARD_REJECT_PATTERNS:
        if pattern.search(text) or pattern.search(normalized):
            return BackgroundValidationResult(approved=False, rejection_reason=reason)

    # 现代/赛博：开局即顶层权力
    if world_id in ("modern", "cyberpunk", ""):
        if re.search(r"(?:掌控|统治).{0,6}(?:世界|国家|全球|财团|网络)", text):
            return BackgroundValidationResult(
                approved=False,
                rejection_reason="背景不应开局即拥有统治世界/全球网络的权能。",
            )

    return BackgroundValidationResult(approved=True)
