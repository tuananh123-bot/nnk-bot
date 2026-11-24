# src/voice/piano_engine.py
"""
Bộ Tổng Hợp Âm Thanh Đại Dương Cầm (Concert Grand Piano Synthesizer) & Tạo Âm Tiết Nốt Nhạc:
1. Hỗ trợ đa chuẩn ký hiệu âm tiết nhạc lý:
   - Âm tiết tiếng Việt (Solfège): Đô, Rê, Mi, Pha, Sol (Son), La, Si (kèm thăng #, giáng b, quãng 1-7, dấu ' tăng quãng).
   - Ký hiệu quốc tế (Scientific Pitch): C4, D4, E4, F#4, Bb3, G5, A0..C8 (đầy đủ 88 phím đàn Piano).
   - Cảm âm số (Jianpu): 1, 2, 3, 4, 5, 6, 7, 1' (cao), 5, (thấp), 0 / - (nghỉ/ngân).
   - Hợp âm (Chords): C, Cm, Cmaj7, Dm, Em, F, Fmaj7, G, G7, Am, Bdim hoặc bấm nhiều phím cùng lúc `C4+E4+G4`.
2. Tổng hợp âm học vật lý (Physical-inspired Acoustic Grand Piano @ 48kHz Stereo 16-bit WAV):
   - Chuỗi bồi âm (8 harmonics) có độ lệch dây đàn thực tế (String Inharmonicity).
   - Đầu búa gõ nỉ (Hammer Strike Transient) + cộng hưởng thùng đàn & Pedal ngân (Damper Sustain).
   - Không gian phòng hòa nhạc Stereo Panning + Schroeder Hall Reverb.
3. Kho bản nhạc cổ điển & Anime Piano mẫu + Sáng tác giai điệu Piano bằng AI (Google Lyria 3.5 / Fast LLM).
"""

import asyncio
import base64
import hashlib
import io
import json
import logging
import math
import os
import re
import wave
from typing import Dict, List, Optional, Tuple, Any

import numpy as np

from src.config import settings

logger = logging.getLogger("Neneka.PianoEngine")

SAMPLE_RATE = 48_000  # Chuẩn 48kHz Stereo tương thích trực tiếp với Discord PCMAudio & Inline Player
AUDIO_CACHE_DIR = os.path.abspath("audio_cache")
os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)

# Bảng ánh xạ nốt cơ bản sang bán cung (semitone trong 1 quãng tám, C = 0)
NOTE_SEMITONES: Dict[str, int] = {
    "c": 0, "đô": 0, "do": 0, "ut": 0,
    "d": 2, "rê": 2, "re": 2,
    "e": 4, "mi": 4,
    "f": 5, "pha": 5, "fa": 5,
    "g": 7, "sol": 7, "son": 7,
    "a": 9, "la": 9,
    "b": 11, "si": 11, "ti": 11, "h": 11,
}

JIANPU_SEMITONES: Dict[str, int] = {
    "1": 0,
    "2": 2,
    "3": 4,
    "4": 5,
    "5": 7,
    "6": 9,
    "7": 11,
}

# Bảng hợp âm phổ biến -> danh sách khoảng cách bán cung tính từ nốt gốc
CHORD_INTERVALS: Dict[str, List[int]] = {
    "": [0, 4, 7],
    "maj": [0, 4, 7],
    "m": [0, 3, 7],
    "min": [0, 3, 7],
    "7": [0, 4, 7, 10],
    "maj7": [0, 4, 7, 11],
    "m7": [0, 3, 7, 10],
    "sus2": [0, 2, 7],
    "sus4": [0, 5, 7],
    "dim": [0, 3, 6],
    "aug": [0, 4, 8],
    "add9": [0, 4, 7, 14],
}

