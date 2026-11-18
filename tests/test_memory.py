# tests/test_memory.py
import uuid
import pytest
import pytest_asyncio
from src.database.connection import db_manager
from src.memory.engine import MemoryEngine

@pytest.mark.asyncio
async def test_user_memory_isolation():
    await db_manager.initialize()
    engine = MemoryEngine()

    user_a = f"user_alpha_{uuid.uuid4().hex[:8]}"
    user_b = f"user_beta_{uuid.uuid4().hex[:8]}"

    # User A records a secret hobby
    await engine.record_exchange(
        discord_user_id=user_a,
        username="Alpha",
        channel_id="ch_1",
        user_message="Tôi thích sưu tầm mô hình robot Astraea",
        bot_response="Fufu... Thú vị đấy."
    )

    # User B records a different hobby
    await engine.record_exchange(
        discord_user_id=user_b,
        username="Beta",
        channel_id="ch_1",
        user_message="Tôi thích nấu ăn cho Pecorine",
        bot_response="Fufu... Tay nghề thế nào?"
    )

    # Test retrieval isolation
    ctx_a = await engine.get_memory_context(user_a, "robot")
    ctx_b = await engine.get_memory_context(user_b, "robot")

    # Alpha's facts must NOT appear in Beta's context
    assert any("robot" in f for f in ctx_a["relevant_facts"])
    assert not any("robot" in f for f in ctx_b["relevant_facts"])

    await db_manager.close()

@pytest.mark.asyncio
async def test_long_term_memory_retrieval_and_forget():
    await db_manager.initialize()
    engine = MemoryEngine()
    uid = f"test_user_privacy_{uuid.uuid4().hex[:8]}"

    await engine.record_exchange(
        discord_user_id=uid,
        username="PrivacyUser",
        channel_id="ch_priv",
        user_message="Sở thích của tôi là chơi cờ ma thuật",
        bot_response="Ta cũng rất thích cờ ma thuật."
    )

    mems = await engine.get_user_memories(uid)
    assert len(mems) >= 1

    # Test delete
    deleted = await engine.delete_user_memory(uid)
    assert deleted >= 1

    mems_after = await engine.get_user_memories(uid)
    assert len(mems_after) == 0

    await db_manager.close()

def test_parse_timeframe():
    from src.cogs.memory import parse_timeframe_to_minutes
    assert parse_timeframe_to_minutes("30m") == 30
    assert parse_timeframe_to_minutes("30p") == 30
    assert parse_timeframe_to_minutes("30 phút") == 30
    assert parse_timeframe_to_minutes("1h") == 60
    assert parse_timeframe_to_minutes("1 tiếng") == 60
    assert parse_timeframe_to_minutes("all") == -1
    assert parse_timeframe_to_minutes(None) == 30

@pytest.mark.asyncio
async def test_forget_recent_messages_30m():
    await db_manager.initialize()
    engine = MemoryEngine()
    uid = f"test_user_forget_{uuid.uuid4().hex[:8]}"

    await engine.record_exchange(
        discord_user_id=uid,
        username="ForgetUser",
        channel_id="ch_forget",
        user_message="Một tin nhắn bí mật vừa gửi 5 phút trước",
        bot_response="Ta đã ghi nhớ cuộc trò chuyện này."
    )

    ctx_before = await engine.get_memory_context(uid, current_query="tin nhắn")
    assert len(ctx_before["recent_history"]) >= 1

    # Forget recent messages within 30 minutes
    res = await engine.forget_recent_messages(uid, minutes=30)
    assert res["total"] >= 2
    assert res["short_term"] >= 1
    assert res["messages"] >= 2

    # Verify context history is now wiped
    ctx_after = await engine.get_memory_context(uid, current_query="tin nhắn")
    assert len(ctx_after["recent_history"]) == 0

    await db_manager.close()

