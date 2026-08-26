import httpx

from config.settings import get_settings


def _build_prompt(scene_name: str, world: str, tone: str) -> str:
    mood = tone or "神秘"
    return (
        f"跑团 TRPG 场景氛围插画，电影级光影，广角或中景，无文字、无水印。"
        f"地点：{scene_name}。世界观：{world}。基调：{mood}。"
        f"不要出现清晰可辨的真实人物正脸，强调环境细节与沉浸感。"
    )


def generate_scene_image(scene_name: str, world: str, tone: str = "") -> str | None:
    """生成场景图，返回图片 URL。默认使用字节 Seedream（火山方舟）。"""
    settings = get_settings()
    if not settings.enable_scene_images:
        return None

    prompt = _build_prompt(scene_name, world, tone)
    provider = settings.image_provider.lower()

    if provider == "seedream":
        return _generate_seedream(prompt, settings)
    if provider == "openai":
        return _generate_openai_dalle(prompt, settings)
    return None


def _generate_seedream(prompt: str, settings) -> str | None:
    if not settings.seedream_api_key:
        return None

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
            response.raise_for_status()
            data = response.json()
        items = data.get("data") or []
        if not items:
            return None
        return items[0].get("url")
    except Exception:
        return None


def _generate_openai_dalle(prompt: str, settings) -> str | None:
    if not settings.openai_api_key:
        return None

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
        return response.data[0].url
    except Exception:
        return None