# Kho bản nhạc Piano kinh điển (2 bè: Giai điệu + Hợp âm rải) sẵn sàng biểu diễn tức thì
BUILTIN_PIANO_PIECES: Dict[str, Dict[str, Any]] = {
    "canon_in_d": {
        "title": "Canon in D Major — Johann Pachelbel",
        "tempo": 88,
        "keywords": ["canon", "pachelbel", "canon in d"],
        "notes": (
            "D3+F#4+A4:2 A2+E4+A4:2 B2+D4+F#4:2 F#2+C#4+F#4:2 "
            "G2+B3+D4:2 D2+A3+D4:2 G2+B3+D4:2 A2+C#4+E4:2 "
            "D3+F#5:1 F#4:1 A4+E5:1 E4:1 B2+D5:1 D4:1 F#2+C#5:1 A3:1 "
            "G2+B4:1 D4:1 D2+A4:1 F#4:1 G2+B4:1 D4:1 A2+C#5:1 E4:1 "
            "D3+D5:0.5 F#5:0.5 A5:1 A2+G5:0.5 F#5:0.5 G5:1 "
            "B2+F#5:0.5 D5:0.5 E5:1 F#2+C#5:0.5 A4:0.5 F#5:1 "
            "G2+D5:0.5 B4:0.5 G5:1 D2+F#5:0.5 D5:0.5 A5:1 "
            "G2+G5:0.5 B4:0.5 E5:1 A2+C#5:1 A3+E5:1 D3+F#4+D5:3"
        ),
    },
    "river_flows_in_you": {
        "title": "River Flows in You — Yiruma",
        "tempo": 108,
        "keywords": ["river flows", "yiruma", "dòng sông"],
        "notes": (
            "F#3+A4:1 C#4+G#4:1 F#4+A4:1 G#4:0.5 A4:0.5 "
            "D3+E4:1 A3+A4:1 D4:2 "
            "A2+C#4:0.5 E3+D4:0.5 A3+E4:1 C#4+A4:1 B4:0.5 C#5:0.5 "
            "E3+G#4:1 B3+E4:1 E4+B3:2 "
            "F#3+A4:0.5 G#4:0.5 C#4+A4:0.5 E4:0.5 F#4+A4:0.5 B4:0.5 C#5:0.5 D5:0.5 "
            "D3+E5:0.5 D5:0.5 A3+C#5:0.5 B4:0.5 D4+A4:2 "
            "A2+G#4:0.5 A4:0.5 E3+B4:0.5 C#5:0.5 E3+G#4:1 B3+E4:1 F#3+C#4+F#4:3"
        ),
    },
    "fur_elise": {
        "title": "Für Elise (Bagatelle No. 25 in A minor) — Beethoven",
        "tempo": 124,
        "keywords": ["fur elise", "für elise", "beethoven", "elise"],
        "notes": (
            "E5:0.5 D#5:0.5 E5:0.5 D#5:0.5 E5:0.5 B4:0.5 D5:0.5 C5:0.5 "
            "A2+A4:1 E3:0.5 A3:0.5 C4:0.5 E4:0.5 A4:0.5 "
            "E2+B4:1 E3:0.5 G#3:0.5 E4:0.5 G#4:0.5 B4:0.5 "
            "A2+C5:1 E3:0.5 A3:0.5 E4:0.5 E5:0.5 D#5:0.5 "
            "E5:0.5 D#5:0.5 E5:0.5 B4:0.5 D5:0.5 C5:0.5 "
            "A2+A4:1 E3:0.5 A3:0.5 C4:0.5 E4:0.5 A4:0.5 "
            "E2+B4:1 E3:0.5 G#3:0.5 E4:0.5 C5:0.5 B4:0.5 A2+E3+A4:3"
        ),
    },
    "merry_go_round": {
        "title": "Merry-Go-Round of Life (Howl's Moving Castle) — Joe Hisaishi",
        "tempo": 132,
        "keywords": ["howl", "merry go round", "hisaishi", "ghibli", "lâu đài bay"],
        "notes": (
            "D4:1 G3+G4:1 B3+B4:1 D3+D5:2 C5:1 "
            "G3+B4:2 A4:1 G3+G4:3 "
            "G4:1 A3+C5:1 E4+E5:1 A3+G5:2 F#5:1 "
            "D3+G5:1 F#5:1 E5:1 D3+A3+D5:3 "
            "B4:1 E3+E5:1 G4+G5:1 B3+B5:2 A5:1 "
            "C3+G5:1 F#5:1 G5:1 D3+A3+A5:2 F#5:1 G2+D3+B4+G5:3"
        ),
    },
    "clair_de_lune": {
        "title": "Clair de Lune — Claude Debussy",
        "tempo": 72,
        "keywords": ["clair de lune", "debussy", "ánh trăng", "moonlight"],
        "notes": (
            "Db3+Ab3+F5:1.5 Ab5:1.5 F5:2 Db5:0.5 Eb5:0.5 F5:1 Eb5:2 "
            "Gb2+Db3+Db5:0.5 Eb5:0.5 Db5:1 F5:1 Db5:2 "
            "Ab2+Eb3+C5:0.5 Db5:0.5 C5:1 Eb5:1 C5:1.5 Bb4:1.5 "
            "Db3+F3+Ab4:3 Db3+Ab3+F4+Db5:3.5"
        ),
    },
    "lost_princess_piano": {
        "title": "Lost Princess (Solo Piano Arrangement) — Princess Connect! Re:Dive",
        "tempo": 112,
        "keywords": ["lost princess", "priconne", "neneka", "landosol", "princess connect"],
        "notes": (
            "F3+C5:1 A3+D5:1 C4+F5:1.5 E5:0.5 D3+A4+D5:1 C5:1 Bb2+F3+D5:2 "
            "C3+G4+C5:1 D5:1 A2+E4+E5:1.5 F5:0.5 D3+A3+D5:2 C3+G3+E5:2 "
            "F3+A4+F5:1 G5:1 D3+A4+A5:1.5 G5:0.5 Bb2+F3+F5:1 E5:1 C3+G3+D5:1 E5:1 "
            "F3+C4+A4+F5:3.5"
        ),
    },
}


