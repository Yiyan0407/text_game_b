"""将 LLM 异常转为玩家可读的简短说明。"""

from __future__ import annotations

from config.settings import get_settings


def format_llm_user_error(exc: BaseException) -> str:
    msg = str(exc).strip() or type(exc).__name__
    lower = msg.lower()
    name = type(exc).__name__.lower()

    if "connection error" in lower or "connect" in name or "connectionerror" in name:
        settings = get_settings()
        endpoint = settings.openai_base_url or "https://api.openai.com/v1（官方）"
        return (
            "无法连接 LLM 服务（网络或 API 地址问题）。\n\n"
            f"当前端点：{endpoint}\n"
            f"模型：{settings.openai_model}\n\n"
            "请检查：\n"
            "1. 本机网络、代理/VPN 是否拦截 HTTPS\n"
            "2. `.env` 中 `OPENAI_API_KEY` 是否有效、未过期\n"
            "3. MiMo 密钥与端点是否匹配：\n"
            "   · `sk-` 开头 → `OPENAI_BASE_URL=https://api.xiaomimimo.com/v1`\n"
            "   · `tp-` 开头 → `OPENAI_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1`\n"
            "4. 稍后重试；若仅开场失败，可暂时设 `ENABLE_STREAMING=false` 再开新局"
        )

    if "401" in msg or "authentication" in lower or "invalid api key" in lower:
        return "API 密钥无效或未配置。请检查 `.env` 中的 `OPENAI_API_KEY`。"

    if "429" in msg or "rate limit" in lower:
        return "API 请求过于频繁或额度不足。请稍后再试，或检查 MiMo 控制台余额。"

    if "timeout" in lower or "timed out" in lower:
        return f"请求超时：{msg}\n\n请检查网络或稍后重试。"

    return msg
