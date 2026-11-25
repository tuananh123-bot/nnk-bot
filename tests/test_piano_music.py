# tests/test_piano_music.py
import os
import wave
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.voice.piano_engine import (
    is_genuine_note_sequence,
    parse_note_sequence,
    synthesize_piano_events_to_wav,
    compose_and_render_piano_melody,
)
from src.voice.piano_search import (
    build_piano_search_query,
    is_valid_playable_audio_file,
    search_piano_songs,
    _score_piano_relevance,
)
from src.voice.voice_channel import voice_channel_mgr, resolve_ffmpeg_executable
from src.cogs.voice import VoiceCog


class TestPianoNoteAndSyllableSynthesis:
    def test_parse_vietnamese_solfege_syllables(self):
        events = parse_note_sequence("Đô Rê Mi Pha Sol La Si Đô5")
        assert len(events) == 8
        midis = [e[0][0] for e in events]
        assert midis == [60, 62, 64, 65, 67, 69, 71, 72]

    def test_parse_hyphen_comma_and_concatenated_notes_not_single_note(self):
        # Không bao giờ bị gộp thành 1 nốt duy nhất khi gõ dấu gạch ngang, dấu phẩy hoặc viết liền!
        ev_hyphen = parse_note_sequence("Đô-Rê-Mi-Pha-Sol")
        assert len(ev_hyphen) == 5
        assert [e[0][0] for e in ev_hyphen] == [60, 62, 64, 65, 67]

        ev_comma = parse_note_sequence("C4,D4,E4,F4,G4")
        assert len(ev_comma) == 5
        assert [e[0][0] for e in ev_comma] == [60, 62, 64, 65, 67]

        ev_concat_sci = parse_note_sequence("C4D4E4G4")
        assert len(ev_concat_sci) == 4
        assert [e[0][0] for e in ev_concat_sci] == [60, 62, 64, 67]

        ev_concat_jianpu = parse_note_sequence("1155665")
        assert len(ev_concat_jianpu) == 7
        assert [e[0][0] for e in ev_concat_jianpu] == [60, 60, 67, 67, 69, 69, 67]

    def test_genuine_note_sequence_rejects_game_and_song_titles(self):
        # Tên bài hát / tên Game vô tình chứa từ trùng tên nốt ('Re', 'La', 'Do', 'A') KHÔNG được phát 1 nốt lẻ!
        assert is_genuine_note_sequence("Lost Princess") is False
        assert is_genuine_note_sequence("Re Zero") is False
        assert is_genuine_note_sequence("La La Land") is False
        assert is_genuine_note_sequence("Do It") is False
        assert is_genuine_note_sequence("A Thousand Years") is False

        # Chuỗi âm tiết / nốt nhạc thật sự phải được nhận diện đúng
        assert is_genuine_note_sequence("Đô Rê Mi Pha Sol") is True
        assert is_genuine_note_sequence("Đô-Rê-Mi-Pha-Sol") is True
        assert is_genuine_note_sequence("C4,D4,E4,G4") is True
        assert is_genuine_note_sequence("1 1 5 5 6 6 5") is True
        assert is_genuine_note_sequence("1155665") is True

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
        assert is_valid_playable_audio_file(wav_path) is True

        with wave.open(wav_path, "rb") as wf:
            assert wf.getnchannels() == 2
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 48000
            assert wf.getnframes() > 48000

        pcm_source = voice_channel_mgr._build_wav_pcm_source(wav_path)
        assert pcm_source is not None
        assert resolve_ffmpeg_executable() is not None

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

    def test_exact_game_song_phrase_beats_scattered_words(self):
        # Regression test cho ảnh chụp màn hình 'n! piano lost princess':
        # 'Lost Princess (Princess Connect! Re:Dive) Piano' PHẢI xếp trên 'The Lost People (From Princess Mononoke)'!
        exact_priconne = {
            "title": "[Princess Connect! Re:Dive OP] Lost Princess (Full ver.) Piano Arrangement",
            "artist": "Frank Tedesco",
            "album": "Full Solo Piano Performance",
            "audio_ext": "mp3",
            "is_full_track": True,
        }
        wrong_scattered = {
            "title": 'The Lost People: Image Album Version (From "Princess Mononoke") [For Piano Solo]',
            "artist": "daigoro789",
            "album": "Princess Mononoke Soundtrack",
            "audio_ext": "mp3",
            "is_full_track": False,
        }
        assert _score_piano_relevance(exact_priconne, "lost princess") > _score_piano_relevance(
            wrong_scattered, "lost princess"
        ) + 100

    def test_reject_corrupt_892_byte_dead_mp3(self, tmp_path):
        # Chặn tuyệt đối file lỗi XML/HTML 892 bytes (0:00 / 0:00 không phát ra tiếng)
        dead_mp3 = tmp_path / "dead_892.mp3"
        dead_mp3.write_bytes(b"<?xml version='1.0'?><Error><Code>AccessDenied</Code></Error>" + b"x" * 831)
        assert os.path.getsize(dead_mp3) == 892
        assert is_valid_playable_audio_file(str(dead_mp3)) is False

        # Chấp nhận file MP3 hợp lệ >= 40KB có header ID3
        valid_mp3 = tmp_path / "valid_full.mp3"
        valid_mp3.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x64" * 12000)
        assert is_valid_playable_audio_file(str(valid_mp3)) is True

    @pytest.mark.asyncio
    async def test_search_piano_songs_dedup_and_ranking(self):
        fake_yt = [
            {
                "source": "YouTube Piano (Full Track)",
                "yt_id": "abc123xyz",
                "title": "River Flows in You (Solo Piano)",
                "artist": "Yiruma",
                "album": "First Love Piano",
                "duration_sec": 188,
                "audio_url": "https://www.youtube.com/watch?v=abc123xyz",
                "audio_ext": "mp3",
                "page_url": "https://www.youtube.com/watch?v=abc123xyz",
                "youtube_url": "https://www.youtube.com/watch?v=abc123xyz",
                "artwork_url": "",
                "is_full_track": True,
            }
        ]
        with patch("src.voice.piano_search._search_youtube_full_piano", new_callable=AsyncMock, return_value=fake_yt), \
             patch("src.voice.piano_search._search_deezer", new_callable=AsyncMock, return_value=[]), \
             patch("src.voice.piano_search._search_itunes", new_callable=AsyncMock, return_value=[]), \
             patch("src.voice.piano_search._search_internet_archive_full_piano", new_callable=AsyncMock, return_value=[]):

            tracks = await search_piano_songs("River Flows in You")
            assert len(tracks) == 1
            assert tracks[0]["artist"] == "Yiruma"
            assert tracks[0]["is_full_track"] is True

    @pytest.mark.asyncio
    async def test_voice_cog_piano_commands_registered(self):
        bot = MagicMock()
        cog = VoiceCog(bot)
        cmd_names = {c.name for c in cog.get_commands()}
        assert "piano" in cmd_names
        assert "notes" in cmd_names
        assert "compose" in cmd_names
