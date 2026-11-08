# tests/test_discord_routing.py
import pytest
from src.autonomous.proactive_engine import proactive_engine

def test_discord_message_routing_modes():
    # 1. Reject Bot messages always
    should_reply_bot, _ = proactive_engine.should_reply(
        is_bot=True, is_dm=False, is_mentioned=True, is_reply_to_bot=True, channel_id=123, content="Hello"
    )
    assert not should_reply_bot

    # 2. Allow DMs
    should_reply_dm, _ = proactive_engine.should_reply(
        is_bot=False, is_dm=True, is_mentioned=False, is_reply_to_bot=False, channel_id=123, content="Hello DM"
    )
    assert should_reply_dm

    # 3. Mention Mode: only reply when mentioned or replied
    proactive_engine.set_mode("MENTION")
    should_unmentioned, _ = proactive_engine.should_reply(
        is_bot=False, is_dm=False, is_mentioned=False, is_reply_to_bot=False, channel_id=999, content="No mention"
    )
    assert not should_unmentioned

    should_mentioned, _ = proactive_engine.should_reply(
        is_bot=False, is_dm=False, is_mentioned=True, is_reply_to_bot=False, channel_id=999, content="@Neneka Hello"
    )
    assert should_mentioned

def test_voice_cog_prefix_commands():
    from src.cogs.voice import VoiceCog
    from src.bot import bot
    cog = VoiceCog(bot)
    commands_map = {cmd.name: cmd for cmd in cog.get_commands()}
    assert "speak" in commands_map
    assert "join" in commands_map
    assert "leave" in commands_map
    assert "radio" in commands_map
    assert "quote" in commands_map
    assert "s" in commands_map["speak"].aliases


