"""KP 叙事输出清理：移除 API 审核/错误文案，避免混入玩家可见故事。"""

from __future__ import annotations

import re

_API_LINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"high\s*risk", re.I),
    re.compile(r"content\s*(policy|filter|moderation|review)", re.I),
    re.compile(r"moderation", re.I),
    re.compile(r"审核(?:未|不)?通过"),
    re.compile(r"内容(?:违规|不合规|敏感)"),
    re.compile(r"无法(?:生成|提供|继续).{0,20}(?:内容|回复|叙事)"),
    re.compile(r"request\s+rejected", re.I),
    re.compile(r"safety\s+filter", re.I),
)

_PURE_API_ERROR_MARKERS = (
    "high risk",
    "content policy",
    "content moderation",
    "审核未通过",
    "审核不通过",
    "request rejected",
)

_FALLBACK = "（本轮叙事暂时无法生成，请稍后用不同表述重试。）"


def _line_is_artifact(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return any(pattern.search(stripped) for pattern in _API_LINE_PATTERNS)


def _looks_like_pure_api_error(text: str) -> bool:
    lowered = text.strip().lower()
    if len(lowered) > 280:
        return False
    if not any(marker in lowered for marker in _PURE_API_ERROR_MARKERS):
        return False
    non_artifact = [
        line
        for line in text.splitlines()
        if line.strip() and not _line_is_artifact(line)
    ]
    if non_artifact and len("".join(non_artifact).strip()) >= 8:
        return False
    return True


def sanitize_kp_narrative(text: str) -> str:
    """过滤 API 审核/错误残留；若整段不可用则返回简短占位说明。"""
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned
    if _looks_like_pure_api_error(cleaned):
        return _FALLBACK

    lines = cleaned.splitlines()
    kept = [line for line in lines if not _line_is_artifact(line)]
    if not kept:
        return _FALLBACK

    result = "\n".join(kept).strip()
    for pattern in _API_LINE_PATTERNS:
        result = pattern.sub("", result).strip()
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    return result or _FALLBACK
