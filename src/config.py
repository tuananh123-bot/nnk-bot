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

    @property
    def max_bond_user_id_list(self) -> List[str]:
        return [uid.strip() for uid in self.MAX_BOND_USER_IDS.split(",") if uid.strip()]

    # Groq & LLM
    GROQ_API_KEY: str = Field(default="", description="Groq API Key")
    GROQ_MODEL: str = Field(default="qwen/qwen3.8-27b", description="Mô hình LLM Groq")
    GROQ_FALLBACK_MODELS: List[str] = Field(
        default=["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]
    )
    GROQ_TIMEOUT_SECONDS: float = Field(default=30.0)
    GROQ_MAX_RETRIES: int = Field(default=3)

    # Gemini (Secondary / Voice design backup)
    GEMINI_API_KEY: Optional[str] = Field(default=None)

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

