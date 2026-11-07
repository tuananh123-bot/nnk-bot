# tests/test_japanese_tts.py
import pytest
import os
from src.voice.japanese_tts import japanese_tts, EMOTION_PRESETS

def test_tts_supported_emotions():
    emotions = japanese_tts.get_supported_emotions()
    assert "Normal" in emotions
    assert "Affectionate" in emotions
    assert "Sarcastic" in emotions
    assert len(emotions) == 10

@pytest.mark.asyncio
async def test_japanese_tts_generation():
    text = "ふふっ、坊や。"
    path = await japanese_tts.generate_speech(text, emotion="Normal")
    assert path is not None
    assert os.path.exists(path)
    assert os.path.getsize(path) > 0

def test_fish_audio_provider():
    from src.voice.fish_audio_tts import FishAudioTTSProvider
    provider = FishAudioTTSProvider()
    assert provider.get_audio_format() == "mp3"
    assert "ja" in provider.get_supported_languages()


