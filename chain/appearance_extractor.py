from langchain_core.prompts import ChatPromptTemplate

from chain.json_utils import extract_json_dict
from chain.llm import create_chat_llm
from config.settings import PROMPTS_DIR
from config.worlds import WORLD_OPTIONS
from game.appearance import CharacterAppearance, parse_appearance_dict
from game.profile import CharacterCard
from prompts.templates import load_world_prompt


class AppearanceExtractor:
    def __init__(self):
        self.llm = create_chat_llm(role="suggestions", temperature=0.2)
        system_prompt = (PROMPTS_DIR / "appearance_extractor.txt").read_text(
            encoding="utf-8"
        )
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                (
                    "human",
                    "【世界观包】\n{world_label}\n\n"
                    "【世界观规则摘要】\n{world_rules}\n\n"
                    "【角色姓名】\n{name}\n\n"
                    "【角色背景】\n{background}\n\n"
                    "【玩家指定性别】\n{locked_gender}\n\n"
                    "【玩家指定年龄】\n{locked_age}\n\n"
                    "【战役气质/经历】\n{career_context}\n\n"
                    "【关键记忆】\n{notable_facts}\n\n"
                    "请输出外貌 JSON：",
                ),
            ]
        )

    def extract_for_card(
        self,
        card: CharacterCard,
        *,
        world_id: str = "",
    ) -> CharacterAppearance:
        world_id = (world_id or card.preferred_world_id or "").strip()
        world_label = WORLD_OPTIONS.get(world_id, world_id or "通用冒险")
        career_context = card.career_summary.strip()
        if not career_context and card.campaign_history:
            latest = card.campaign_history[-1]
            career_context = latest.summary.strip()
        notable = "\n".join(f"- {fact}" for fact in card.notable_facts[-5:] if fact.strip())
        locked_gender = (card.appearance.gender or "").strip() or "（未指定，可从背景推断）"
        locked_age = (card.appearance.age or "").strip() or "（未指定，可从背景推断）"
        chain = self.prompt | self.llm
        response = chain.invoke(
            {
                "world_label": world_label,
                "world_rules": load_world_prompt(world_id) if world_id else "（无额外规则）",
                "name": card.name.strip(),
                "background": card.background.strip() or "一位冒险者。",
                "locked_gender": locked_gender,
                "locked_age": locked_age,
                "career_context": career_context or "（尚无）",
                "notable_facts": notable or "（尚无）",
            }
        )
        data = extract_json_dict((response.content or "").strip())
        if not isinstance(data, dict):
            return CharacterAppearance()
        return parse_appearance_dict(data)
