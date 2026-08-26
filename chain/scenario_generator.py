import json
import re
import uuid
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from chain.llm import create_chat_llm
from config.settings import get_settings
from config.worlds import WORLD_OPTIONS
from game.scenario import Scenario


class ScenarioGenerationError(ValueError):
    pass


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text.lower())
    cleaned = re.sub(r"[\s_-]+", "_", cleaned).strip("_")
    return cleaned[:24] or "adventure"


def _extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ScenarioGenerationError("AI 未返回有效 JSON") from None
        return json.loads(match.group())


def _normalize_scenario_data(data: dict, world_id: str) -> dict:
    data = dict(data)
    title = str(data.get("title") or "自定义冒险")
    data["id"] = data.get("id") or f"gen_{_slugify(title)}_{uuid.uuid4().hex[:6]}"
    data["world_id"] = data.get("world_id") or world_id
    if not data.get("opening_scene_id"):
        data["opening_scene_id"] = "start"
    if not data.get("opening_scene_name"):
        data["opening_scene_name"] = "起点"
    return data


class ScenarioGenerator:
    def __init__(self):
        self.llm = create_chat_llm(temperature=0.9)

    def generate_from_theme(
        self,
        world_id: str,
        theme_hint: str = "",
        mode: Literal["full", "world"] = "full",
    ) -> Scenario:
        world_label = WORLD_OPTIONS.get(world_id, world_id)
        hint = theme_hint if theme_hint and theme_hint != "完全随机" else "请自由发挥，给一个有趣且具体的创意"
        user_prompt = (
            f"世界观规则包：{world_label}（world_id={world_id}）\n"
            f"主题方向：{hint}\n"
            f"生成模式：{'完整剧本' if mode == 'full' else '仅世界观设定'}"
        )
        return self._generate(user_prompt, world_id, mode)

    def generate_from_description(
        self,
        description: str,
        world_id: str | None = None,
        mode: Literal["full", "world"] = "full",
    ) -> Scenario:
        if world_id:
            world_label = WORLD_OPTIONS.get(world_id, world_id)
            world_part = f"优先使用世界观规则包：{world_label}（world_id={world_id}）\n"
        else:
            world_part = "请根据描述自行选择最合适的 world_id（modern/cyberpunk/xianxia/fantasy）。\n"
        user_prompt = (
            f"{world_part}"
            f"用户描述：{description.strip()}\n"
            f"生成模式：{'完整剧本' if mode == 'full' else '仅世界观设定'}"
        )
        return self._generate(user_prompt, world_id or "modern", mode)

    def _generate(
        self,
        user_prompt: str,
        world_id: str,
        mode: Literal["full", "world"],
    ) -> Scenario:
        schema_hint = self._schema_hint(mode)
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", self._system_prompt(mode)),
                ("human", "{input}\n\n{schema}"),
            ]
        )
        chain = prompt | self.llm
        response = chain.invoke({"input": user_prompt, "schema": schema_hint})
        raw = _extract_json(response.content or "")
        raw = _normalize_scenario_data(raw, world_id)
        try:
            scenario = Scenario.model_validate(raw)
        except ValidationError as exc:
            raise ScenarioGenerationError(f"剧本结构无效：{exc}") from exc
        if mode == "world" and not scenario.opening_prompt:
            scenario.opening_prompt = (
                scenario.custom_world_overlay or scenario.description or "自由探索这个世界。"
            )
        return scenario

    @staticmethod
    def _system_prompt(mode: Literal["full", "world"]) -> str:
        base = (
            "你是跑团模组编剧。根据用户要求生成中文跑团模组，输出**单个 JSON 对象**，不要 markdown 代码块。"
            "id 用英文 slug；内容要有画面感、可玩性，适合文字跑团。"
            "world_id 只能是：modern, cyberpunk, xianxia, fantasy 之一。"
        )
        if mode == "world":
            return (
                base
                + "本次仅生成世界观：title/description/world/tone/world_id/custom_world_overlay/opening_prompt 要详细；"
                "initial_quests 给 1 个开放式任务；key_nodes 2-3 个；endings 1-2 个即可。"
            )
        return (
            base
            + "生成完整剧本：含 initial_quests(1个)、key_nodes(3-4个)、endings(2-3个)；"
            "opening_prompt 写清开场情境与委托/动机。"
        )

    @staticmethod
    def _schema_hint(mode: Literal["full", "world"]) -> str:
        base = (
            "JSON 字段：id, title, description, world_id, world, tone, "
            "opening_scene_id, opening_scene_name, opening_prompt, custom_world_overlay, "
            "initial_quests[{id,title,status,description}], "
            "key_nodes[{id,title,description}], endings[{id,title,condition}]"
        )
        if mode == "world":
            return base + "。custom_world_overlay 写 150-300 字世界观细节。"
        return base
