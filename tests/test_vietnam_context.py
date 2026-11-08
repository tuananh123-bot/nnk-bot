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

    # Kiểm tra lấy thời tiết mặc định (Hà Nội & TP.HCM)
    default_w = await get_vietnam_weather_info()
    assert len(default_w) == 2
    city_names = [item["city_name"] for item in default_w]
    assert "Hà Nội" in city_names
    assert "TP. Hồ Chí Minh" in city_names


@pytest.mark.asyncio
async def test_get_vietnam_context_for_prompt():
    prompt_snippet = await get_vietnam_context_for_prompt("Hôm nay Sài Gòn mưa không?")
    assert "### THÔNG TIN THỜI GIAN & THỜI TIẾT THỰC TẾ (VIỆT NAM - UTC+7):" in prompt_snippet
    assert "TP. Hồ Chí Minh" in prompt_snippet
    assert "### QUY TẮC NHẬN THỨC CỦA NENEKA:" in prompt_snippet

