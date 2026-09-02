import logging
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from chain.image_prompt_safety import (
    format_content_policy_hint,
    is_content_policy_error,
)
from config.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImageGenerationResult:
    url: str | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.url)


def _extract_http_error(response: httpx.Response) -> str:
    try:
        data = response.json()
        err = data.get("error") or {}
        if isinstance(err, dict):
            message = (err.get("message") or "").strip()
            code = (err.get("code") or "").strip()
            if message and code:
                return f"{code}: {message}"
            if message:
                return message
            if code:
                return code
    except Exception:
        pass
    text = (response.text or "").strip()
    if text:
        return text[:500]
    return f"HTTP {response.status_code}"


def _generate_seedream(prompt: str, settings) -> ImageGenerationResult:
    if not settings.seedream_api_key:
        return ImageGenerationResult(error="未配置 SEEDREAM_API_KEY")

    url = f"{settings.seedream_base_url.rstrip('/')}/images/generations"
    headers = {
        "Authorization": f"Bearer {settings.seedream_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.seedream_model,
        "prompt": prompt,
        "size": settings.seedream_size,
        "response_format": "url",
        "watermark": settings.seedream_watermark,
        "sequential_image_generation": "disabled",
    }

    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(url, headers=headers, json=payload)
            if response.is_error:
                error = _extract_http_error(response)
                logger.warning("Seedream 出图失败: %s", error)
                return ImageGenerationResult(error=error)
            data = response.json()
        items = data.get("data") or []
        if not items:
            return ImageGenerationResult(error="Seedream 返回空结果")
        image_url = items[0].get("url")
        if not image_url:
            return ImageGenerationResult(error="Seedream 响应缺少图片 URL")
        return ImageGenerationResult(url=image_url)
    except httpx.HTTPError as exc:
        logger.exception("Seedream 请求失败")
        return ImageGenerationResult(error=f"Seedream 网络错误：{exc}")
    except Exception as exc:
        logger.exception("Seedream 出图异常")
        return ImageGenerationResult(error=f"Seedream 出图异常：{exc}")


def _generate_openai_dalle(prompt: str, settings) -> ImageGenerationResult:
    if not settings.openai_api_key:
        return ImageGenerationResult(error="未配置 OPENAI_API_KEY")

    from openai import OpenAI

    client_kwargs: dict = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    client = OpenAI(**client_kwargs)

    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            n=1,
        )
        image_url = response.data[0].url
        if not image_url:
            return ImageGenerationResult(error="DALL·E 响应缺少图片 URL")
        return ImageGenerationResult(url=image_url)
    except Exception as exc:
        logger.exception("DALL·E 出图失败")
        return ImageGenerationResult(error=f"DALL·E 出图失败：{exc}")


def generate_with_policy_fallback(
    *,
    primary_prompt: str,
    fallback_prompt: str,
    provider: str,
    settings,
) -> ImageGenerationResult:
    generate: Callable[[str], ImageGenerationResult]
    if provider == "seedream":
        generate = lambda p: _generate_seedream(p, settings)
    elif provider == "openai":
        generate = lambda p: _generate_openai_dalle(p, settings)
    else:
        return ImageGenerationResult(error=f"不支持的图片提供商：{provider}")

    result = generate(primary_prompt)
    if result.ok or not is_content_policy_error(result.error):
        return result

    logger.info("图片 API 内容策略拦截，尝试合规简化提示词")
    retry = generate(fallback_prompt)
    if retry.ok:
        return retry

    error = retry.error or result.error
    return ImageGenerationResult(error=format_content_policy_hint(error or result.error))


def _build_prompt(scene_name: str, world: str, tone: str) -> str:
    from chain.image_prompt_safety import sanitize_image_text
    from chain.image_style import SCENE_STYLE, SCENE_TAIL

    mood = sanitize_image_text(tone or "神秘", max_len=32) or "神秘"
    place = sanitize_image_text(scene_name, max_len=80) or "当前场景"
    setting = sanitize_image_text(world, max_len=80) or "幻想世界"
    return (
        f"{SCENE_STYLE}"
        f"地点：{place}。世界设定：{setting}。基调：{mood}。"
        f"{SCENE_TAIL}"
    )


def generate_scene_image(scene_name: str, world: str, tone: str = "") -> ImageGenerationResult:
    """生成场景图，返回 URL 与错误信息。"""
    settings = get_settings()
    if not settings.enable_scene_images:
        return ImageGenerationResult(error="场景图生成未启用（ENABLE_SCENE_IMAGES=false）")

    from chain.image_prompt_safety import build_safe_scene_prompt

    prompt = _build_prompt(scene_name, world, tone)
    fallback = build_safe_scene_prompt(scene_name, world, tone)
    provider = settings.image_provider.lower()
    return generate_with_policy_fallback(
        primary_prompt=prompt,
        fallback_prompt=fallback,
        provider=provider,
        settings=settings,
    )
