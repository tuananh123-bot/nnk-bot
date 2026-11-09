# tests/test_vietnam_context.py
import pytest
from datetime import datetime, timezone, timedelta
from src.utils.vietnam_context import (
    get_vietnam_time_info,
    detect_city_from_query,
    get_vietnam_weather_info,
    get_vietnam_context_for_prompt,
    WMO_WEATHER_CODES,
    DAYS_OF_WEEK_VN
)

def test_vietnam_time_info():
    info = get_vietnam_time_info()
    assert "time_str" in info
    assert "date_str" in info
    assert "day_of_week" in info
    assert "period" in info
    assert "greeting" in info
    assert "care_tip" in info
    assert "formatted_summary" in info

    # Kiểm tra múi giờ UTC+7
    now = info["now"]
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(hours=7)

    # Kiểm tra định dạng giờ:phút
    assert len(info["time_str"]) == 5
    assert ":" in info["time_str"]

    # Kiểm tra thứ trong tuần hợp lệ
    assert info["day_of_week"] in DAYS_OF_WEEK_VN.values()


def test_detect_city_from_query():
    assert detect_city_from_query("Thời tiết ở Hà Nội hôm nay thế nào?") == "hanoi"
    assert detect_city_from_query("sài gòn có mưa không neneka?") == "hcm"
    assert detect_city_from_query("cho ta hỏi thời tiết đà nẵng") == "danang"
    assert detect_city_from_query("nay tphcm nóng bao nhiêu độ") == "hcm"
    assert detect_city_from_query("thời tiết ở đà lạt") == "dalat"
    assert detect_city_from_query("khí hậu sa pa ra sao") == "sapa"
    assert detect_city_from_query("không có thành phố nào ở đây") is None


@pytest.mark.asyncio
async def test_get_vietnam_weather_live():
    # Kiểm tra lấy thời tiết Hà Nội
    w_list = await get_vietnam_weather_info("Hà Nội")
    assert len(w_list) >= 1
    w = w_list[0]
    assert w["city_name"] == "Hà Nội"
    assert "temperature" in w
    assert "apparent_temperature" in w
    assert "humidity" in w
    assert "weather_desc" in w
    assert w["status"] == "success"

    # Kiểm tra không còn mặc định ở Hà Nội khi không có địa điểm
    empty_w = await get_vietnam_weather_info()
    assert empty_w == [], "Không được mặc định trả về Hà Nội khi chưa biết vị trí người dùng"

    # Kiểm tra lấy thời tiết theo nơi ở đã lưu của người dùng
    user_w = await get_vietnam_weather_info(user_location="Sài Gòn")
    assert len(user_w) == 1
    assert user_w[0]["city_name"] == "TP. Hồ Chí Minh"


@pytest.mark.asyncio
async def test_get_vietnam_context_for_prompt():
    # Trường hợp chỉ định trong tin nhắn
    prompt_snippet = await get_vietnam_context_for_prompt("Hôm nay Sài Gòn mưa không?")
    assert "### THÔNG TIN THỜI GIAN & THỜI TIẾT THỰC TẾ (VIỆT NAM - UTC+7):" in prompt_snippet
    assert "TP. Hồ Chí Minh" in prompt_snippet
    assert "### QUY TẮC NHẬN THỨC CỦA NENEKA:" in prompt_snippet

    # Trường hợp không có địa điểm và chưa lưu nơi ở -> Tuyệt đối không tự ý nói Hà Nội
    unknown_prompt = await get_vietnam_context_for_prompt("Thời tiết hôm nay thế nào?")
    assert "Chưa xác định được vị trí" in unknown_prompt
    assert "TUYỆT ĐỐI KHÔNG được tự ý mặc định hay bịa đặt rằng người đối thoại đang ở Hà Nội" in unknown_prompt

    # Trường hợp người dùng có nơi ở đã lưu (ví dụ: Đà Nẵng)
    saved_prompt = await get_vietnam_context_for_prompt("Hôm nay có cần mang ô không?", user_location="Đà Nẵng")
    assert "Đà Nẵng" in saved_prompt

