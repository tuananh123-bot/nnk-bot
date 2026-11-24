# tests/test_piano_music.py
import os
import wave
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.voice.piano_engine import (
    parse_note_sequence,
    synthesize_piano_events_to_wav,
    compose_and_render_piano_melody,
)
from src.voice.piano_search import (
    build_piano_search_query,
    search_piano_songs,
    _score_piano_relevance,
)
from src.voice.voice_channel import voice_channel_mgr
from src.cogs.voice import VoiceCog


class TestPianoNoteAndSyllableSynthesis:
    def test_parse_vietnamese_solfege_syllables(self):
        events = parse_note_sequence("Đô Rê Mi Pha Sol La Si Đô5")
        assert len(events) == 8
        midis = [e[0][0] for e in events]
        assert midis == [60, 62, 64, 65, 67, 69, 71, 72]

    def test_parse_scientific_pitch_chords_and_durations(self):
        events = parse_note_sequence("C4+E4+G4:2 F#4:0.5 Bb3:1.5")
        assert len(events) == 3
        assert events[0] == ([60, 64, 67], 2.0)
        assert events[1] == ([66], 0.5)
        assert events[2] == ([58], 1.5)

    def test_parse_jianpu_numbered_notation_and_sustain(self):
        events = parse_note_sequence("1 1 5 5 6 6 5 - 1'")
        # Nốt '5' gặp dấu '-' nối tiếp nên kéo dài lên 2.0 phách
        assert len(events) == 8
        assert events[6] == ([67], 2.0)
        assert events[7] == ([72], 1.0)

    def test_parse_named_chords(self):
        events = parse_note_sequence("Cmaj Am Fmaj7 G7")
        assert len(events) == 4
        assert events[0][0] == [60, 64, 67]
        assert len(events[3][0]) == 4  # G7 có 4 nốt

    def test_synthesize_48khz_stereo_wav_and_pcm_audio(self, tmp_path):
        events = parse_note_sequence("Đô4 Mi4 Sol4 Đô5:2")
        out_wav = str(tmp_path / "test_grand_piano.wav")
        wav_path, meta = synthesize_piano_events_to_wav(events, tempo_bpm=120, output_path=out_wav)

        assert os.path.exists(wav_path)
        assert meta["notes_played"] == 4
        assert meta["tempo_bpm"] == 120

        with wave.open(wav_path, "rb") as wf:
            assert wf.getnchannels() == 2
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 48000
            assert wf.getnframes() > 48000

        # Kiểm tra đọc trực tiếp thành discord.PCMAudio không cần FFmpeg
        pcm_source = voice_channel_mgr._build_wav_pcm_source(wav_path)
        assert pcm_source is not None

    @pytest.mark.asyncio
    async def test_compose_builtin_masterpiece(self):
        wav_path, meta = await compose_and_render_piano_melody("Canon in D", prefer_lyria=False)
        assert os.path.exists(wav_path)
        assert "Canon in D" in meta["title"]
        assert meta["duration_sec"] > 2.0


class TestGlobalPianoSearchEngine:
    def test_build_piano_search_query(self):
        assert build_piano_search_query("tìm nhạc Suzume") == "Suzume piano"
        assert build_piano_search_query("Chopin Nocturne Piano") == "Chopin Nocturne Piano"
        assert build_piano_search_query("mở bài Nơi này có anh") == "Nơi này có anh piano"

    def test_piano_relevance_scoring(self):
        piano_cover = {
            "title": "Unravel (Tokyo Ghoul) - Solo Piano Version",
            "artist": "Animenz Piano Sheets",
            "album": "Anime Piano Collection",
            "audio_ext": "mp3",
            "is_full_track": False,
        }
        generic_pop = {
            "title": "Random Pop Song",
            "artist": "DJ Beats",
            "album": "Club Mix",
            "audio_ext": "m4a",
            "is_full_track": False,
        }
        assert _score_piano_relevance(piano_cover, "Unravel") > _score_piano_relevance(generic_pop, "Unravel")

    @pytest.mark.asyncio
    async def test_search_piano_songs_dedup_and_ranking(self):
        fake_deezer = [
            {
                "source": "Deezer Hi-Fi",
                "title": "River Flows in You (Solo Piano)",
                "artist": "Yiruma",
                "album": "First Love Piano",
                "duration_sec": 188,
                "audio_url": "https://cdn.example.com/river.mp3",
                "audio_ext": "mp3",
                "page_url": "https://deezer.com/track/1",
                "youtube_url": "https://youtube.com",
                "artwork_url": "",
                "is_full_track": False,
            }
        ]
        with patch("src.voice.piano_search._search_deezer", new_callable=AsyncMock, return_value=fake_deezer), \
             patch("src.voice.piano_search._search_itunes", new_callable=AsyncMock, return_value=[]), \
             patch("src.voice.piano_search._search_internet_archive_full_piano", new_callable=AsyncMock, return_value=[]):

            tracks = await search_piano_songs("River Flows in You")
            assert len(tracks) == 1
            assert tracks[0]["artist"] == "Yiruma"
            assert tracks[0]["audio_ext"] == "mp3"

    @pytest.mark.asyncio
    async def test_voice_cog_piano_commands_registered(self):
        bot = MagicMock()
        cog = VoiceCog(bot)
        cmd_names = {c.name for c in cog.get_commands()}
        assert "piano" in cmd_names
        assert "notes" in cmd_names
        assert "compose" in cmd_names
