# src/config.py
import os
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    # Discord
    DISCORD_TOKEN: str = Field(default="", description="Discord Bot Token")
    COMMAND_PREFIXES: List[str] = Field(default=["!n ", "!n", "n! ", "n!"])
    CHOSEN_ONE_NAME: str = Field(default="Kishi-kun", description="Tên định danh người dùng đặc biệt / Hiệp sĩ")
    CREATOR_USER_ID: str = Field(default="483169533922639902", description="Discord ID của Người Tạo Ra Bot / Creator")
    MAX_BOND_USER_IDS: str = Field(
        default="864077473661845504",
        description="Comma-separated Discord IDs of users with maximum bond/affection (Cấp 6 tối đa)"
    )
    AUTO_REPLY_CHANNELS: str = Field(default="", description="Comma-separated channel IDs")

    # Custom Discord Emoji Source Server (https://discord.gg/BJTm5Zsjm)
    EMOJI_SOURCE_GUILD_ID: str = Field(
        default="413766882277982228",
        description="ID máy chủ Discord nguồn cung cấp custom emoji khi chat"
    )
    EMOJI_SOURCE_INVITE_URL: str = Field(
        default="https://discord.gg/BJTm5Zsjm",
        description="Link invite máy chủ Discord nguồn cung cấp custom emoji"
    )

    @property
    def max_bond_user_id_list(self) -> List[str]:
        return [uid.strip() for uid in self.MAX_BOND_USER_IDS.split(",") if uid.strip()]

    # Uncensored LLM (NoTrack AI / Venice AI / Local LLM - OpenAI-compatible)
    VENICE_API_KEY: str = Field(default="", description="API Key cho NoTrack AI hoặc Venice AI hoặc Local LLM")
    VENICE_DEFAULT_MODEL: str = Field(
        default="notrack-uncensored",
        description="Model mặc định cho Uncensored LLM (ví dụ: notrack-uncensored, default)"
    )
    VENICE_BASE_URL: str = Field(
        default="https://api.notrack.ai/v1",
        description="Base URL cho API không kiểm duyệt (mặc định https://api.notrack.ai/v1 hoặc https://api.venice.ai/api/v1 hoặc http://localhost:1235/v1)"
    )
    NOTRACK_API_KEY: str = Field(default="", description="NoTrack AI API Key (sk-notrack-...)")
    NOTRACK_DEFAULT_MODEL: str = Field(default="notrack-uncensored", description="Model NoTrack")
    NOTRACK_BASE_URL: str = Field(default="https://api.notrack.ai/v1", description="Base URL NoTrack")

    # AI Horde (Image Generation / Distributed Cluster)
    AI_HORDE_API_KEY: str = Field(default="", description="AI Horde API Key (https://aihorde.net/)")

    # Uncensored AI (Text Chat & Image Generation)
    UNCENSORED_API_KEY: str = Field(default="", description="Uncensored AI API Key (uai_sk_...)")
    UNCENSORED_BASE_URL: str = Field(
        default="https://api.uncensored.com/api/v1",
        description="Base URL cho Uncensored AI API (Chat & Images)"
    )
    UNCENSORED_CHAT_MODEL: str = Field(
        default="deepseek-v4-1-flash-uncensored",
        description="Model mặc định cho Uncensored AI Chat (ví dụ: deepseek-v4-1-flash-uncensored)"
    )
    UNCENSORED_IMAGE_BASE_URL: str = Field(
        default="https://api.uncensored.com/api/v1",
        description="Base URL cho Uncensored AI Images API"
    )
    UNCENSORED_IMAGE_MODEL: str = Field(
        default="seedream-v5",
        description="Model mặc định cho Uncensored AI Image Gen (ví dụ: seedream-v5)"
    )

    # NSFW mode (per-guild / per-channel được lưu runtime; flag global này bật/tắt toàn bộ tính năng)
    NSFW_ENABLED: bool = Field(default=False, description="Cho phép nội dung 18+ toàn cục (True/False)")
    NSFW_CHANNEL_IDS: str = Field(default="", description="Comma-separated channel IDs được phép NSFW")

    @property
    def nsfw_channel_id_list(self) -> List[int]:
        ids = []
        for raw in self.NSFW_CHANNEL_IDS.split(","):
            raw_s = raw.strip()
            if raw_s.isdigit():
                ids.append(int(raw_s))
        return ids

    # Groq & Fast LLM
    GROQ_API_KEY: str = Field(default="", description="Groq API Key")
    GROQ_MODEL: str = Field(default="qwen/qwen3.8-27b", description="Mô hình LLM Groq chính")
    GROQ_CODING_MODEL: str = Field(default="openai/gpt-oss-120b", description="Mô hình Groq ưu tiên khi đọc/viết code")
    GROQ_FALLBACK_MODELS: List[str] = Field(
        default=["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]
    )
    GROQ_TIMEOUT_SECONDS: float = Field(default=18.0)
    GROQ_MAX_RETRIES: int = Field(default=2)

    # Ultra-Fast Chat APIs (Free Tiers: Cerebras ~2200 tok/s, SambaNova ~1000 tok/s)
    CEREBRAS_API_KEY: str = Field(default="", description="Cerebras Cloud API Key (https://cloud.cerebras.ai - Free 1M tokens/day)")
    CEREBRAS_BASE_URL: str = Field(default="https://api.cerebras.ai/v1", description="Base URL cho Cerebras Inference")
    CEREBRAS_CHAT_MODEL: str = Field(default="qwen-3-32b", description="Model chat siêu tốc trên Cerebras")

    SAMBANOVA_API_KEY: str = Field(default="", description="SambaNova Cloud API Key (https://cloud.sambanova.ai - Free tier)")
    SAMBANOVA_BASE_URL: str = Field(default="https://api.sambanova.ai/v1", description="Base URL cho SambaNova Cloud")
    SAMBANOVA_CHAT_MODEL: str = Field(default="Meta-Llama-3.3-70B-Instruct", description="Model chat trên SambaNova")

    # Free Fast Coding APIs (Mistral Codestral Free Tier & OpenRouter Free Coder)
    CODESTRAL_API_KEY: str = Field(default="", description="Mistral Codestral Free API Key (https://console.mistral.ai)")
    CODESTRAL_BASE_URL: str = Field(default="https://codestral.mistral.ai/v1", description="Base URL cho Mistral Codestral")
    CODESTRAL_MODEL: str = Field(default="codestral-latest", description="Model chuyên đọc/viết code siêu nhanh Codestral")

    OPENROUTER_API_KEY: str = Field(default="", description="OpenRouter API Key (hỗ trợ model :free)")
    OPENROUTER_BASE_URL: str = Field(default="https://openrouter.ai/api/v1", description="Base URL OpenRouter")
    OPENROUTER_CODE_MODEL: str = Field(default="qwen/qwen3-coder:free", description="Model code miễn phí trên OpenRouter")

    # Gemini (Vision, Fast Chat Fallback & Nano Banana Image Generation)
    GEMINI_API_KEY: Optional[str] = Field(default=None)
    GEMINI_CHAT_MODEL: str = Field(
        default="gemini-3.5-flash-lite",
        description="Model Gemini Flash siêu nhanh dự phòng cho chat & đọc code"
    )
    GEMINI_IMAGE_MODEL: str = Field(
        default="gemini-2.5-flash-image",
        description="Model Google Gemini Nano Banana vẽ tranh thông thường (gemini-2.5-flash-image)"
    )

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/neneka_db",
        description="Async PostgreSQL connection string"
    )
    SQLITE_FALLBACK_URL: str = Field(
        default="sqlite+aiosqlite:///neneka.db",
        description="Fallback SQLite async database if PostgreSQL is not reachable"
    )
    DB_ECHO: bool = Field(default=False)

    # Redis Cache & Anti-Spam
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection string"
    )

    # Autonomous / Proactive Behavior
    # Modes: "MENTION" (Mode A), "AUTO_CHAT" (Mode B), "AUTONOMOUS" (Mode C)
    AUTONOMOUS_MODE: str = Field(default="AUTONOMOUS")
    CHANNEL_COOLDOWN_SECONDS: int = Field(default=3)
    USER_COOLDOWN_SECONDS: int = Field(default=2)
    PROACTIVE_MIN_INTERVAL_SECONDS: int = Field(default=120)

    # Memory Token Limit
    MAX_MEMORY_TOKENS: int = Field(default=1500)
    SHORT_TERM_MEMORY_LIMIT: int = Field(default=15)

    # Japanese Voice / TTS
    TTS_PROVIDER: str = Field(default="fishaudio", description="Provider for Japanese TTS: fishaudio, edge, or gpt_sovits")
    DEFAULT_JAPANESE_VOICE: str = Field(default="ja-JP-NanamiNeural")
    VOICE_PITCH_ADJUST: str = Field(default="-14Hz")
    VOICE_RATE_ADJUST: str = Field(default="-6%")

    # Fish Audio API
    FISH_AUDIO_API_KEY: str = Field(default="")
    FISH_AUDIO_MODEL_ID: str = Field(default="5b11a7f1653844048d44a5068859212a")

    # GPT-SoVITS (Dự phòng chạy local)
    SOVITS_API_URL: str = Field(default="http://127.0.0.1:9880")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def auto_reply_channel_ids(self) -> List[int]:
        ids = []
        for raw in self.AUTO_REPLY_CHANNELS.split(","):
            raw_s = raw.strip()
            if raw_s.isdigit():
                ids.append(int(raw_s))
        return ids

settings = Settings()
