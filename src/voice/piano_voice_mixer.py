# src/voice/piano_voice_mixer.py
"""
Phòng Thu Hòa Âm Đại Dương Cầm & Giọng Nói Neneka (Piano + Voice Line Studio Mixer):
Kết hợp hoàn chỉnh tiếng đàn Piano (bản Full-Length tìm kiếm toàn cầu hoặc Grand Piano 48kHz Synth)
với toàn bộ hệ thống Voice Line có trong code của Neneka:
1. Kho Voice Line gốc chính thức (Yuka Iguchi — `assets/voice_samples/*.mp3`).
2. Giọng hát tiếng Nhật (`JAPANESE_SONG_CATALOG` + sáng tác lời tự động).
3. Lời thì thầm ru ngủ ban đêm (`SLEEP_LULLABIES`) & Radio thoại ngẫu nhiên (`RADIO_LINES`).
4. Bất kỳ câu thoại tiếng Việt / Nhật / Anh nào do người dùng nhập (qua Fish Audio / Edge-TTS).

Kỹ thuật xử lý âm thanh phòng thu (48kHz Stereo Studio Mastering):
- Tự động cân bằng âm lượng chuẩn của giọng Neneka + phủ vang Concert Hall nhẹ để giọng & đàn hòa quyện cùng không gian.
- **Sidechain Ducking thông minh (10ms RMS Envelope Ballistics)**: Khi Neneka cất tiếng nói/hát, tiếng đàn Piano tự động dịu xuống mượt mà để lời thoại rõ từng âm tiết; khi Neneka ngắt nhịp, tiếng dương cầm dâng lên đầy cảm xúc.
- **Bố cục biểu diễn hoàn chỉnh**: Dạo đầu Piano (Intro) -> Giọng Neneka hòa cùng tiếng đàn -> Đuôi ngân Piano (Outro) fade-out êm ái (hoặc giữ trọn bài nhạc Full-Length).
"""

import asyncio
import hashlib
import logging
import math
import os
import subprocess
import wave
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.voice.piano_engine import (
    BUILTIN_PIANO_PIECES,
    compose_and_render_piano_melody,
    parse_note_sequence,
    synthesize_piano_events_to_wav,
)
from src.voice.piano_search import (
    download_piano_track_audio,
    is_valid_playable_audio_file,
    search_piano_songs,
)
from src.voice.voice_channel import resolve_ffmpeg_executable

logger = logging.getLogger("Neneka.PianoVoiceMixer")

SAMPLE_RATE = 48_000
AUDIO_CACHE_DIR = os.path.abspath("audio_cache")
os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)

VOICE_SAMPLES_DIR = os.path.abspath(os.path.join("assets", "voice_samples"))

