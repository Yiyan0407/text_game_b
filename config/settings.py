import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = PROJECT_ROOT / "prompts"
DATA_DIR = PROJECT_ROOT / "data"
SAVES_DIR = DATA_DIR / "saves"
PROFILES_DIR = DATA_DIR / "profiles"
SCENARIOS_DIR = DATA_DIR / "scenarios"
LOG_FILE = PROJECT_ROOT / "logs" / "game.log"


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    openai_model_lite: str
    openai_model_kp: str
    openai_base_url: str | None
    llm_temperature: float
    llm_thinking_enabled: bool
    max_history_messages: int
    summary_interval: int
    chapter_interval: int
    max_story_summary_chars: int
    max_memory_facts: int
    max_chapters_kept: int
    memory_journal_compress_at: int
    memory_journal_max_chars: int
    enable_streaming: bool
    enable_action_suggestions: bool
    enable_scene_map: bool
    enable_scene_images: bool
    image_provider: str
    seedream_api_key: str
    seedream_base_url: str
    seedream_model: str
    seedream_size: str
    seedream_watermark: bool
    app_password: str
    log_level: str
    llm_retry_enabled: bool
    llm_max_retries: int
    llm_retry_initial_delay: float
    llm_retry_max_delay: float
    llm_retry_backoff_factor: float


@lru_cache
def get_settings() -> Settings:
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
    openai_model = os.getenv("OPENAI_MODEL", "mimo-v2.5-pro")
    openai_model_lite = os.getenv("OPENAI_MODEL_LITE", "").strip() or "mimo-v2.5"
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=openai_model,
        openai_model_lite=openai_model_lite,
        openai_model_kp=os.getenv("OPENAI_MODEL_KP", "").strip() or openai_model,
        openai_base_url=base_url,
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.8")),
        llm_thinking_enabled=os.getenv("LLM_THINKING_ENABLED", "false").lower() == "true",
        max_history_messages=int(os.getenv("MAX_HISTORY_MESSAGES", "40")),
        summary_interval=int(os.getenv("SUMMARY_INTERVAL", "6")),
        chapter_interval=int(os.getenv("CHAPTER_INTERVAL", "24")),
        max_story_summary_chars=int(os.getenv("MAX_STORY_SUMMARY_CHARS", "1500")),
        max_memory_facts=int(os.getenv("MAX_MEMORY_FACTS", "50")),
        max_chapters_kept=int(os.getenv("MAX_CHAPTERS_KEPT", "8")),
        memory_journal_compress_at=int(os.getenv("MEMORY_JOURNAL_COMPRESS_AT", "40")),
        memory_journal_max_chars=int(os.getenv("MEMORY_JOURNAL_MAX_CHARS", "6000")),
        enable_streaming=os.getenv("ENABLE_STREAMING", "true").lower() == "true",
        enable_action_suggestions=os.getenv("ENABLE_ACTION_SUGGESTIONS", "true").lower() == "true",
        enable_scene_map=os.getenv("ENABLE_SCENE_MAP", "true").lower() == "true",
        enable_scene_images=os.getenv("ENABLE_SCENE_IMAGES", "false").lower() == "true",
        image_provider=os.getenv("IMAGE_PROVIDER", "seedream"),
        seedream_api_key=os.getenv("SEEDREAM_API_KEY", ""),
        seedream_base_url=os.getenv(
            "SEEDREAM_BASE_URL",
            "https://ark.cn-beijing.volces.com/api/v3",
        ),
        seedream_model=os.getenv("SEEDREAM_MODEL", "doubao-seedream-4-5-251128"),
        seedream_size=os.getenv("SEEDREAM_SIZE", "2K"),
        seedream_watermark=os.getenv("SEEDREAM_WATERMARK", "false").lower() == "true",
        app_password=os.getenv("APP_PASSWORD", "1123"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        llm_retry_enabled=os.getenv("LLM_RETRY_ENABLED", "true").lower() == "true",
        llm_max_retries=max(1, int(os.getenv("LLM_MAX_RETRIES", "3"))),
        llm_retry_initial_delay=float(os.getenv("LLM_RETRY_INITIAL_DELAY", "1.0")),
        llm_retry_max_delay=float(os.getenv("LLM_RETRY_MAX_DELAY", "60.0")),
        llm_retry_backoff_factor=float(os.getenv("LLM_RETRY_BACKOFF_FACTOR", "2.0")),
    )
