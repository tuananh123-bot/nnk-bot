# tests/test_piano_voice_mix.py
import os
import numpy as np
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.voice.piano_engine import parse_note_sequence, synthesize_piano_events_to_wav, BUILTIN_PIANO_PIECES
from src.voice.piano_search import is_valid_playable_audio_file
from src.voice.piano_voice_mixer import (
    OFFICIAL_VOICE_PRESETS,
    SAMPLE_RATE,
    _compute_sidechain_piano_gain,
    mix_piano_and_voice_sync,
    resolve_official_voice_sample,
)
from src.voice.sleep_manager import sleep_manager, SLEEP_LULLABIES
from src.cogs.voice import VoiceCog


class TestPianoVoiceStudioMixer:
    def test_all_official_voice_presets_exist_in_codebase(self):
        for preset_key in OFFICIAL_VOICE_PRESETS:
            v_path, meta = resolve_official_voice_sample(preset_key)
            assert v_path is not None, f"Preset {preset_key} thiếu file mẫu"
            assert os.path.exists(v_path)
            assert os.path.getsize(v_path) > 50_000
            assert meta["jp_text"]

    def test_sidechain_ducking_lowers_piano_when_neneka_speaks(self):
        # 1 giây im lặng -> 1 giây giọng nói biên độ lớn -> 1 giây im lặng
        silence = np.zeros(SAMPLE_RATE, dtype=np.float32)
        t = np.arange(SAMPLE_RATE, dtype=np.float32) / SAMPLE_RATE
        speech = (0.5 * np.sin(2.0 * np.pi * 220.0 * t)).astype(np.float32)
        timeline = np.concatenate([silence, speech, silence])

        gain_curve = _compute_sidechain_piano_gain(timeline, base_gain=0.60, ducked_gain=0.22)
        assert len(gain_curve) == len(timeline)
        # Đoạn dạo đầu im lặng: đàn giữ nguyên âm lượng ~0.60
        assert float(np.mean(gain_curve[: SAMPLE_RATE // 2])) > 0.57
        # Giữa lúc Neneka đang nói: đàn tự động hạ xuống gần ~0.22
        assert float(np.mean(gain_curve[int(1.3 * SAMPLE_RATE) : int(1.9 * SAMPLE_RATE)])) < 0.28
        # Cuối đoạn sau khi dứt lời: đàn dâng mượt trở lại
        assert float(gain_curve[-1]) > 0.50

    def test_real_mix_piano_and_official_neneka_voice_to_stereo_mp3(self, tmp_path):
        # Kết xuất nhạc nền Lost Princess Piano 48kHz + ghép thực tế với Voice Line gốc của Yuka Iguchi
        events = parse_note_sequence(BUILTIN_PIANO_PIECES["lost_princess_piano"]["notes"])
        piano_wav = str(tmp_path / "piano_backing.wav")
        synthesize_piano_events_to_wav(events, tempo_bpm=112, output_path=piano_wav)

        voice_mp3, _ = resolve_official_voice_sample("metamorph")
        out_mp3 = str(tmp_path / "neneka_complete_duet.mp3")

        final_path, meta = mix_piano_and_voice_sync(
            piano_path=piano_wav,
            voice_path=voice_mp3,
            intro_sec=1.8,
            outro_sec=2.5,
            output_path=out_mp3,
        )

        assert os.path.exists(final_path)
        assert is_valid_playable_audio_file(final_path) is True
        assert os.path.getsize(final_path) > 120_000
        assert meta["duration_sec"] > meta["voice_duration_sec"] + 3.0

    @pytest.mark.asyncio
    async def test_voice_cog_concert_sing_and_sleep_with_piano(self):
        bot = MagicMock()
        cog = VoiceCog(bot)

        # Kiểm tra đăng ký lệnh prefix !n concert và các alias
        prefix_cmds = {c.name for c in cog.get_commands()}
        assert "concert" in prefix_cmds
        slash_cmds = {c.name for c in cog.get_app_commands()}
        assert "concert" in slash_cmds

        # Kiểm tra handle_piano_voice_concert chạy hoàn chỉnh với bản nhạc sẵn có + thoại gốc
        mixed_path, fname, embed, view = await cog.handle_piano_voice_concert(
            piano_query="lost_princess_piano",
            voice_preset_or_text="affection",
            keep_full_piano=False,
        )
        assert os.path.exists(mixed_path)
        assert is_valid_playable_audio_file(mixed_path) is True
        assert fname.startswith("neneka_concert.")
        assert "Piano" in embed.title

        # Kiểm tra _handle_sing trả về bản thu có đệm đàn Piano (giả lập TTS bằng file thoại mẫu để chạy nhanh)
        sample_v, _ = resolve_official_voice_sample("affection")
        with patch("src.cogs.voice.japanese_tts.generate_speech", new_callable=AsyncMock, return_value=sample_v):
            sing_audio, song, piano_title, mix_meta = await cog._handle_sing(theme="lost princess")
            assert sing_audio and os.path.exists(sing_audio)
            assert is_valid_playable_audio_file(sing_audio) is True
            assert "Lost Princess" in piano_title
            assert mix_meta.get("duration_sec", 0) > 5.0

        # Kiểm tra chế độ ru ngủ (SleepManager) hòa âm lời thì thầm trên nền Dương Cầm Clair de Lune
        with patch("src.voice.sleep_manager.japanese_tts.generate_speech", new_callable=AsyncMock, return_value=sample_v):
            lullaby_audio = await sleep_manager.generate_lullaby_audio(SLEEP_LULLABIES[0], with_piano=True)
            assert lullaby_audio and os.path.exists(lullaby_audio)
            assert is_valid_playable_audio_file(lullaby_audio) is True