# Danh mục Voice Line gốc có sẵn trong kho tài nguyên của dự án
OFFICIAL_VOICE_PRESETS: Dict[str, Dict[str, str]] = {
    "canon_short": {
        "file": "neneka_sample_short.mp3",
        "label": "👑 Thoại Thất Vương Tinh Tuyển (Yuka Iguchi — Ngắn gọn 25s)",
        "jp_text": "「私の冠が偽物ではないと、その身に刻み込んであげます。私はメタモルレグナント、千変万化の女ですよ。」",
        "vi_text": "Vương miện của ta không phải đồ giả, ta sẽ khắc sâu điều đó vào thân xác ngươi. Ta là Metamorph Regnant — người phụ nữ của vạn biến thiên hóa.",
        "max_sec": "32",
    },
    "canon_full": {
        "file": "neneka_sample_clean_1min.mp3",
        "label": "👑 Tuyển Tập 5 Câu Thoại Kinh Điển (Yuka Iguchi — Đầy đủ 60s)",
        "jp_text": "「鏡よ鏡、世界で最も賢く強いのは誰ですか？ ええ、その通り。当然私です。…私の中にデータさえあれば、本人は不要なのです。彼以外は。」",
        "vi_text": "Gương kia ngự ở trên tường, ai thông minh và mạnh nhất thế gian? Đương nhiên là ta... Chỉ cần có dữ liệu, bản thể gốc là vô dụng — ngoại trừ anh ấy.",
        "max_sec": "65",
    },
    "metamorph": {
        "file": "test_metamorph_voice.mp3",
        "label": "🔮 Thanh Âm Biến Mạo Ảo Ảnh (Metamorphose Voice)",
        "jp_text": "「自分の目に映った私が、本当の私だと思いますか？ ふふっ…」",
        "vi_text": "Ngươi nghĩ hình bóng phản chiếu trong mắt mình là bản thể thật của ta sao? Fufu...",
        "max_sec": "25",
    },
    "affection": {
        "file": "test_fish_audio_neneka.mp3",
        "label": "💜 Lời Tâm Tình Dịu Dàng Của Neneka",
        "jp_text": "「ふふっ、また私に会いに来てくれたのね。少し私のそばで休みましょう。」",
        "vi_text": "Fufu, cậu lại đến gặp ta đấy ư? Hãy nán lại nghỉ ngơi bên cạnh ta một lát nhé.",
        "max_sec": "25",
    },
    "story_memory": {
        "file": "neneka_story_long.mp3",
        "label": "📖 Độc Thoại Ký Ức Cốt Truyện Neneka (Trích đoạn 45s)",
        "jp_text": "「この世界の理と幻影の狭間で…あなたと共に歩む時間を、私も悪くないと思っているのですよ。」",
        "vi_text": "Giữa ranh giới của quy luật thế giới và ảo ảnh... khoảng thời gian sánh bước cùng cậu, chính ta cũng thấy thật đáng trân quý.",
        "max_sec": "45",
    },
}

# Ánh xạ thông minh giữa các bài hát trong song_manager.py và bản phối Đại Dương Cầm tương ứng
SONG_ID_TO_PIANO_PIECE: Dict[str, str] = {
    "lost_princess": "lost_princess_piano",
    "connecting_happy": "canon_in_d",
    "metamorph_serenade": "fur_elise",
    "twilight_lullaby": "clair_de_lune",
    "sakura_night": "river_flows_in_you",
    "tiny_traveler": "merry_go_round",
    "stardust_prelude": "clair_de_lune",
}

# Ánh xạ giữa kịch bản ru ngủ trong sleep_manager.py và bản nhạc nền Dương Cầm êm dịu
LULLABY_ID_TO_PIANO_PIECE: Dict[str, str] = {
    "moonlit_landosol": "clair_de_lune",
    "counting_sheep": "canon_in_d",
    "chamomile_tea": "river_flows_in_you",
    "purple_breeze": "merry_go_round",
    "seven_crowns_blessing": "lost_princess_piano",
}


def resolve_official_voice_sample(preset_key: str = "canon_short") -> Tuple[Optional[str], Dict[str, str]]:
    """Lấy đường dẫn file âm thanh gốc trong `assets/voice_samples` kèm thông tin lời thoại."""
    preset = OFFICIAL_VOICE_PRESETS.get(preset_key) or OFFICIAL_VOICE_PRESETS["canon_short"]
    fpath = os.path.join(VOICE_SAMPLES_DIR, preset["file"])
    if os.path.exists(fpath) and os.path.getsize(fpath) > 1024:
        return fpath, preset

    # Fallback sang bất kỳ file mẫu nào hiện có trong assets/voice_samples
    if os.path.isdir(VOICE_SAMPLES_DIR):
        for name in sorted(os.listdir(VOICE_SAMPLES_DIR)):
            cand = os.path.join(VOICE_SAMPLES_DIR, name)
            if name.lower().endswith((".mp3", ".wav")) and os.path.getsize(cand) > 1024:
                return cand, preset
    return None, preset


