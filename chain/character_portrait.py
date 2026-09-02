"""角色立绘生成（复用场景图的 Seedream / DALL·E 通道）。"""

from config.settings import get_settings
from config.worlds import WORLD_OPTIONS
from chain.scene_image import ImageGenerationResult, _generate_openai_dalle, _generate_seedream
from game.profile import CharacterCard


def _world_label(world_id: str) -> str:
    if not world_id.strip():
        return "奇幻冒险"
    return WORLD_OPTIONS.get(world_id.strip(), world_id.strip())


def _appearance_hints(card: CharacterCard) -> str:
    parts: list[str] = []
    if card.equipment:
        worn = "、".join(entry.item_name for entry in card.equipment[:4])
        parts.append(f"可见装备：{worn}")
    if card.inventory:
        carried = "、".join(item.name for item in card.inventory[:4])
        parts.append(f"库中物品：{carried}")
    if card.career_summary.strip():
        parts.append(f"经历气质：{card.career_summary.strip()[:200]}")
    elif card.campaign_history:
        latest = card.campaign_history[-1]
        if latest.summary.strip():
            parts.append(f"近期经历：{latest.summary.strip()[:160]}")
    if card.notable_facts:
        parts.append(f"外貌或气质线索：{'；'.join(card.notable_facts[-3:])[:180]}")
    if card.deceased:
        parts.append("角色已阵亡：面容疲惫、战损或沉重气质，但仍保持人物辨识度。")
    return " ".join(parts)


def build_portrait_prompt(card: CharacterCard, *, world_id: str = "") -> str:
    world = _world_label(world_id or card.preferred_world_id)
    hints = _appearance_hints(card)
    hint_block = f" {hints}" if hints else ""
    appearance_block = card.appearance.format_for_prompt()
    appearance_text = f"外貌设定：{appearance_block}。" if appearance_block else ""
    return (
        f"跑团 TRPG 角色全身立绘，从头到脚完整呈现，自然站立或轻微动态姿势，"
        f"精致插画、电影级光影，单一主角居中，背景简洁不抢戏，无文字、无水印、无 UI 边框。"
        f"角色名：{card.name}。人物设定：{card.background.strip() or '一位冒险者'}。"
        f"{appearance_text}"
        f"世界观氛围：{world}。{hint_block}"
        f"严格遵循上述性别、年龄与种族/族裔设定；强调全身服装、装备、体态与气质，风格统一、辨识度高。"
    )


def generate_portrait_url(card: CharacterCard, *, world_id: str = "") -> ImageGenerationResult:
    settings = get_settings()
    if not settings.enable_character_portraits:
        return ImageGenerationResult(error="角色立绘未启用（ENABLE_CHARACTER_PORTRAITS=false）")

    prompt = build_portrait_prompt(card, world_id=world_id)
    provider = settings.image_provider.lower()
    if provider == "seedream":
        return _generate_seedream(prompt, settings)
    if provider == "openai":
        return _generate_openai_dalle(prompt, settings)
    return ImageGenerationResult(error=f"不支持的图片提供商：{settings.image_provider}")
