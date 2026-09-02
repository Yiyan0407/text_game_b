"""角色立绘：下载、落盘与 ProfileManager 集成。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

from chain.character_portrait import generate_portrait_url
from game.profile import CharacterCard, ProfileManager

logger = logging.getLogger(__name__)

PORTRAIT_FILENAME = "portrait.png"


@dataclass(frozen=True)
class PortraitSaveResult:
    card: CharacterCard
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def portrait_enabled() -> bool:
    from config.settings import get_settings

    settings = get_settings()
    if not settings.enable_character_portraits:
        return False
    provider = settings.image_provider.lower()
    if provider == "seedream":
        return bool(settings.seedream_api_key)
    if provider == "openai":
        return bool(settings.openai_api_key)
    return False


def _download_image(url: str) -> tuple[bytes | None, str]:
    try:
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            response = client.get(url)
            if response.is_error:
                return None, f"下载立绘失败：HTTP {response.status_code}"
            content_type = response.headers.get("content-type", "")
            if content_type and not content_type.startswith("image/"):
                return None, f"下载立绘失败：响应不是图片（{content_type}）"
            data = response.content
            if not data:
                return None, "下载立绘失败：空文件"
            return data, ""
    except httpx.HTTPError as exc:
        logger.exception("下载角色立绘失败")
        return None, f"下载立绘网络错误：{exc}"
    except Exception as exc:
        logger.exception("下载角色立绘失败")
        return None, f"下载立绘异常：{exc}"


def generate_and_save_portrait(
    manager: ProfileManager,
    profile_id: str,
    card: CharacterCard,
    *,
    world_id: str = "",
    refresh_appearance: bool = True,
) -> PortraitSaveResult:
    """尝试生成并保存立绘；失败时返回原因。"""
    active_world = world_id or card.preferred_world_id
    if refresh_appearance:
        try:
            from chain.appearance_extractor import AppearanceExtractor
            from game.appearance import merge_appearance

            manual = card.appearance.model_copy()
            inferred = AppearanceExtractor().extract_for_card(
                card,
                world_id=active_world,
            )
            card.appearance = merge_appearance(manual, inferred)
            manager.save_character_card(profile_id, card)
        except Exception:
            logger.exception("外貌档案推断失败，将仅使用背景文本")

    gen = generate_portrait_url(card, world_id=active_world)
    if not gen.ok:
        return PortraitSaveResult(
            card=card,
            error=_portrait_failure_hint(gen.error or "出图 API 无响应"),
        )

    image_bytes, download_error = _download_image(gen.url or "")
    if not image_bytes:
        return PortraitSaveResult(card=card, error=download_error or "下载立绘失败")

    saved = manager.save_portrait(profile_id, card, image_bytes)
    return PortraitSaveResult(card=saved, error="")


def _portrait_failure_hint(error: str) -> str:
    from chain.image_prompt_safety import format_image_generation_error

    lowered = error.lower()
    formatted = format_image_generation_error(error)
    if formatted != error:
        return formatted
    if "modelnotopen" in lowered or "not activated" in lowered:
        return (
            f"{error}\n\n"
            "请在火山方舟控制台开通 Seedream 模型，或将 .env 中 SEEDREAM_MODEL "
            "改为你账号下已开通的推理接入点 ID（ep-xxx）。"
        )
    return error


def resolve_portrait_path(
    manager: ProfileManager,
    profile_id: str,
    card: CharacterCard,
) -> Path | None:
    path = manager.portrait_file_path(profile_id, card)
    if path is None or not path.exists():
        return None
    return path