def _decode_audio_to_stereo_float32(file_path: str, max_seconds: Optional[float] = None) -> Optional[np.ndarray]:
    """
    Giải mã mọi định dạng âm thanh (MP3, WAV, M4A, OGG) sang mảng NumPy float32 48kHz Stereo `[-1.0, 1.0]`.
    Sử dụng FFmpeg đóng gói sẵn (`imageio-ffmpeg`) hoặc trình đọc `wave` thuần Python cho WAV.
    """
    if not file_path or not os.path.exists(file_path):
        return None

    ffmpeg_exe = resolve_ffmpeg_executable()
    if ffmpeg_exe:
        cmd: List[str] = [ffmpeg_exe, "-hide_banner", "-loglevel", "error"]
        if max_seconds and max_seconds > 0:
            cmd.extend(["-t", f"{float(max_seconds):.2f}"])
        cmd.extend([
            "-i", file_path,
            "-f", "s16le",
            "-acodec", "pcm_s16le",
            "-ar", str(SAMPLE_RATE),
            "-ac", "2",
            "-",
        ])
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=40, check=False)
            if proc.returncode == 0 and len(proc.stdout) >= 4096:
                raw = np.frombuffer(proc.stdout, dtype="<i2")
                usable = (len(raw) // 2) * 2
                stereo = raw[:usable].reshape(-1, 2).astype(np.float32) / 32768.0
                return stereo
        except Exception as e:
            logger.warning(f"FFmpeg decode lỗi cho '{file_path}': {e}")

    # Dự phòng thuần Python nếu là file WAV
    if file_path.lower().endswith(".wav"):
        try:
            with wave.open(file_path, "rb") as wf:
                ch = wf.getnchannels()
                sw = wf.getsampwidth()
                sr = wf.getframerate()
                max_frames = int(max_seconds * sr) if max_seconds else wf.getnframes()
                raw_bytes = wf.readframes(min(wf.getnframes(), max_frames))
                if sw == 2:
                    arr = np.frombuffer(raw_bytes, dtype="<i2").astype(np.float32) / 32768.0
                    if ch == 1:
                        arr = np.column_stack([arr, arr])
                    else:
                        arr = arr[: (len(arr) // ch) * ch].reshape(-1, ch)[:, :2]
                    if sr != SAMPLE_RATE and len(arr) > 16:
                        new_len = int(len(arr) * SAMPLE_RATE / sr)
                        x_old = np.linspace(0.0, 1.0, len(arr))
                        x_new = np.linspace(0.0, 1.0, new_len)
                        arr = np.column_stack([
                            np.interp(x_new, x_old, arr[:, 0]),
                            np.interp(x_new, x_old, arr[:, 1]),
                        ]).astype(np.float32)
                    return arr
        except Exception as e:
            logger.warning(f"WAV fallback decode lỗi cho '{file_path}': {e}")

    return None


def _encode_stereo_float32_to_audio(stereo: np.ndarray, output_mp3_path: str) -> str:
    """
    Xuất mảng âm thanh 48kHz Stereo float32 đã mastering ra file `.mp3` 192kbps chất lượng phòng thu
    (hoặc `.wav` 48kHz Stereo nếu không có FFmpeg).
    """
    pcm_int16 = np.clip(stereo * 32767.0, -32768, 32767).astype("<i2")
    raw_bytes = pcm_int16.tobytes()

    ffmpeg_exe = resolve_ffmpeg_executable()
    if ffmpeg_exe:
        cmd = [
            ffmpeg_exe,
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            "-f", "s16le",
            "-ar", str(SAMPLE_RATE),
            "-ac", "2",
            "-i", "-",
            "-acodec", "libmp3lame",
            "-b:a", "192k",
            output_mp3_path,
        ]
        try:
            proc = subprocess.run(
                cmd,
                input=raw_bytes,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=45,
                check=False,
            )
            if proc.returncode == 0 and is_valid_playable_audio_file(output_mp3_path):
                return output_mp3_path
        except Exception as e:
            logger.warning(f"FFmpeg encode MP3 lỗi ({e}), chuyển sang xuất WAV 48kHz.")

    wav_fallback = output_mp3_path[:-4] + ".wav" if output_mp3_path.lower().endswith(".mp3") else output_mp3_path + ".wav"
    with wave.open(wav_fallback, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(raw_bytes)
    return wav_fallback


def _trim_voice_silence(voice_stereo: np.ndarray, threshold: float = 0.008) -> np.ndarray:
    """Cắt bỏ khoảng im lặng thừa ở đầu và cuối file giọng nói để căn nhịp vào đàn chuẩn xác."""
    if len(voice_stereo) < SAMPLE_RATE // 4:
        return voice_stereo
    mono_abs = np.max(np.abs(voice_stereo), axis=1)
    active_idx = np.where(mono_abs > threshold)[0]
    if len(active_idx) == 0:
        return voice_stereo
    pad = int(0.08 * SAMPLE_RATE)
    start = max(0, int(active_idx[0]) - pad)
    end = min(len(voice_stereo), int(active_idx[-1]) + pad)
    return voice_stereo[start:end]


def _add_subtle_vocal_hall_air(voice_stereo: np.ndarray, wet: float = 0.11) -> np.ndarray:
    """Phủ một lớp vang phòng hòa nhạc thật mỏng lên giọng Neneka để hòa quyện tự nhiên với tiếng đàn Grand Piano."""
    n = len(voice_stereo)
    reverb = np.zeros_like(voice_stereo)
    for delay_sec, gain, swap in ((0.029, 0.42, True), (0.057, 0.26, False), (0.093, 0.15, True)):
        d = int(delay_sec * SAMPLE_RATE)
        if d < n:
            src = voice_stereo[:-d, ::-1] if swap else voice_stereo[:-d]
            reverb[d:] += src * gain
    return voice_stereo * (1.0 - wet * 0.25) + reverb * wet


def _tile_piano_with_crossfade(piano_stereo: np.ndarray, target_samples: int) -> np.ndarray:
    """Lặp mượt mà bản nhạc Piano bằng crossfade 1.2 giây nếu câu thoại/bài hát dài hơn bản đàn."""
    if len(piano_stereo) >= target_samples:
        return piano_stereo[:target_samples].copy()

    xfade = min(int(1.2 * SAMPLE_RATE), len(piano_stereo) // 4)
    if xfade < 64:
        repeats = math.ceil(target_samples / max(1, len(piano_stereo)))
        return np.tile(piano_stereo, (repeats, 1))[:target_samples].copy()

    out = piano_stereo.copy()
    fade_out = np.linspace(1.0, 0.0, xfade, dtype=np.float32)[:, None]
    fade_in = np.linspace(0.0, 1.0, xfade, dtype=np.float32)[:, None]

    while len(out) < target_samples:
        overlap = out[-xfade:] * fade_out + piano_stereo[:xfade] * fade_in
        out = np.vstack([out[:-xfade], overlap, piano_stereo[xfade:]])

    return out[:target_samples].copy()


def _compute_sidechain_piano_gain(
    voice_timeline_mono: np.ndarray,
    base_gain: float = 0.60,
    ducked_gain: float = 0.23,
) -> np.ndarray:
    """
    Tính đường bao Sidechain Ducking tốc độ 100Hz (10ms/khung):
    - Khi giọng Neneka cất lên: hạ mượt âm lượng đàn từ `base_gain` xuống `ducked_gain` (attack 30ms).
    - Khi giọng Neneka ngắt câu: nâng dần âm lượng đàn trở lại `base_gain` (release 450ms).
    """
    n_samples = len(voice_timeline_mono)
    frame_size = SAMPLE_RATE // 100  # 480 mẫu = 10ms
    n_frames = max(1, n_samples // frame_size)

    trimmed = voice_timeline_mono[: n_frames * frame_size].reshape(n_frames, frame_size)
    rms_frames = np.sqrt(np.mean(trimmed * trimmed, axis=1) + 1e-12)

    # Chuẩn hóa độ nhạy phát hiện giọng nói
    voice_drive = np.clip((rms_frames - 0.012) / 0.085, 0.0, 1.0)

    env = np.zeros(n_frames, dtype=np.float32)
    attack_coeff = math.exp(-0.010 / 0.030)   # 30ms attack
    release_coeff = math.exp(-0.010 / 0.450)  # 450ms release
    cur = 0.0
    for i in range(n_frames):
        target = float(voice_drive[i])
        if target > cur:
            cur = attack_coeff * cur + (1.0 - attack_coeff) * target
        else:
            cur = release_coeff * cur + (1.0 - release_coeff) * target
        env[i] = cur

    frame_gains = base_gain - env * (base_gain - ducked_gain)
    frame_centers = np.linspace(0, n_samples - 1, n_frames, dtype=np.float32)
    sample_indices = np.arange(n_samples, dtype=np.float32)
    return np.interp(sample_indices, frame_centers, frame_gains).astype(np.float32)


def mix_piano_and_voice_sync(
    piano_path: str,
    voice_path: str,
    intro_sec: float = 2.4,
    outro_sec: float = 3.8,
    piano_base_gain: float = 0.60,
    piano_ducked_gain: float = 0.23,
    voice_gain: float = 0.94,
    keep_full_piano: bool = False,
    max_voice_sec: float = 75.0,
    output_path: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Hòa âm hoàn chỉnh 1 bản nhạc Piano (`piano_path`) và 1 Voice Line (`voice_path`) thành 1 file Stereo `.mp3` duy nhất.
    Trả về `(mixed_audio_path, mix_metadata)`.
    """
    voice_arr = _decode_audio_to_stereo_float32(voice_path, max_seconds=max_voice_sec)
    if voice_arr is None or len(voice_arr) < SAMPLE_RATE // 5:
        raise ValueError(f"Không thể giải mã Voice Line từ '{voice_path}'.")

    voice_arr = _trim_voice_silence(voice_arr)
    # Chuẩn hóa biên độ giọng nói để luôn trong trẻo, rõ nét dù nguồn là Fish Audio, Edge-TTS hay file gốc
    v_peak = float(np.max(np.abs(voice_arr)))
    if v_peak > 1e-4:
        voice_arr = (voice_arr / v_peak) * 0.88
    voice_arr = _add_subtle_vocal_hall_air(voice_arr, wet=0.11) * voice_gain

    max_piano_decode = 270.0 if keep_full_piano else (intro_sec + (len(voice_arr) / SAMPLE_RATE) + outro_sec + 12.0)
    piano_arr = _decode_audio_to_stereo_float32(piano_path, max_seconds=max_piano_decode)
    if piano_arr is None or len(piano_arr) < SAMPLE_RATE // 2:
        raise ValueError(f"Không thể giải mã bản nhạc Piano từ '{piano_path}'.")

    p_peak = float(np.max(np.abs(piano_arr)))
    if p_peak > 1e-4:
        piano_arr = (piano_arr / p_peak) * 0.86

    intro_samples = int(max(0.5, intro_sec) * SAMPLE_RATE)
    outro_samples = int(max(1.2, outro_sec) * SAMPLE_RATE)
    min_required_samples = intro_samples + len(voice_arr) + outro_samples

    if keep_full_piano and len(piano_arr) > min_required_samples:
        total_samples = len(piano_arr)
        piano_bed = piano_arr.copy()
    else:
        total_samples = min_required_samples
        piano_bed = _tile_piano_with_crossfade(piano_arr, total_samples)

    # Đặt Voice Line lên trục thời gian sau đoạn dạo đầu Piano
    voice_timeline = np.zeros((total_samples, 2), dtype=np.float32)
    v_end = min(total_samples, intro_samples + len(voice_arr))
    voice_timeline[intro_samples:v_end] = voice_arr[: v_end - intro_samples]

    # Nếu giữ trọn bài Piano dài (> 55s) mà đoạn thoại ngắn (< 30s), nhắc lại nhẹ câu kết hoặc để đàn độc tấu mượt đến hết bài
    voice_mono = 0.5 * (voice_timeline[:, 0] + voice_timeline[:, 1])
    duck_curve = _compute_sidechain_piano_gain(
        voice_mono,
        base_gain=piano_base_gain,
        ducked_gain=piano_ducked_gain,
    )

    # Fade-in 0.6s mở màn & Fade-out 2.6s kết bài thật êm ái
    fade_in_len = min(int(0.6 * SAMPLE_RATE), total_samples // 6)
    if fade_in_len > 16:
        duck_curve[:fade_in_len] *= np.linspace(0.0, 1.0, fade_in_len, dtype=np.float32)

    fade_out_len = min(int(2.6 * SAMPLE_RATE), total_samples // 4)
    if fade_out_len > 16:
        # Cosine fade-out mượt như đĩa thu âm chuyên nghiệp
        cos_fade = 0.5 * (1.0 + np.cos(np.linspace(0.0, math.pi, fade_out_len, dtype=np.float32)))
        duck_curve[-fade_out_len:] *= cos_fade

    mixed = piano_bed * duck_curve[:, None] + voice_timeline

    # Mastering Soft-Limiter chống vỡ tiếng, giữ độ ấm và lực âm thanh chuẩn -0.8 dBFS
    peak_mix = float(np.max(np.abs(mixed)))
    if peak_mix > 0.94:
        mixed = mixed / peak_mix * 0.92
    mixed = np.tanh(mixed * 1.08) / math.tanh(1.08) * 0.93

    if not output_path:
        sig = f"{os.path.basename(piano_path)}:{os.path.basename(voice_path)}:{intro_sec}:{keep_full_piano}:{len(voice_arr)}"
        digest = hashlib.md5(sig.encode("utf-8")).hexdigest()[:12]
        output_path = os.path.join(AUDIO_CACHE_DIR, f"neneka_duet_mix_{digest}.mp3")

    final_path = _encode_stereo_float32_to_audio(mixed, output_path)
    meta = {
        "file_path": final_path,
        "duration_sec": round(total_samples / SAMPLE_RATE, 1),
        "voice_duration_sec": round(len(voice_arr) / SAMPLE_RATE, 1),
        "intro_sec": round(intro_sec, 1),
        "keep_full_piano": keep_full_piano,
    }
    return final_path, meta


async def mix_piano_and_voice(
    piano_path: str,
    voice_path: str,
    intro_sec: float = 2.4,
    outro_sec: float = 3.8,
    piano_base_gain: float = 0.60,
    piano_ducked_gain: float = 0.23,
    voice_gain: float = 0.94,
    keep_full_piano: bool = False,
    max_voice_sec: float = 75.0,
    output_path: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Bản bất đồng bộ chạy trong thread pool để không bao giờ chặn Discord Event Loop."""
    return await asyncio.to_thread(
        mix_piano_and_voice_sync,
        piano_path,
        voice_path,
        intro_sec,
        outro_sec,
        piano_base_gain,
        piano_ducked_gain,
        voice_gain,
        keep_full_piano,
        max_voice_sec,
        output_path,
    )


async def ensure_builtin_or_searched_piano_backing(
    piano_query_or_piece_key: Optional[str] = None,
    prefer_search: bool = False,
    tempo_override: Optional[int] = None,
) -> Tuple[str, str]:
    """
    Chuẩn bị nhanh file nhạc nền Piano cho buổi biểu diễn:
    - Nếu `prefer_search=True` và có tên bài hát / nhạc Game cụ thể: ưu tiên tải bản Full-Length Piano thật từ YouTube/Cloud!
    - Nếu khớp `BUILTIN_PIANO_PIECES` hoặc chạy chế độ tức thì cho `/sing`, `/sleep`, `/quote`: kết xuất ngay Grand Piano 48kHz.
    Trả về `(piano_audio_path, piano_display_title)`.
    """
    q = (piano_query_or_piece_key or "").strip()

    if prefer_search and q and q not in BUILTIN_PIANO_PIECES:
        tracks = await search_piano_songs(q, limit=3)
        for tr in tracks:
            dl = await download_piano_track_audio(tr)
            if dl and os.path.exists(dl):
                return dl, f"{tr.get('title', q)} — {tr.get('artist', 'Solo Piano')}"

    if q in BUILTIN_PIANO_PIECES:
        piece = BUILTIN_PIANO_PIECES[q]
        events = parse_note_sequence(piece["notes"])
        tempo = tempo_override or piece["tempo"]
        wav_path, _ = await asyncio.to_thread(synthesize_piano_events_to_wav, events, tempo)
        return wav_path, piece["title"]

    # Sáng tác / chọn bản nhạc mẫu khớp từ khóa
    wav_path, meta = await compose_and_render_piano_melody(q or "Lost Princess", prefer_lyria=False)
    return wav_path, meta.get("title", "Concert Grand Piano Accompaniment")
