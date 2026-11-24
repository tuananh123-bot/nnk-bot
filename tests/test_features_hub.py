# tests/test_features_hub.py
import pytest
from unittest.mock import MagicMock

from src.utils.features_hub import (
    is_asking_whats_new,
    build_spoken_whats_new_reply,
    build_updates_embed,
    build_help_embed,
    NENEKA_BOT_CAPABILITIES_PROMPT,
)
from src.personality.engine import PersonalityEngine
from src.cogs.chat import ChatCog
from src.cogs.admin import AdminCog


def test_updates_embed_contains_all_new_features():
    embed = build_updates_embed()
    full_text = embed.title + " " + (embed.description or "") + " " + " ".join(
        f"{f.name} {f.value}" for f in embed.fields
    )
    assert "Piano" in full_text
    assert "/notes" in full_text
    assert "/code" in full_text
    assert "GIF" in full_text
    assert "1169588792064217159" in full_text
    assert "Nano Banana" in full_text


def test_categorized_help_embeds():
    for cat in ("all", "new", "music", "code_media", "character", "system"):
        emb = build_help_embed(cat)
        assert emb.title is not None
        assert len(emb.fields) >= 1


def test_neneka_system_prompt_has_self_awareness_of_capabilities():
    engine = PersonalityEngine()
    prompt = engine.get_system_prompt("vi", "Kishi-kun")
    assert NENEKA_BOT_CAPABILITIES_PROMPT in prompt
    assert "/piano" in prompt
    assert "/notes" in prompt
    assert "/code" in prompt


def test_updates_help_and_reload_commands_registered():
    bot = MagicMock()
    chat_cog = ChatCog(bot)
    admin_cog = AdminCog(bot)

    chat_cmds = {c.name for c in chat_cog.get_commands()}
    admin_cmds = {c.name for c in admin_cog.get_commands()}

    assert "updates" in chat_cmds
    assert "help" in chat_cmds
    assert "reload" in admin_cmds


def test_is_asking_whats_new_slang_and_spoken_reply():
    positive_queries = [
        "nay có j mới ko em",
        "ê có gì mới thế",
        "bot mới update j vậy",
        "em vừa cập nhật gì đó",
        "co j moi khong",
        "có tính năng gì mới",
        "what's new",
    ]
    for q in positive_queries:
        assert is_asking_whats_new(q) is True, f"Should match: {q}"

    assert is_asking_whats_new("hôm nay ăn cơm chưa") is False

    spoken = build_spoken_whats_new_reply()
    assert "Piano" in spoken
    assert "Code" in spoken
    assert "GIF" in spoken