def midi_to_freq(midi_note: int) -> float:
    """Chuyển mã phím MIDI (21=A0 .. 108=C8, 69=A4=440Hz) sang tần số Hz."""
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))


def midi_to_note_name(midi_note: int) -> str:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    octave = (midi_note // 12) - 1
    return f"{names[midi_note % 12]}{octave}"


def _parse_single_pitch_token(token: str, default_octave: int = 4) -> List[int]:
    """
    Phân tích 1 token đơn (không chứa thời lượng) thành danh sách mã MIDI (1 nốt hoặc hợp âm).
    Trả về [] nếu là dấu lặng (rest).
    """
    t = token.strip()
    if not t or t in {"-", "_", "~", "0", "rest", "nghi", "nghỉ", "lặng"}:
        return []

    # Hợp âm ghép bằng dấu '+' (ví dụ C4+E4+G4 hoặc Đô4+Mi4+Sol4)
    if "+" in t:
        midis: List[int] = []
        for part in t.split("+"):
            midis.extend(_parse_single_pitch_token(part, default_octave=default_octave))
        return sorted(set(midis))

    # 1. Kiểm tra cảm âm số Jianpu: 1, 2, 3, #4, b7, 1', 2'', 5,
    m_num = re.match(r"^([#b]?)([1-7])([#b]?)([',]*)$", t)
    if m_num:
        acc1, digit, acc2, oct_marks = m_num.groups()
        semi = JIANPU_SEMITONES[digit]
        acc = acc1 or acc2
        if acc == "#":
            semi += 1
        elif acc == "b":
            semi -= 1
        octave = default_octave + oct_marks.count("'") - oct_marks.count(",")
        midi = 12 * (octave + 1) + semi
        return [max(21, min(108, midi))]

    # 2. Kiểm tra tên hợp âm chuẩn (ví dụ: Cmaj7, Am, Dm7, F#m, G7, Bbmaj)
    m_chord = re.match(r"^([A-Ga-g])([#b]?)(maj7|maj|min|m7|m|7|sus2|sus4|dim|aug|add9)$", t)
    if m_chord and not t.lower().startswith(("do", "re", "mi", "fa", "so", "la", "si")):
        root_char, acc, ctype = m_chord.groups()
        base_semi = NOTE_SEMITONES[root_char.lower()]
        if acc == "#":
            base_semi += 1
        elif acc == "b":
            base_semi -= 1
        root_midi = 12 * (default_octave + 1) + base_semi
        intervals = CHORD_INTERVALS.get(ctype.lower(), [0, 4, 7])
        return [max(21, min(108, root_midi + iv)) for iv in intervals]

    # 3. Kiểm tra âm tiết tiếng Việt (Đô, Rê, Mi, Pha, Sol, Son, La, Si) hoặc nốt chữ cái (C4, F#5, Bb3)
    lower_t = t.lower()
    # Sắp xếp key dài trước để 'đô'/'sol'/'pha' khớp trước 'd'/'f'/'b'
    sorted_keys = sorted(NOTE_SEMITONES.keys(), key=len, reverse=True)
    for k in sorted_keys:
        if lower_t.startswith(k):
            rest = t[len(k):]
            m_tail = re.match(r"^([#♯b♭]?)(\d?)([',]*)$", rest)
            if m_tail:
                acc, oct_digit, oct_marks = m_tail.groups()
                semi = NOTE_SEMITONES[k]
                if acc in ("#", "♯"):
                    semi += 1
                elif acc in ("b", "♭"):
                    semi -= 1
                octave = int(oct_digit) if oct_digit else default_octave
                octave += oct_marks.count("'") - oct_marks.count(",")
                midi = 12 * (octave + 1) + semi
                return [max(21, min(108, midi))]

    return []


def parse_note_sequence(
    sequence_text: str,
    default_octave: int = 4,
) -> List[Tuple[List[int], float]]:
    """
    Phân tích chuỗi âm tiết / nốt nhạc người dùng nhập thành danh sách sự kiện:
    [(danh_sách_midi, số_phách_beats), ...]
    Hỗ trợ phân tách bằng khoảng trắng, dấu phẩy, gạch đứng `|`, xuống dòng.
    Thời lượng tùy chọn qua `:số` hoặc `*số` hoặc `/số` (ví dụ `C4:2`, `Đô*1.5`, `Sol/2`, `Mi.`).
    """
    if not sequence_text:
        return []

    # Thay dấu gạch nhịp '|' và xuống dòng bằng khoảng trắng; tách dấu phẩy nếu không phải ký hiệu quãng trầm Jianpu
    cleaned = sequence_text.replace("|", " ").replace("\n", " ").replace(";", " ")
    cleaned = re.sub(r",\s+", " ", cleaned)
    raw_tokens = [tok.strip() for tok in cleaned.split() if tok.strip()]

    events: List[Tuple[List[int], float]] = []
    for tok in raw_tokens:
        beats = 1.0
        pitch_part = tok

        # Tách thời lượng :2, *2, /2
        m_dur = re.match(r"^(.+?)(?:[:*]([0-9]*\.?[0-9]+)|/([0-9]*\.?[0-9]+))$", tok)
        if m_dur:
            pitch_part = m_dur.group(1)
            if m_dur.group(2):
                beats = float(m_dur.group(2))
            elif m_dur.group(3) and float(m_dur.group(3)) > 0:
                beats = 1.0 / float(m_dur.group(3))
        elif pitch_part.endswith(".") and len(pitch_part) > 1:
            pitch_part = pitch_part[:-1]
            beats = 1.5

        beats = max(0.125, min(8.0, beats))

        # Nếu là ký hiệu ngân '-' nối tiếp nốt trước đó thì cộng thêm phách ngân cho nốt trước
        if pitch_part in {"-", "~"} and events and events[-1][0]:
            prev_midis, prev_beats = events[-1]
            events[-1] = (prev_midis, min(8.0, prev_beats + beats))
            continue

        midis = _parse_single_pitch_token(pitch_part, default_octave=default_octave)
        if midis or pitch_part in {"0", "_", "rest", "nghi", "nghỉ", "lặng", "-"}:
            events.append((midis, beats))

    return events


def _synthesize_single_piano_key(midi_note: int, duration_sec: float, velocity: float = 0.85) -> Tuple[np.ndarray, float]:
    """
    Tổng hợp sóng âm 1 phím Đại Dương Cầm (Grand Piano) ở tần số lấy mẫu 48kHz:
    - 8 bồi âm (harmonics) kèm hệ số lệch tần số dây thép (inharmonicity B).
    - Búa nỉ gõ (hammer strike transient) + bao hình suy giảm kép (two-stage soundboard decay).
    Trả về: (mono_wave_float32, pan_position [-0.35 .. +0.35])
    """
    freq = midi_to_freq(midi_note)
    # Cộng thêm đuôi ngân tự nhiên của thùng đàn piano (pedal sustain nhẹ)
    ring_tail = min(0.45, max(0.18, 0.38 - (midi_note - 48) * 0.003))
    total_dur = max(0.08, duration_sec + ring_tail)
    n_samples = int(SAMPLE_RATE * total_dur)
    t = np.arange(n_samples, dtype=np.float32) / SAMPLE_RATE

    # Hệ số lệch dây đàn piano thực tế (cao hơn ở quãng cao)
    inharmonicity_b = 0.00015 * (1.0 + max(0.0, (midi_note - 45) / 36.0))
    # Tốc độ tắt âm tự nhiên: nốt trầm ngân lâu, nốt cao tắt nhanh và trong trẻo
    base_decay = 1.15 + max(0.0, (midi_note - 36) / 72.0) * 2.6

    harmonic_weights = (1.00, 0.54, 0.29, 0.17, 0.10, 0.055, 0.03, 0.015)
    wave_mono = np.zeros(n_samples, dtype=np.float32)
    nyquist_guard = SAMPLE_RATE * 0.42

    for k_idx, weight in enumerate(harmonic_weights, start=1):
        fk = freq * k_idx * math.sqrt(1.0 + inharmonicity_b * (k_idx ** 2))
        if fk >= nyquist_guard:
            break
        # Các bồi âm bậc cao tắt nhanh hơn bồi âm cơ bản -> tạo tiếng đàn ấm dần sau khi gõ
        decay_k = base_decay + 0.85 * (k_idx - 1)
        env_k = 0.72 * np.exp(-t * decay_k) + 0.28 * np.exp(-t * (decay_k * 0.38))
        # Pha hơi lệch tự nhiên giữa các họa âm giúp tránh nhọn đỉnh sóng
        phase = (k_idx - 1) * 0.21
        wave_mono += (weight * env_k) * np.sin(2.0 * math.pi * fk * t + phase)

    # Tiếng búa nỉ chạm dây trong 9ms đầu tiên (tạo độ chân thực của phím cơ)
    strike_len = min(n_samples, int(0.009 * SAMPLE_RATE))
    if strike_len > 8:
        st_t = np.arange(strike_len, dtype=np.float32) / SAMPLE_RATE
        thunk = np.sin(2.0 * math.pi * min(3200.0, freq * 3.5) * st_t) * np.exp(-st_t * 320.0) * 0.12
        wave_mono[:strike_len] += thunk

    # Đường bao Attack (4ms không gây tiếng click) & Release mượt ở cuối đuôi ngân
    attack_env = 1.0 - np.exp(-t / 0.004)
    wave_mono *= attack_env * velocity

    release_samples = min(n_samples // 3, int(0.06 * SAMPLE_RATE))
    if release_samples > 4:
        fade_out = np.linspace(1.0, 0.0, release_samples, dtype=np.float32)
        wave_mono[-release_samples:] *= fade_out

    # Vị trí không gian Stereo giống người ngồi trước đàn Grand Piano (trầm bên trái, cao bên phải)
    pan = max(-0.35, min(0.35, ((midi_note - 60) / 44.0) * 0.35))
    return wave_mono, pan


def _apply_concert_hall_reverb(stereo: np.ndarray, wet: float = 0.18) -> np.ndarray:
    """Thêm vang phòng hòa nhạc nhẹ nhàng (Multi-tap Stereo Hall Reflection)."""
    n_samples = stereo.shape[0]
    out = stereo.copy()
    taps = [
        (int(0.031 * SAMPLE_RATE), 0.38, True),
        (int(0.053 * SAMPLE_RATE), 0.27, False),
        (int(0.089 * SAMPLE_RATE), 0.18, True),
        (int(0.137 * SAMPLE_RATE), 0.11, False),
    ]
    reverb_buf = np.zeros_like(stereo)
    for delay, gain, swap_ch in taps:
        if delay < n_samples:
            src = stereo[:-delay, ::-1] if swap_ch else stereo[:-delay]
            reverb_buf[delay:] += src * gain
    out = out * (1.0 - wet * 0.35) + reverb_buf * wet
    return out


def synthesize_piano_events_to_wav(
    events: List[Tuple[List[int], float]],
    tempo_bpm: int = 108,
    output_path: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Kết xuất danh sách sự kiện nốt nhạc thành file âm thanh `.wav` chuẩn 48kHz 16-bit Stereo.
    Trả về: (đường_dẫn_file_wav, metadata_dict)
    """
    if not events:
        raise ValueError("Danh sách âm tiết / nốt nhạc trống hoặc không hợp lệ.")

    tempo_bpm = max(40, min(240, int(tempo_bpm)))
    sec_per_beat = 60.0 / float(tempo_bpm)

    # Giới hạn tối đa ~60 giây mỗi lần tổng hợp để cực nhanh và nhẹ file Discord
    max_total_sec = 60.0
    total_beats = sum(b for _, b in events)
    est_sec = total_beats * sec_per_beat
    if est_sec > max_total_sec:
        scale = max_total_sec / est_sec
        events = [(m, b * scale) for m, b in events]
        total_beats = sum(b for _, b in events)

    total_duration = total_beats * sec_per_beat + 0.75
    total_samples = int(SAMPLE_RATE * total_duration) + 1
    stereo_mix = np.zeros((total_samples, 2), dtype=np.float32)

    cursor_sec = 0.05
    note_names_preview: List[str] = []
    total_notes_played = 0

    for midis, beats in events:
        dur_sec = beats * sec_per_beat
        start_idx = int(cursor_sec * SAMPLE_RATE)

        if not midis:
            note_names_preview.append("𝄽")
        else:
            chord_label = "+".join(midi_to_note_name(m) for m in midis)
            note_names_preview.append(chord_label)
            # Cân bằng âm lượng khi đánh hợp âm nhiều phím cùng lúc
            chord_vel = 0.85 / math.sqrt(len(midis))
            for idx_m, m in enumerate(midis):
                # Rải nhẹ 6ms giữa các ngón tay khi bấm hợp âm (humanize strumming) cho tự nhiên
                strum_offset = int(idx_m * 0.006 * SAMPLE_RATE) if len(midis) > 1 else 0
                mono_wave, pan = _synthesize_single_piano_key(m, dur_sec, velocity=chord_vel)
                s_pos = start_idx + strum_offset
                e_pos = min(total_samples, s_pos + len(mono_wave))
                if e_pos > s_pos:
                    seg = mono_wave[: e_pos - s_pos]
                    left_gain = math.sqrt(0.5 * (1.0 - pan))
                    right_gain = math.sqrt(0.5 * (1.0 + pan))
                    stereo_mix[s_pos:e_pos, 0] += seg * left_gain
                    stereo_mix[s_pos:e_pos, 1] += seg * right_gain
                    total_notes_played += 1

        cursor_sec += dur_sec

    # Áp dụng Reverb phòng hòa nhạc & Chuẩn hóa biên độ mềm (Soft Limiter chống rè)
    stereo_mix = _apply_concert_hall_reverb(stereo_mix, wet=0.18)
    peak = float(np.max(np.abs(stereo_mix)))
    if peak > 1e-5:
        stereo_mix = stereo_mix / peak * 0.88
    stereo_mix = np.tanh(stereo_mix * 1.12) / math.tanh(1.12) * 0.92

    pcm_int16 = np.clip(stereo_mix * 32767.0, -32768, 32767).astype("<i2")

    if not output_path:
        digest = hashlib.md5(f"{events}_{tempo_bpm}".encode("utf-8")).hexdigest()[:10]
        output_path = os.path.join(AUDIO_CACHE_DIR, f"neneka_piano_{digest}.wav")

    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_int16.tobytes())

    meta = {
        "file_path": output_path,
        "duration_sec": round(total_samples / SAMPLE_RATE, 2),
        "tempo_bpm": tempo_bpm,
        "event_count": len(events),
        "notes_played": total_notes_played,
        "sheet_preview": "  ".join(note_names_preview[:32]) + (" ..." if len(note_names_preview) > 32 else ""),
    }
    return output_path, meta


def find_builtin_piano_piece(query: str) -> Optional[Dict[str, Any]]:
    """Tìm bản nhạc cổ điển / anime có sẵn trong kho nếu khớp tên."""
    if not query:
        return None
    lower = query.lower().strip()
    for key, piece in BUILTIN_PIANO_PIECES.items():
        if key in lower or any(kw in lower for kw in piece["keywords"]):
            return piece
    return None


async def try_generate_lyria_piano_clip(prompt: str) -> Optional[Tuple[str, str]]:
    """
    Thử sinh bản nhạc Piano 44.1kHz bằng Google Lyria (`lyria-3-clip-preview`) qua Interactions API nếu khả dụng.
    Trả về (file_path, model_used) hoặc None nếu key chưa mở quyền Lyria / chạm hạn mức.
    """
    if not settings.GEMINI_API_KEY:
        return None

    def _sync_lyria() -> Optional[bytes]:
        from google import genai
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        interaction = client.interactions.create(
            model="lyria-3-clip-preview",
            input=f"Solo acoustic grand piano instrumental performance, expressive and crystal clear: {prompt}",
        )
        audio_obj = getattr(interaction, "output_audio", None)
        if audio_obj and getattr(audio_obj, "data", None):
            return base64.b64decode(audio_obj.data)
        return None

    try:
        mp3_bytes = await asyncio.wait_for(asyncio.to_thread(_sync_lyria), timeout=25.0)
        if mp3_bytes and len(mp3_bytes) > 1000:
            digest = hashlib.md5(prompt.encode("utf-8")).hexdigest()[:10]
            out_path = os.path.join(AUDIO_CACHE_DIR, f"neneka_lyria_piano_{digest}.mp3")
            with open(out_path, "wb") as f:
                f.write(mp3_bytes)
            return out_path, "Google Lyria 3 Piano AI"
    except Exception as e:
        logger.debug(f"Google Lyria chưa khả dụng cho yêu cầu này ({e}), chuyển sang bộ soạn nốt Grand Piano Synth.")
    return None


async def compose_and_render_piano_melody(
    request_text: str,
    groq_client=None,
    prefer_lyria: bool = False,
) -> Tuple[str, Dict[str, Any]]:
    """
    Tạo bản độc tấu Piano từ chủ đề / tên bài / cảm xúc:
    1. Kiểm tra kho bản nhạc mẫu kinh điển (Canon in D, River Flows in You, Für Elise, Howl's Moving Castle, Clair de Lune, Lost Princess).
    2. Tùy chọn gọi Google Lyria 3 nếu `prefer_lyria=True`.
    3. Dùng LLM soạn chuỗi nốt 2 tay (hợp âm + giai điệu) chuẩn xác và kết xuất qua Concert Grand Piano 48kHz.
    """
    # 1. Khớp bản nhạc kinh điển có sẵn
    builtin = find_builtin_piano_piece(request_text)
    if builtin:
        events = parse_note_sequence(builtin["notes"])
        wav_path, meta = await asyncio.to_thread(
            synthesize_piano_events_to_wav, events, builtin["tempo"]
        )
        meta["title"] = builtin["title"]
        meta["engine"] = "Concert Grand Piano 48kHz Synth (Masterpiece Score)"
        return wav_path, meta

    # 2. Thử Google Lyria nếu được ưu tiên
    if prefer_lyria:
        lyria_res = await try_generate_lyria_piano_clip(request_text)
        if lyria_res:
            out_path, engine_name = lyria_res
            return out_path, {
                "file_path": out_path,
                "title": f"Piano Improvisation — {request_text[:50]}",
                "duration_sec": 30.0,
                "tempo_bpm": 100,
                "notes_played": 0,
                "sheet_preview": "44.1kHz Stereo Studio Piano Track",
                "engine": engine_name,
            }

    # 3. Nhờ LLM biên soạn bản nhạc 2 bè (Hợp âm tay trái + Giai điệu tay phải)
    sys_prompt = (
        "You are a classical & anime concert pianist composer. "
        "Compose a beautiful, melodic 24-to-36-event polyphonic solo piano score matching the user's request. "
        "Return ONLY valid JSON (no markdown fences) with exact keys:\n"
        "{\n"
        '  "title": "Poetic title of the piano piece",\n'
        '  "tempo": 96,\n'
        '  "notes": "Space-separated note/chord tokens with beat durations, e.g. A2+E3+C5:1 E4:1 B4:1 C5:1 F2+C3+A4:2 ..."\n'
        "}\n"
        "Rules for 'notes': Use scientific pitch (C2..C6), combine left-hand bass + right-hand melody with '+' on downbeats (e.g. C3+G3+E5:1.5), and use ':0.5', ':1', ':1.5', ':2' for expressive rhythm."
    )
    title = f"Khúc Dương Cầm Ngẫu Hứng — {request_text[:45]}"
    tempo = 98
    notes_str = ""

    if groq_client and getattr(groq_client, "is_available", False):
        try:
            raw = await groq_client.chat_completion(
                [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": f"Request: {request_text}"},
                ],
                temperature=0.65,
                max_tokens=450,
            )
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            m_json = re.search(r"\{[\s\S]*\}", clean)
            if m_json:
                parsed = json.loads(m_json.group(0))
                title = parsed.get("title") or title
                tempo = int(parsed.get("tempo") or 98)
                notes_str = parsed.get("notes") or ""
        except Exception as e:
            logger.warning(f"LLM soạn nốt piano gặp lỗi nhẹ ({e}), dùng bản nhạc mẫu du dương.")

    events = parse_note_sequence(notes_str) if notes_str else []
    if len(events) < 6:
        fallback_piece = BUILTIN_PIANO_PIECES["river_flows_in_you"]
        events = parse_note_sequence(fallback_piece["notes"])
        tempo = fallback_piece["tempo"]

    wav_path, meta = await asyncio.to_thread(synthesize_piano_events_to_wav, events, tempo)
    meta["title"] = title
    meta["engine"] = "Concert Grand Piano 48kHz Synth"
    return wav_path, meta
