# tests/test_vision.py
import io
import pytest
from PIL import Image

from src.llm.vision_client import vision_client
from src.autonomous.proactive_engine import proactive_engine

def test_vision_client_availability():
    assert vision_client.is_available is True
    assert len(vision_client.models) >= 1


@pytest.mark.asyncio
async def test_vision_client_analyze_image():
    # Tạo ảnh màu xanh dương 60x60
    img = Image.new("RGB", (60, 60), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    result = await vision_client.analyze_image(
        image_bytes=img_bytes,
        mime_type="image/png",
        user_prompt="Bức ảnh này chủ yếu là màu gì? Trả lời thật ngắn gọn.",
        system_instruction="Ngươi là Neneka. Trả lời súc tích, thanh lịch."
    )

    assert result is not None
    assert len(result) > 0
    assert any(k in result.lower() for k in ["xanh", "blue", "lam"])


def test_proactive_engine_should_reply_with_attachment():
    # Nội dung rỗng nhưng có file đính kèm trong DM hoặc khi mention
    should_dm, _ = proactive_engine.should_reply(
        is_bot=False,
        is_dm=True,
        is_mentioned=False,
        is_reply_to_bot=False,
        channel_id=123,
        content="",
        has_attachments=True
    )
    assert should_dm is True

    should_mention, _ = proactive_engine.should_reply(
        is_bot=False,
        is_dm=False,
        is_mentioned=True,
        is_reply_to_bot=False,
        channel_id=123,
        content="",
        has_attachments=True
    )
    assert should_mention is True
