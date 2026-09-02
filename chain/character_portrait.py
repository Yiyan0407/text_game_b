"""角色立绘生成（复用场景图的 Seedream / DALL·E 通道）。"""

from config.settings import get_settings
from config.worlds import WORLD_OPTIONS
from chain.image_prompt_safety import sanitize_image_text
from chain.image_style import PORTRAIT_STYLE, PORTRAIT_TAIL
from chain.scene_image import ImageGenerationResult, generate_with_policy_fallback
from game.profile import CharacterCard


def _world_label(world_id: str) -> str:
    if not world_id.strip():
        return "奇幻冒险"
    return WORLD_OPTIONS.get(world_id.strip(), world_id.strip())


def _appearance_hints(card: CharacterCard, *, safe_mode: bool = False) -> str:
    parts: list[str] = []
    if card.equipment:
        worn = "、".join(entry.item_name for entry in card.equipment[:4])
        if safe_mode:
            worn = sanitize_image_text(worn, max_len=48)
        if worn:
            parts.append(f"可见装备：{worn}")
    if card.inventory:
        carried = "、".join(item.name for item in card.inventory[:4])
        if safe_mode:
            carried = sanitize_image_text(carried, max_len=48)
        if carried:
            parts.append(f"随身物品：{carried}")
    if not safe_mode:
        if card.career_summary.strip():
            parts.append(f"经历气质：{card.career_summary.strip()[:200]}")
        elif card.campaign_history:
            latest = card.campaign_history[-1]
            if latest.summary.strip():
                parts.append(f"近期经历：{latest.summary.strip()[:160]}")
        if card.notable_facts:
            parts.append(f"外貌或气质线索：{'；'.join(card.notable_facts[-3:])[:180]}")
    if card.deceased:
        if safe_mode:
            parts.append("疲惫战损气质，仍保持人物辨识度。")
        else:
            parts.append("角色已阵亡：面容疲惫、战损或沉重气质，但仍保持人物辨识度。")
    return " ".join(parts)


def build_portrait_prompt(
    card: CharacterCard,
    *,
    world_id: str = "",
    safe_mode: bool = False,
) -> str:
    world = _world_label(world_id or card.preferred_world_id)
    hints = _appearance_hints(card, safe_mode=safe_mode)
    hint_block = f" {hints}" if hints else ""

    appearance_block = card.appearance.format_for_prompt()
    if safe_mode and appearance_block:
        appearance_block = sanitize_image_text(appearance_block, max_len=140)
    appearance_text = f"外貌设定：{appearance_block}。" if appearance_block else ""

    background = sanitize_image_text(
        card.background.strip() or "一位冒险者。",
        max_len=100 if safe_mode else 160,
    ) or "一位原创冒险者"

    if safe_mode:
        identity_line = f"人物设定：{background}。"
    else:
        name = sanitize_image_text(card.name, max_len=16) or "主角"
        identity_line = f"角色称呼：{name}。人物设定：{background}。"

    return (
        f"{PORTRAIT_STYLE}"
        f"{identity_line}"
        f"{appearance_text}"
        f"世界观氛围：{world}。{hint_block}"
        f"{PORTRAIT_TAIL}"
    )


def generate_portrait_url(card: CharacterCard, *, world_id: str = "") -> ImageGenerationResult:
    settings = get_settings()
    if not settings.enable_character_portraits:
        return ImageGenerationResult(error="角色立绘未启用（ENABLE_CHARACTER_PORTRAITS=false）")

    provider = settings.image_provider.lower()
    primary = build_portrait_prompt(card, world_id=world_id, safe_mode=False)
    fallback = build_portrait_prompt(card, world_id=world_id, safe_mode=True)
    return generate_with_policy_fallback(
        primary_prompt=primary,
        fallback_prompt=fallback,
        provider=provider,
        settings=settings,
        image_kind="portrait",
    )
