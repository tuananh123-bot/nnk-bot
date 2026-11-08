# tests/test_song_manager.py
import pytest
from src.voice.song_manager import (
    JAPANESE_SONG_CATALOG,
    get_song_by_theme_or_random,
    is_singing_request,
    create_song_embed
)

def test_song_catalog_integrity():
    assert len(JAPANESE_SONG_CATALOG) >= 5
    for song in JAPANESE_SONG_CATALOG:
        assert "id" in song
        assert "title" in song
        assert "genre" in song
        assert "japanese_lyrics" in song
        assert "romaji" in song
        assert "vietnamese_lyrics" in song
        assert "intro_quote" in song
        assert "outro_quote" in song
        assert "emotion" in song
        assert "♪" in song["japanese_lyrics"]


def test_is_singing_request():
    # Các câu yêu cầu hát
    assert is_singing_request("Neneka ơi hát cho tôi nghe 1 bài đi") is True
    assert is_singing_request("hát một bài tiếng nhật nhé") is True
    assert is_singing_request("hát đi") is True
    assert is_singing_request("hát ru tôi ngủ đi") is True
    assert is_singing_request("sing a song for me") is True

    # Các câu hội thoại thông thường không phải yêu cầu hát
    assert is_singing_request("thời tiết hôm nay thế nào") is False
    assert is_singing_request("bây giờ là mấy giờ") is False
    assert is_singing_request("chào buổi sáng neneka") is False
    assert is_singing_request("") is False


@pytest.mark.asyncio
async def test_get_song_random_and_themed():
    # Lấy bài hát ngẫu nhiên
    song_random = await get_song_by_theme_or_random()
    assert song_random is not None
    assert "japanese_lyrics" in song_random
    assert "romaji" in song_random

    # Lấy bài hát theo chủ đề (ru ngủ)
    song_lullaby = await get_song_by_theme_or_random("hát ru ngủ")
    assert song_lullaby["id"] == "twilight_lullaby"

    # Lấy bài hát theo chủ đề hoa anh đào
    song_sakura = await get_song_by_theme_or_random("hoa anh đào sakura")
    assert song_sakura["id"] == "sakura_night"


def test_create_song_embed():
    song = JAPANESE_SONG_CATALOG[0]
    embed = create_song_embed(song)
    assert embed.title is not None
    assert song["title"] in embed.title
    fields = {f.name: f.value for f in embed.fields}
    assert "🇯🇵 Lời Bài Hát (Japanese)" in fields
    assert "🔤 Phiên Âm (Romaji)" in fields
    assert "🇻🇳 Dịch Nghĩa (Tiếng Việt)" in fields
