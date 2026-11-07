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

