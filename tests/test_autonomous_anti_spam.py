# tests/test_autonomous_anti_spam.py
import pytest
from src.autonomous.proactive_engine import proactive_engine

@pytest.mark.asyncio
async def test_anti_spam_rate_limits():
    channel_id = 88888
    user_id = 77777

    # First call: should be allowed
    ok1, _ = await proactive_engine.check_rate_limit(channel_id, user_id)
    assert ok1

    # Immediate second call: should be rate-limited by user/channel cooldown
    ok2, reason = await proactive_engine.check_rate_limit(channel_id, user_id)
    assert not ok2
    assert "cooldown active" in reason

def test_duplicate_response_prevention():
    channel_id = 55555
    sentence = "Fufu... Cậu nhóc lại làm phiền ta rồi."
    proactive_engine.record_last_response(channel_id, sentence)

    assert proactive_engine.is_duplicate_response(channel_id, sentence)
    assert not proactive_engine.is_duplicate_response(channel_id, "Câu hoàn toàn khác.")
