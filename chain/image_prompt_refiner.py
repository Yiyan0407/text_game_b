"""图片 prompt LLM 矫正：在 API 内容策略拦截后自动改写并重试。"""

from __future__ import annotations

import logging

from langchain_core.prompts import ChatPromptTemplate

from chain.image_prompt_safety import sanitize_image_text
from chain.llm import create_chat_llm
from config.settings import PROMPTS_DIR

logger = logging.getLogger(__name__)

_KIND_LABELS = {
    "portrait": "角色立绘（写实全身肖像）",
    "scene": "场景氛围图（写实摄影）",
}


class ImagePromptRefiner:
    def __init__(self):
        self.llm = create_chat_llm(role="suggestions", temperature=0.2)
        system_prompt = (PROMPTS_DIR / "image_prompt_refiner.txt").read_text(
            encoding="utf-8"
        )
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                (
                    "human",
                    "【图片类型】\n{image_kind}\n\n"
                    "【API 拦截原因】\n{error}\n\n"
                    "【待矫正 prompt】\n{prompt}\n\n"
                    "请输出矫正后的 prompt：",
                ),
            ]
        )

    def refine(self, prompt: str, *, error: str, image_kind: str = "image") -> str:
        source = (prompt or "").strip()
        if not source:
            return ""
        label = _KIND_LABELS.get(image_kind, "游戏插画")
        try:
            chain = self.prompt | self.llm
            response = chain.invoke(
                {
                    "image_kind": label,
                    "error": (error or "内容策略拦截").strip()[:500],
                    "prompt": source[:1200],
                }
            )
            refined = (response.content or "").strip()
            if refined.startswith("```"):
                refined = refined.strip("`").strip()
                if refined.lower().startswith("text"):
                    refined = refined[4:].strip()
            refined = sanitize_image_text(refined, max_len=480)
            if len(refined) >= 40:
                return refined
        except Exception:
            logger.exception("LLM 矫正图片 prompt 失败")
        return sanitize_image_text(source, max_len=480)
