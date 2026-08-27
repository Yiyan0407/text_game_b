from langchain_core.prompts import ChatPromptTemplate

from chain.json_utils import extract_json_dict
from chain.llm import create_chat_llm
from config.settings import PROMPTS_DIR
from game.background_validator import BackgroundValidationResult, validate_background_quick
from game.scenario import Scenario
from prompts.templates import load_world_prompt


class BackgroundValidator:
    def __init__(self):
        self.llm = create_chat_llm(temperature=0.1)
        system_prompt = (PROMPTS_DIR / "background_validator.txt").read_text(encoding="utf-8")
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                (
                    "human",
                    "【世界观规则】\n{world_rules}\n\n"
                    "【世界观包】\n{world_id}\n\n"
                    "【玩家提交的背景】\n{background}\n\n"
                    "请输出审核 JSON：",
                ),
            ]
        )

    def evaluate(
        self,
        background: str,
        *,
        world_id: str,
        scenario: Scenario | None = None,
    ) -> BackgroundValidationResult:
        text = background.strip()
        if not text:
            return BackgroundValidationResult(approved=True)

        quick = validate_background_quick(text, world_id=world_id)
        if not quick.approved:
            return quick

        chain = self.prompt | self.llm
        response = chain.invoke(
            {
                "world_rules": load_world_prompt(world_id),
                "world_id": world_id,
                "background": text,
            }
        )
        return self._parse_response((response.content or "").strip())

    @staticmethod
    def _parse_response(text: str) -> BackgroundValidationResult:
        data = extract_json_dict(text)
        if isinstance(data, dict):
            approved = bool(data.get("approved", False))
            reason = str(data.get("rejection_reason", "")).strip()
            if not approved and not reason:
                reason = "背景设定过于超模或与世界观不符，请改写为普通冒险者起点。"
            return BackgroundValidationResult(approved=approved, rejection_reason=reason)
        return BackgroundValidationResult(
            approved=False,
            rejection_reason="背景审核解析失败，请稍微改写后再试。",
        )
