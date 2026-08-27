from langchain_core.prompts import ChatPromptTemplate

from chain.json_utils import extract_json_list
from chain.llm import create_chat_llm


class ActionSuggester:
    def __init__(self):
        self.llm = create_chat_llm(temperature=0.7)
        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是跑团行动建议生成器。根据 KP 最新叙事，为玩家生成 3 个简短可行的行动建议。"
                    "每个建议 8–20 字，动词开头，贴合当前场景，不要剧透。"
                    "只输出 JSON 数组，如：[\"调查吧台\",\"询问酒保\",\"观察门口\"]"
                    "{guidance}",
                ),
                (
                    "human",
                    "场景：{scene}\n\n"
                    "模式：{mode_label}\n"
                    "存活敌人：{enemies}\n\n"
                    "KP 叙事：\n{narrative}\n\n"
                    "补充要求：{guidance}\n\n"
                    "请输出 3 个行动建议 JSON 数组：",
                ),
            ]
        )

    def suggest(
        self,
        scene: str,
        narrative: str,
        turn_count: int = 0,
        *,
        in_combat: bool = False,
        enemy_names: list[str] | None = None,
    ) -> list[str]:
        if in_combat:
            enemies = enemy_names or []
            if enemies:
                target = enemies[0]
                return [
                    f"攻击{target}",
                    f"推撞{target}",
                    "结束回合",
                ][:3]
            return ["举盾防御", "观察弱点", "结束回合"]

        guidance = ""
        if turn_count <= 3:
            guidance = (
                "玩家处于开局阶段，建议应具体、易上手、动词开头，"
                "帮助玩家知道第一句话可以做什么；避免抽象或需要前置知识的选项。"
            )
        chain = self.prompt | self.llm
        response = chain.invoke(
            {
                "scene": scene,
                "mode_label": "战斗" if in_combat else "探索",
                "enemies": "、".join(enemy_names) if enemy_names else "无",
                "narrative": narrative,
                "guidance": guidance or "无特殊要求。",
            }
        )
        text = (response.content or "").strip()
        parsed = self._parse_suggestions(text)
        if parsed:
            return parsed
        if turn_count <= 1:
            return ActionSuggester._fallback_opening_suggestions(scene)
        return []

    @staticmethod
    def _parse_suggestions(text: str) -> list[str]:
        items = extract_json_list(text)
        if isinstance(items, list):
            return [str(item).strip() for item in items[:3] if str(item).strip()]
        lines = [line.strip("-•* ").strip() for line in text.splitlines() if line.strip()]
        return lines[:3]

    async def asuggest(
        self,
        scene: str,
        narrative: str,
        turn_count: int = 0,
        *,
        in_combat: bool = False,
        enemy_names: list[str] | None = None,
    ) -> list[str]:
        return self.suggest(
            scene,
            narrative,
            turn_count=turn_count,
            in_combat=in_combat,
            enemy_names=enemy_names,
        )

    @staticmethod
    def _fallback_opening_suggestions(scene: str) -> list[str]:
        label = scene or "周围"
        return [
            f"观察{label}",
            "和在场的人交谈",
            "检查随身物品",
        ]
