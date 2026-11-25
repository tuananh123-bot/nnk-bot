# src/cogs/voice.py
import asyncio
import os
import random
from typing import Optional, Tuple, Dict, Any, List
import discord
from discord import app_commands
from discord.ext import commands

from src.voice.japanese_tts import japanese_tts, EMOTION_PRESETS
from src.voice.voice_channel import voice_channel_mgr
from src.voice.song_manager import get_song_by_theme_or_random, create_song_embed
from src.voice.piano_engine import (
    is_genuine_note_sequence,
    parse_note_sequence,
    synthesize_piano_events_to_wav,
    compose_and_render_piano_melody,
    BUILTIN_PIANO_PIECES,
)
from src.voice.piano_search import (
    search_piano_songs,
    download_piano_track_audio,
    format_duration_mmss,
)
from src.voice.piano_voice_mixer import (
    OFFICIAL_VOICE_PRESETS,
    SONG_ID_TO_PIANO_PIECE,
    ensure_builtin_or_searched_piano_backing,
    mix_piano_and_voice,
    resolve_official_voice_sample,
)
from src.llm.groq_client import GroqClient

groq_client = GroqClient()

RADIO_LINES = [
    ("ふふっ、また私に会いに来てくれたのね、坊や。", "Affectionate"),
    ("この世界は計算と変貌で満ちているわ。あなたはどう思う？", "Curious"),
    ("あらあら…そんなに急いでどこへ行くのかしら。", "Normal"),
    ("私を観察しようだなんて、いい度胸ね。でも嫌いじゃないわ。", "Sarcastic"),
    ("無理は禁物よ。少し私のそばで休みましょう。", "Affectionate"),
]


def build_piano_track_embed(
    selected_track: Dict[str, Any],
    all_tracks: List[Dict[str, Any]],
    query: str,
) -> discord.Embed:
    """Tạo Embed hiển thị bản nhạc Piano đang phát và danh sách kết quả tìm kiếm."""
    dur_str = format_duration_mmss(selected_track.get("duration_sec", 0))
    mode_tag = "Full Track" if selected_track.get("is_full_track") else "Audio Stream"

    embed = discord.Embed(
        title=f"🎹 {selected_track.get('title', 'Bản Nhạc Piano')}",
        description=(
            f"👤 **Nghệ sĩ:** {selected_track.get('artist', 'Unknown Pianist')}\n"
            f"💿 **Album:** {selected_track.get('album') or 'Solo Piano Collection'}\n"
            f"⏱️ **Thời lượng gốc:** `{dur_str}` • **Nguồn:** `{selected_track.get('source', 'Piano Cloud')}` ({mode_tag})\n"
            f"🔗 [Mở Bản Đầy Đủ]({selected_track.get('page_url')}) • [Tìm Trên YouTube Piano]({selected_track.get('youtube_url')})"
        ),
        color=0x9b59b6,
    )
    if selected_track.get("artwork_url"):
        embed.set_thumbnail(url=selected_track["artwork_url"])

    if len(all_tracks) > 1:
        lines = []
        for idx, t in enumerate(all_tracks[:5], start=1):
            t_dur = format_duration_mmss(t.get("duration_sec", 0))
            marker = "▶️" if t is selected_track else f"`{idx}.`"
            lines.append(f"{marker} **{t['title'][:45]}** — *{t['artist'][:28]}* (`{t_dur}`)")
        embed.add_field(
            name=f"🎼 Các Bản Piano Tìm Thấy Cho '{query}' (Chọn bên dưới để đổi bài)",
            value="\n".join(lines),
            inline=False,
        )

    embed.set_footer(text="Neneka Global Piano Search • Bấm nút bên dưới để lồng thêm Voice Line của Neneka!")
    return embed


def build_piano_synth_embed(meta: Dict[str, Any], subtitle: str = "") -> discord.Embed:
    """Tạo Embed hiển thị thông tin bản nhạc / chuỗi âm tiết Piano vừa được tổng hợp."""
    title = meta.get("title") or "Khúc Độc Tấu Đại Dương Cầm (48kHz Stereo)"
    embed = discord.Embed(
        title=f"🎹 {title}",
        description=subtitle or "Giai điệu vừa được tổng hợp trực tiếp trên đàn Concert Grand Piano của ta ✨",
        color=0x8e44ad,
    )
    embed.add_field(name="🎼 Bản Phổ Nốt / Âm Tiết", value=f"`{meta.get('sheet_preview', 'C4 D4 E4 G4')}`", inline=False)
    embed.add_field(name="⏱️ Thời Lượng", value=f"`{meta.get('duration_sec', 0)} giây`", inline=True)
    embed.add_field(name="🎚️ Nhịp Độ (Tempo)", value=f"`{meta.get('tempo_bpm', 108)} BPM`", inline=True)
    if meta.get("notes_played"):
        embed.add_field(name="🎹 Số Phím Ngân", value=f"`{meta['notes_played']} phím`", inline=True)
    embed.set_footer(text=f"{meta.get('engine', 'Concert Grand Piano 48kHz Synth')} • Phát trực tiếp trên Chat & Voice")
    return embed


def build_concert_duet_embed(
    piano_title: str,
    voice_label: str,
    jp_line: str,
    vi_line: str,
    mix_meta: Dict[str, Any],
) -> discord.Embed:
    """Tạo Embed sang trọng cho bản hòa âm hoàn chỉnh giữa Piano & Voice Line của Neneka."""
    dur_str = format_duration_mmss(int(mix_meta.get("duration_sec", 0)))
    mode_desc = "Trọn bài Piano Full-Length + Voice Line" if mix_meta.get("keep_full_piano") else "Hòa âm Phòng thu theo nhịp thoại (Intro + Ducking + Outro)"
    embed = discord.Embed(
        title="👑🎹 Buổi Hòa Nhạc Thất Vương • Piano & Neneka Voice Line",
        description=(
            "*Tiếng Đại Dương Cầm ngân vang hòa quyện cùng thanh âm biến mạo của Utsushimi Neneka trong cùng một không gian thính phòng...*"
        ),
        color=0x9b59b6,
    )
    embed.add_field(name="🎹 Bản Nhạc Piano Nền", value=f"**{piano_title}**", inline=False)
    embed.add_field(name="🎙️ Voice Line Kết Hợp", value=f"**{voice_label}**", inline=False)
    if jp_line:
        embed.add_field(name="🇯🇵 Lời Thoại / Lời Ca (Japanese)", value=f"「*{jp_line}*」", inline=False)
    if vi_line:
        embed.add_field(name="🇻🇳 Ý Nghĩa (Tiếng Việt)", value=f"*{vi_line}*", inline=False)
    embed.add_field(
        name="🎚️ Thông Số Hòa Âm (48kHz Stereo 192kbps)",
        value=f"⏱️ Tổng thời lượng: `{dur_str}` (`{mix_meta.get('duration_sec', 0)}s`) • Chế độ: `{mode_desc}`",
        inline=False,
    )
    embed.set_footer(text="Neneka Concert Studio • Sidechain Ducking & Hall Mastering • Đổi Voice Line ở menu dưới!")
    return embed


class ConcertVoiceSwitchSelect(discord.ui.Select):
    """Menu đổi nhanh giữa 5 Voice Line gốc của Neneka ngay trên nền bản nhạc Piano vừa chọn."""

    def __init__(self, piano_path: str, piano_title: str, keep_full_piano: bool, guild_id: Optional[int]):
        self.piano_path = piano_path
        self.piano_title = piano_title
        self.keep_full_piano = keep_full_piano
        self.guild_id = guild_id
        options = [
            discord.SelectOption(
                label=info["label"][:95],
                description=info["vi_text"][:95],
                value=key,
            )
            for key, info in OFFICIAL_VOICE_PRESETS.items()
        ]
        super().__init__(
            placeholder="🎙️ Đổi sang Voice Line khác của Neneka trên nền bài Piano này...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        preset_key = self.values[0]
        v_path, preset = resolve_official_voice_sample(preset_key)
        if not v_path:
            await interaction.followup.send("❌ Không tìm thấy tệp Voice Line gốc.", ephemeral=True)
            return

        max_v = float(preset.get("max_sec", "45"))
        mixed_path, mix_meta = await mix_piano_and_voice(
            piano_path=self.piano_path,
            voice_path=v_path,
            keep_full_piano=self.keep_full_piano,
            max_voice_sec=max_v,
        )
        if self.guild_id and os.path.exists(mixed_path):
            vc = voice_channel_mgr.get_voice_client(self.guild_id)
            if vc and vc.is_connected():
                await voice_channel_mgr.enqueue_audio(self.guild_id, mixed_path)

        embed = build_concert_duet_embed(
            piano_title=self.piano_title,
            voice_label=preset["label"],
            jp_line=preset["jp_text"],
            vi_line=preset["vi_text"],
            mix_meta=mix_meta,
        )
        ext = "mp3" if mixed_path.lower().endswith(".mp3") else "wav"
        await interaction.followup.send(
            embed=embed,
            file=discord.File(mixed_path, filename=f"neneka_concert_{preset_key}.{ext}"),
        )


class ConcertVoiceSwitchView(discord.ui.View):
    def __init__(self, piano_path: str, piano_title: str, keep_full_piano: bool, guild_id: Optional[int]):
        super().__init__(timeout=240)
        if piano_path and os.path.exists(piano_path):
            self.add_item(ConcertVoiceSwitchSelect(piano_path, piano_title, keep_full_piano, guild_id))


class PianoTrackSelect(discord.ui.Select):
    """Menu thả xuống cho phép người dùng chọn phát bất kỳ bản Piano nào trong danh sách tìm được."""

    def __init__(self, tracks: List[Dict[str, Any]], query: str, guild_id: Optional[int], parent_view: "PianoTrackSelectView"):
        self.tracks = tracks[:5]
        self.query = query
        self.guild_id = guild_id
        self.parent_view = parent_view
        options = [
            discord.SelectOption(
                label=f"{idx}. {t['title'][:85]}",
                description=f"{t['artist'][:50]} • {format_duration_mmss(t.get('duration_sec', 0))}"[:100],
                value=str(idx - 1),
                emoji="🎹",
            )
            for idx, t in enumerate(self.tracks, start=1)
        ]
        super().__init__(
            placeholder="🎹 Chọn một phiên bản Piano khác để nghe ngay...",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        idx = int(self.values[0])
        chosen = self.tracks[idx]
        audio_path = await download_piano_track_audio(chosen)
        if not audio_path or not os.path.exists(audio_path):
            audio_path, _ = await compose_and_render_piano_melody(
                chosen.get("title") or self.query, groq_client=groq_client
            )
            chosen["audio_ext"] = "mp3" if audio_path.lower().endswith(".mp3") else "wav"

        self.parent_view.current_audio_path = audio_path
        self.parent_view.current_title = f"{chosen.get('title', self.query)} — {chosen.get('artist', 'Solo Piano')}"
        embed = build_piano_track_embed(chosen, self.tracks, self.query)

        if audio_path and os.path.exists(audio_path):
            if self.guild_id:
                vc = voice_channel_mgr.get_voice_client(self.guild_id)
                if vc and vc.is_connected():
                    await voice_channel_mgr.enqueue_audio(self.guild_id, audio_path)
            ext = chosen.get("audio_ext", "mp3")
            d_file = discord.File(audio_path, filename=f"neneka_piano_{idx + 1}.{ext}")
            await interaction.followup.send(embed=embed, file=d_file, view=self.parent_view)
        else:
            await interaction.followup.send(embed=embed)


class PianoTrackSelectView(discord.ui.View):
    """View kèm theo mỗi kết quả `/piano`: vừa đổi bài Piano, vừa bấm 1 nút để ghép ngay Voice Line của Neneka!"""

    def __init__(
        self,
        tracks: List[Dict[str, Any]],
        query: str,
        guild_id: Optional[int],
        current_audio_path: Optional[str] = None,
        current_title: Optional[str] = None,
    ):
        super().__init__(timeout=240)
        self.tracks = tracks
        self.query = query
        self.guild_id = guild_id
        self.current_audio_path = current_audio_path
        first = tracks[0] if tracks else {}
        self.current_title = current_title or f"{first.get('title', query)} — {first.get('artist', 'Solo Piano')}"
        if len(tracks) > 1:
            self.add_item(PianoTrackSelect(tracks, query, guild_id, self))

    @discord.ui.button(
        label="🎙️ Kết Hợp Voice Line Neneka Vào Bài Này",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def btn_mix_neneka_voice(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        piano_path = self.current_audio_path
        if not piano_path or not os.path.exists(piano_path):
            if self.tracks:
                piano_path = await download_piano_track_audio(self.tracks[0])
        if not piano_path or not os.path.exists(piano_path):
            piano_path, _ = await ensure_builtin_or_searched_piano_backing(self.query, prefer_search=False)

        v_path, preset = resolve_official_voice_sample("canon_short")
        if not v_path:
            await interaction.followup.send("❌ Chưa tìm thấy file Voice Line mẫu của Neneka.", ephemeral=True)
            return

        mixed_path, mix_meta = await mix_piano_and_voice(
            piano_path=piano_path,
            voice_path=v_path,
            keep_full_piano=True,
            max_voice_sec=32.0,
        )
        if self.guild_id and os.path.exists(mixed_path):
            vc = voice_channel_mgr.get_voice_client(self.guild_id)
            if vc and vc.is_connected():
                await voice_channel_mgr.enqueue_audio(self.guild_id, mixed_path)

        embed = build_concert_duet_embed(
            piano_title=self.current_title,
            voice_label=preset["label"],
            jp_line=preset["jp_text"],
            vi_line=preset["vi_text"],
            mix_meta=mix_meta,
        )
        switch_view = ConcertVoiceSwitchView(piano_path, self.current_title, True, self.guild_id)
        ext = "mp3" if mixed_path.lower().endswith(".mp3") else "wav"
        await interaction.followup.send(
            embed=embed,
            file=discord.File(mixed_path, filename=f"neneka_piano_voice.{ext}"),
            view=switch_view,
        )


class VoiceCog(commands.Cog):
    """Quản lý kết nối phòng thoại Discord, Japanese TTS, Đại Dương Cầm 48kHz & Phòng Thu Hòa Âm Piano + Voice Line"""

    def __init__(self, bot):
        self.bot = bot

    async def _auto_join_user_voice(self, guild: Optional[discord.Guild], member) -> Optional[int]:
        """Tự động vào phòng thoại của người dùng nếu họ đang ở trong Voice Channel."""
        if not guild or not member or not getattr(member, "voice", None) or not member.voice.channel:
            return guild.id if guild else None
        vc = voice_channel_mgr.get_voice_client(guild.id)
        if not vc or not vc.is_connected():
            await voice_channel_mgr.join_channel(member.voice.channel)
        return guild.id

    async def _translate_to_japanese_line(self, text: str) -> Tuple[str, bool]:
        """Chuyển câu tiếng Việt/Anh sang thoại tiếng Nhật chuẩn thần thái Neneka."""
        clean_text = text.strip()
        is_ja = any(("\u3040" <= c <= "\u30ff") or ("\u4e00" <= c <= "\u9fff") for c in clean_text)
        if is_ja:
            return clean_text, True
        prompt = (
            "Bạn là Utsushimi Neneka (Seven Crowns trong Princess Connect! Re:Dive). "
            f'Hãy dịch câu sau sang lời thoại tiếng Nhật anime quý phái, tự nhiên của Neneka: "{clean_text}". '
            "Chỉ trả về đúng 1 câu tiếng Nhật duy nhất (kanji/kana), không giải thích."
        )
        try:
            res = await groq_client.chat_completion([{"role": "user", "content": prompt}], max_tokens=120)
            ja = res.strip().strip('"').strip("「」")
            if ja:
                return ja, False
        except Exception:
            pass
        return "ふふっ、私の調べと声を、心ゆくまで堪能なさい。", False

    async def _handle_speak(
        self,
        text: str,
        emotion: str = "Normal",
        guild_id: Optional[int] = None,
        with_piano_bg: bool = False,
    ):
        """Xử lý dịch câu thoại, sinh giọng Neneka (tùy chọn hòa âm cùng nhạc nền Piano) và đẩy vào Voice Channel."""
        ja_text, is_ja = await self._translate_to_japanese_line(text)
        audio_file = await japanese_tts.generate_speech(ja_text, emotion=emotion)
        if not audio_file or not os.path.exists(audio_file):
            return None, ja_text, is_ja

        if with_piano_bg:
            try:
                piano_path, _ = await ensure_builtin_or_searched_piano_backing("lost_princess_piano", prefer_search=False)
                audio_file, _ = await mix_piano_and_voice(
                    piano_path=piano_path,
                    voice_path=audio_file,
                    intro_sec=1.8,
                    outro_sec=3.2,
                )
            except Exception:
                pass

        if guild_id and os.path.exists(audio_file):
            vc = voice_channel_mgr.get_voice_client(guild_id)
            if vc and vc.is_connected():
                await voice_channel_mgr.enqueue_audio(guild_id, audio_file)

        return audio_file, ja_text, is_ja

    async def _handle_sing(
        self,
        theme: Optional[str] = None,
        guild_id: Optional[int] = None,
    ) -> Tuple[Optional[str], Dict[str, str], str, Dict[str, Any]]:
        """
        Chọn/sáng tác bài hát phong cách Nhật Bản của Neneka VÀ hòa âm hoàn chỉnh trên nền Đại Dương Cầm 48kHz!
        Trả về `(mixed_audio_file, song_dict, piano_title, mix_meta)`.
        """
        song = await get_song_by_theme_or_random(theme)
        lyrics = song["japanese_lyrics"]
        emotion = song.get("emotion", "Affectionate")

        vocal_file = await japanese_tts.generate_speech(lyrics, emotion=emotion)
        if not vocal_file or not os.path.exists(vocal_file):
            vocal_file, _ = resolve_official_voice_sample("canon_short")

        if not vocal_file or not os.path.exists(vocal_file):
            return None, song, "", {}

        piece_key = SONG_ID_TO_PIANO_PIECE.get(song.get("id", ""), "")
        piano_path, piano_title = await ensure_builtin_or_searched_piano_backing(
            piece_key or theme or "lost_princess_piano",
            prefer_search=False,
        )

        try:
            mixed_file, mix_meta = await mix_piano_and_voice(
                piano_path=piano_path,
                voice_path=vocal_file,
                intro_sec=2.4,
                outro_sec=4.0,
                piano_base_gain=0.58,
                piano_ducked_gain=0.24,
                voice_gain=0.95,
            )
        except Exception:
            mixed_file, mix_meta = vocal_file, {}

        if guild_id and mixed_file and os.path.exists(mixed_file):
            vc = voice_channel_mgr.get_voice_client(guild_id)
            if vc and vc.is_connected():
                await voice_channel_mgr.enqueue_audio(guild_id, mixed_file)

        return mixed_file, song, piano_title, mix_meta

    async def handle_piano_voice_concert(
        self,
        piano_query: Optional[str] = None,
        voice_preset_or_text: Optional[str] = None,
        keep_full_piano: bool = False,
        guild_id: Optional[int] = None,
    ) -> Tuple[str, str, discord.Embed, Optional[discord.ui.View]]:
        """
        Tạo bản biểu diễn hoàn chỉnh kết hợp **Đàn Piano (Full-Length hoặc Synth 48kHz)** + **Voice Line của Neneka**:
        - Nếu `voice_preset_or_text` trùng mã preset (`canon_short`, `canon_full`, `metamorph`, `affection`, `story_memory`) hoặc để trống:
          dùng ngay Voice Line gốc chính thức của Yuka Iguchi trong `assets/voice_samples`!
        - Nếu `voice_preset_or_text` là `"sing"` / `"hat"`: ghép lời hát tiếng Nhật của Neneka!
        - Nếu `voice_preset_or_text` là câu chữ tự do (tiếng Việt/Nhật/Anh): tự dịch sang thoại tiếng Nhật của Neneka, tạo giọng nói và hòa âm trên nền bài Piano đã chọn!
        """
        target_piano = (piano_query or "").strip() or "Lost Princess"
        piano_path, piano_title = await ensure_builtin_or_searched_piano_backing(
            target_piano,
            prefer_search=True,
        )

        v_spec = (voice_preset_or_text or "").strip()
        v_key_lower = v_spec.lower()

        if not v_spec or v_key_lower in OFFICIAL_VOICE_PRESETS:
            chosen_key = v_key_lower if v_key_lower in OFFICIAL_VOICE_PRESETS else "canon_short"
            voice_path, preset = resolve_official_voice_sample(chosen_key)
            voice_label = preset["label"]
            jp_line = preset["jp_text"]
            vi_line = preset["vi_text"]
            max_v_sec = float(preset.get("max_sec", "45"))
        elif v_key_lower in {"sing", "hat", "hát", "song"}:
            song = await get_song_by_theme_or_random(target_piano)
            voice_path = await japanese_tts.generate_speech(song["japanese_lyrics"], emotion=song.get("emotion", "Affectionate"))
            if not voice_path or not os.path.exists(voice_path):
                voice_path, _ = resolve_official_voice_sample("canon_short")
            voice_label = f"🎵 Giọng Hát Neneka — {song.get('title', 'Khúc Ca Landosol')}"
            jp_line = song.get("japanese_lyrics", "")
            vi_line = song.get("vietnamese_lyrics", "")
            max_v_sec = 60.0
        else:
            ja_text, is_ja = await self._translate_to_japanese_line(v_spec)
            voice_path = await japanese_tts.generate_speech(ja_text, emotion="Affectionate")
            if not voice_path or not os.path.exists(voice_path):
                voice_path, preset = resolve_official_voice_sample("canon_short")
                voice_label = preset["label"]
                jp_line = preset["jp_text"]
                vi_line = preset["vi_text"]
            else:
                voice_label = "🗣️ Thoại Neneka Tùy Biến (Fish Audio / Neural Japanese Voice)"
                jp_line = ja_text
                vi_line = v_spec if not is_ja else ""
            max_v_sec = 65.0

        mixed_path, mix_meta = await mix_piano_and_voice(
            piano_path=piano_path,
            voice_path=voice_path,
            intro_sec=2.5,
            outro_sec=4.0,
            keep_full_piano=keep_full_piano,
            max_voice_sec=max_v_sec,
        )

        if guild_id and os.path.exists(mixed_path):
            vc = voice_channel_mgr.get_voice_client(guild_id)
            if vc and vc.is_connected():
                await voice_channel_mgr.enqueue_audio(guild_id, mixed_path)

        embed = build_concert_duet_embed(
            piano_title=piano_title,
            voice_label=voice_label,
            jp_line=jp_line,
            vi_line=vi_line,
            mix_meta=mix_meta,
        )
        view = ConcertVoiceSwitchView(piano_path, piano_title, keep_full_piano, guild_id)
        ext = "mp3" if mixed_path.lower().endswith(".mp3") else "wav"
        return mixed_path, f"neneka_concert.{ext}", embed, view

    async def handle_piano_notes(
        self,
        sequence_or_theme: str,
        tempo: int = 108,
        guild_id: Optional[int] = None,
    ) -> Tuple[str, str, discord.Embed, Optional[discord.ui.View]]:
        """
        Tạo âm tiết / đánh chuỗi nốt nhạc Piano (hoặc tự động chuyển sang tìm bài nhạc Piano đầy đủ nếu người dùng nhập tên bài hát / tên game!).
        """
        clean_input = sequence_or_theme.strip()
        if is_genuine_note_sequence(clean_input):
            events = parse_note_sequence(clean_input)
            valid_notes = [e for e in events if e[0]]
            if len(valid_notes) == 1 and len(events) == 1:
                root_m = valid_notes[0][0][0]
                events = [([root_m], 2.5)]

            wav_path, meta = await asyncio.to_thread(synthesize_piano_events_to_wav, events, tempo)
            meta["title"] = "Tổng Hợp Âm Tiết Đại Dương Cầm (48kHz Stereo)"
            meta["engine"] = "Concert Grand Piano 48kHz Synth"
            subtitle = f"Chuỗi âm tiết đã kết xuất ({meta['notes_played']} phím ngân): `{clean_input[:120]}` 🎹"

            if guild_id and os.path.exists(wav_path):
                vc = voice_channel_mgr.get_voice_client(guild_id)
                if vc and vc.is_connected():
                    await voice_channel_mgr.enqueue_audio(guild_id, wav_path)

            embed = build_piano_synth_embed(meta, subtitle=subtitle)
            view = ConcertVoiceSwitchView(wav_path, meta["title"], False, guild_id)
            return wav_path, "neneka_piano_notes.wav", embed, view

        audio_path, fname, embed, view = await self.handle_piano_search(clean_input, guild_id=guild_id)
        return audio_path or "", fname, embed, view

    async def handle_piano_search(
        self,
        query: str,
        guild_id: Optional[int] = None,
    ) -> Tuple[Optional[str], str, discord.Embed, Optional[discord.ui.View]]:
        """
        Tìm kiếm toàn bộ bài nhạc tiếng Piano Full-Length (kèm nút ghép trực tiếp Voice Line của Neneka).
        """
        tracks = await search_piano_songs(query, limit=5)
        if tracks:
            chosen = None
            audio_path = None
            for candidate in tracks:
                dl = await download_piano_track_audio(candidate)
                if dl and os.path.exists(dl):
                    chosen = candidate
                    audio_path = dl
                    break

            if chosen and audio_path:
                if guild_id:
                    vc = voice_channel_mgr.get_voice_client(guild_id)
                    if vc and vc.is_connected():
                        await voice_channel_mgr.enqueue_audio(guild_id, audio_path)
                ext = chosen.get("audio_ext", "mp3")
                embed = build_piano_track_embed(chosen, tracks, query)
                cur_title = f"{chosen.get('title', query)} — {chosen.get('artist', 'Solo Piano')}"
                view = PianoTrackSelectView(tracks, query, guild_id, current_audio_path=audio_path, current_title=cur_title)
                return audio_path, f"neneka_piano.{ext}", embed, view

        wav_path, meta = await compose_and_render_piano_melody(
            query, groq_client=groq_client, prefer_lyria=True
        )
        if guild_id and os.path.exists(wav_path):
            vc = voice_channel_mgr.get_voice_client(guild_id)
            if vc and vc.is_connected():
                await voice_channel_mgr.enqueue_audio(guild_id, wav_path)
        ext = "mp3" if wav_path.lower().endswith(".mp3") else "wav"
        embed = build_piano_synth_embed(
            meta,
            subtitle=f"Không tìm thấy bản thu thương mại khớp `{query}`, nên ta tự dạo bản Piano này tặng cậu luôn nhé 🎹✨",
        )
        view = ConcertVoiceSwitchView(wav_path, meta.get("title", query), False, guild_id)
        return wav_path, f"neneka_piano_solo.{ext}", embed, view

    # =========================================================================
    # SLASH COMMANDS
    # =========================================================================
    @app_commands.command(
        name="concert",
        description="👑🎹 Hòa âm hoàn chỉnh Đàn Piano + Voice Line gốc / Giọng nói của Neneka trong 1 bản thu Stereo",
    )
    @app_commands.describe(
        piano_song="Tên bài hát / nhạc Game Piano muốn làm nền (VD: Lost Princess, Unravel, River Flows in You, Suzume...)",
        voice_preset="Chọn Voice Line gốc của Neneka (Yuka Iguchi) hoặc chế độ hát",
        custom_line="Hoặc tự nhập câu thoại tiếng Việt/Nhật bất kỳ để Neneka cất giọng trên nền bài Piano đó",
        full_song="Giữ trọn độ dài cả bài Piano Full-Length (True) hay cắt gọn vừa khớp câu thoại (False)",
    )
    @app_commands.choices(
        voice_preset=[
            app_commands.Choice(name="👑 Thoại Thất Vương Tinh Tuyển (Yuka Iguchi — 25s)", value="canon_short"),
            app_commands.Choice(name="👑 5 Câu Thoại Kinh Điển Đầy Đủ (Yuka Iguchi — 60s)", value="canon_full"),
            app_commands.Choice(name="🔮 Thanh Âm Ma Pháp Biến Mạo (Metamorphose)", value="metamorph"),
            app_commands.Choice(name="💜 Lời Tâm Tình Dịu Dàng Của Neneka", value="affection"),
            app_commands.Choice(name="📖 Độc Thoại Ký Ức Cốt Truyện (45s)", value="story_memory"),
            app_commands.Choice(name="🎵 Neneka Hát Theo Chủ Đề Bài Nhạc", value="sing"),
        ]
    )
    async def cmd_concert(
        self,
        interaction: discord.Interaction,
        piano_song: Optional[str] = "Lost Princess",
        voice_preset: Optional[str] = "canon_short",
        custom_line: Optional[str] = None,
        full_song: Optional[bool] = False,
    ):
        await interaction.response.defer()
        guild_id = await self._auto_join_user_voice(interaction.guild, interaction.user)
        voice_target = custom_line.strip() if (custom_line and custom_line.strip()) else (voice_preset or "canon_short")
        audio_path, fname, embed, view = await self.handle_piano_voice_concert(
            piano_query=piano_song,
            voice_preset_or_text=voice_target,
            keep_full_piano=bool(full_song),
            guild_id=guild_id,
        )
        send_kwargs: Dict[str, Any] = {"embed": embed}
        if audio_path and os.path.exists(audio_path):
            send_kwargs["file"] = discord.File(audio_path, filename=fname)
        if view:
            send_kwargs["view"] = view
        await interaction.followup.send(**send_kwargs)

    @app_commands.command(name="piano", description="🎹 Tìm kiếm và phát bất kỳ bài nhạc tiếng Piano nào (kèm nút ghép Voice Line Neneka)")
    @app_commands.describe(query="Tên bài hát, nhạc Game hoặc nghệ sĩ Piano cần tìm (ví dụ: Lost Princess, Unravel, Suzume, Chopin...)")
    async def cmd_piano(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        guild_id = await self._auto_join_user_voice(interaction.guild, interaction.user)
        audio_path, fname, embed, view = await self.handle_piano_search(query, guild_id=guild_id)

        send_kwargs: Dict[str, Any] = {"embed": embed}
        if audio_path and os.path.exists(audio_path):
            send_kwargs["file"] = discord.File(audio_path, filename=fname)
        if view:
            send_kwargs["view"] = view
        await interaction.followup.send(**send_kwargs)

    @app_commands.command(name="notes", description="🎼 Tạo âm tiết & đánh chuỗi nốt nhạc trên đàn Đại Dương Cầm 48kHz")
    @app_commands.describe(
        sequence="Chuỗi âm tiết/nốt nhạc (VD: 'Đô Rê Mi Pha Sol La Si Đô5', 'C4 E4 G4 C5', cảm âm '1 1 5 5 6 6 5', hợp âm 'Cmaj Am F G')",
        tempo="Nhịp độ BPM (từ 40 đến 240, mặc định 108)",
    )
    async def cmd_notes(
        self,
        interaction: discord.Interaction,
        sequence: str,
        tempo: Optional[int] = 108,
    ):
        await interaction.response.defer()
        guild_id = await self._auto_join_user_voice(interaction.guild, interaction.user)
        audio_path, fname, embed, view = await self.handle_piano_notes(sequence, tempo=tempo or 108, guild_id=guild_id)
        send_kwargs: Dict[str, Any] = {"embed": embed}
        if audio_path and os.path.exists(audio_path):
            send_kwargs["file"] = discord.File(audio_path, filename=fname)
        if view:
            send_kwargs["view"] = view
        await interaction.followup.send(**send_kwargs)

    @app_commands.command(name="piano_compose", description="✨ Nhờ Neneka sáng tác hoặc độc tấu một bản nhạc Piano theo chủ đề/tâm trạng")
    @app_commands.describe(
        theme="Chủ đề cảm xúc hoặc tên tác phẩm kinh điển (VD: Canon in D, đêm mưa buồn, Howl's Moving Castle, Clair de Lune...)",
        ai_studio="Thử dùng Google Lyria 3 Studio AI nếu khả dụng (mặc định: Tự động)",
    )
    async def cmd_piano_compose(
        self,
        interaction: discord.Interaction,
        theme: str,
        ai_studio: Optional[bool] = True,
    ):
        await interaction.response.defer()
        guild_id = await self._auto_join_user_voice(interaction.guild, interaction.user)
        out_path, meta = await compose_and_render_piano_melody(
            theme, groq_client=groq_client, prefer_lyria=bool(ai_studio)
        )
        if guild_id and os.path.exists(out_path):
            vc = voice_channel_mgr.get_voice_client(guild_id)
            if vc and vc.is_connected():
                await voice_channel_mgr.enqueue_audio(guild_id, out_path)

        ext = "mp3" if out_path.lower().endswith(".mp3") else "wav"
        embed = build_piano_synth_embed(meta, subtitle=f"Độc tấu dương cầm theo yêu cầu: *{theme}* 🎹💜")
        view = ConcertVoiceSwitchView(out_path, meta.get("title", theme), False, guild_id)
        await interaction.followup.send(embed=embed, file=discord.File(out_path, filename=f"neneka_solo.{ext}"), view=view)

    @app_commands.command(name="join", description="🔊 Mời Neneka tham gia phòng thoại (Voice Channel) của bạn")
    async def cmd_join(self, interaction: discord.Interaction):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ Bạn cần tham gia vào một phòng thoại trước khi gọi Neneka!", ephemeral=True)
            return

        channel = interaction.user.voice.channel
        success, msg, _ = await voice_channel_mgr.join_channel(channel)
        if success:
            await interaction.response.send_message(f"👑 {msg}")
        else:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)

    @app_commands.command(name="leave", description="👋 Cho Neneka rời khỏi phòng thoại hiện tại")
    async def cmd_leave(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ Lệnh này chỉ khả dụng trong máy chủ Discord.", ephemeral=True)
            return

        success, msg = await voice_channel_mgr.leave_channel(interaction.guild.id)
        if success:
            await interaction.response.send_message(f"👋 {msg}")
        else:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)

    @app_commands.command(name="speak", description="🎙️ Yêu cầu Neneka cất giọng tiếng Nhật (có tùy chọn đệm đàn Piano nền)")
    @app_commands.describe(
        text="Văn bản tiếng Nhật hoặc tiếng Việt cần phát âm",
        emotion="Cảm xúc biểu đạt của giọng nói",
        with_piano="Đệm thêm tiếng đàn Đại Dương Cầm dịu nhẹ phía sau giọng nói (mặc định: False)",
    )
    @app_commands.choices(emotion=[
        app_commands.Choice(name=f"✨ {k}", value=k) for k in EMOTION_PRESETS.keys()
    ])
    async def cmd_speak(
        self,
        interaction: discord.Interaction,
        text: str,
        emotion: Optional[str] = "Normal",
        with_piano: Optional[bool] = False,
    ):
        await interaction.response.defer()

        guild_id = await self._auto_join_user_voice(interaction.guild, interaction.user)
        audio_file, ja_text, is_ja = await self._handle_speak(
            text, emotion=emotion or "Normal", guild_id=guild_id, with_piano_bg=bool(with_piano)
        )
        if not audio_file:
            await interaction.followup.send("❌ Không thể tạo giọng nói vào thời điểm này.")
            return

        discord_file = discord.File(audio_file, filename="neneka_voice.mp3")
        piano_tag = " *(kèm đệm đàn Grand Piano)*" if with_piano else ""
        display_msg = f"🗣️ **Neneka cất giọng{piano_tag}:**\n🇯🇵 **「{ja_text}」**"
        if not is_ja:
            display_msg = f'🇻🇳 *"{text}"*\n' + display_msg
        await interaction.followup.send(display_msg, file=discord_file)

    @app_commands.command(name="sing", description="🎵 Yêu cầu Neneka cất giọng hát hòa âm cùng tiếng Đàn Dương Cầm 48kHz")
    @app_commands.describe(theme="Chủ đề hoặc phong cách bài hát (ví dụ: lost princess, ru ngủ, tình yêu, hoa anh đào, vui tươi...)")
    async def cmd_sing(self, interaction: discord.Interaction, theme: Optional[str] = None):
        await interaction.response.defer()
        guild_id = await self._auto_join_user_voice(interaction.guild, interaction.user)

        audio_file, song, piano_title, mix_meta = await self._handle_sing(theme=theme, guild_id=guild_id)
        if not audio_file:
            await interaction.followup.send("❌ Không thể cất giọng hát vào thời điểm này.")
            return

        embed = create_song_embed(song, piano_title=piano_title, duration_sec=mix_meta.get("duration_sec"))
        discord_file = discord.File(audio_file, filename="neneka_singing_piano.mp3")
        await interaction.followup.send(embed=embed, file=discord_file)

    @app_commands.command(name="radio", description="📻 Phát câu thoại radio ngẫu nhiên của Neneka trên nền Dương Cầm")
    async def cmd_radio(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild_id = await self._auto_join_user_voice(interaction.guild, interaction.user)

        line, emo = random.choice(RADIO_LINES)
        audio_file = await japanese_tts.generate_speech(line, emotion=emo)
        if not audio_file or not os.path.exists(audio_file):
            audio_file, _ = resolve_official_voice_sample("affection")

        if audio_file and os.path.exists(audio_file):
            try:
                piano_path, _ = await ensure_builtin_or_searched_piano_backing("river_flows_in_you", prefer_search=False)
                audio_file, _ = await mix_piano_and_voice(
                    piano_path=piano_path,
                    voice_path=audio_file,
                    intro_sec=1.8,
                    outro_sec=3.2,
                )
            except Exception:
                pass
            if guild_id:
                vc = voice_channel_mgr.get_voice_client(guild_id)
                if vc and vc.is_connected():
                    await voice_channel_mgr.enqueue_audio(guild_id, audio_file)
            await interaction.followup.send(
                f"📻🎹 **Đang phát Radio Dương Cầm:** 「{line}」 *(Cảm xúc: {emo})*",
                file=discord.File(audio_file, filename="neneka_piano_radio.mp3"),
            )
        else:
            await interaction.followup.send("❌ Có lỗi khi tạo âm thanh radio.")

    @app_commands.command(name="quote", description="👑 Phát 5 câu thoại kinh điển của Neneka (Yuka Iguchi) hòa âm trên nền Piano Lost Princess")
    async def cmd_quote(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild_id = await self._auto_join_user_voice(interaction.guild, interaction.user)
        quote_file, _ = resolve_official_voice_sample("canon_full")
        if not quote_file:
            await interaction.followup.send("❌ Không tìm thấy file âm thanh câu thoại của Neneka.")
            return

        piano_path, piano_title = await ensure_builtin_or_searched_piano_backing("lost_princess_piano", prefer_search=False)
        try:
            final_audio, mix_meta = await mix_piano_and_voice(
                piano_path=piano_path,
                voice_path=quote_file,
                intro_sec=2.4,
                outro_sec=4.0,
                max_voice_sec=65.0,
            )
        except Exception:
            final_audio, mix_meta = quote_file, {}

        if guild_id and os.path.exists(final_audio):
            vc = voice_channel_mgr.get_voice_client(guild_id)
            if vc and vc.is_connected():
                await voice_channel_mgr.enqueue_audio(guild_id, final_audio)

        embed = discord.Embed(
            title="👑🎹 Utsushimi Neneka — Metamorph Regnant (Thoại Gốc & Dương Cầm)",
            description=(
                "**🇯🇵 Trích đoạn thoại kinh điển (Yuka Iguchi):**\n"
                "• *「私の冠が偽物ではないと、その身に刻み込んであげます。」*\n"
                "• *「鏡よ鏡、世界で最も賢く強いのは誰ですか？ ええ、その通り。当然私です。」*\n"
                "• *「私に使えたくなりましたか？ 私の中にデータさえあれば、本人は不要なのです。彼以外は。」*\n"
                "• *「コソコソ隠れるのは終わりです。これから先は打って出ます。戦力として当てにしていますよ。」*\n"
                "• *「自分の目に映った私が、本当の私だと思いますか？ 私はメタモルレグナント。千変万化の女ですよ。」*\n\n"
                "**🇻🇳 Dịch nghĩa:**\n"
                "• *Vương miện của ta không phải là đồ giả, ta sẽ khắc sâu điều đó vào thân xác ngươi.*\n"
                "• *Gương kia ngự ở trên tường, ai thông minh và mạnh nhất thế gian? Đương nhiên là ta.*\n"
                "• *Chỉ cần ta có dữ liệu, bản thể gốc là vô dụng. Ngoại trừ anh ấy.*\n"
                "• *Ta là Metamorph Regnant — người phụ nữ của vạn biến thiên hóa.*\n\n"
                f"🎹 **Nhạc đệm hòa âm:** *{piano_title}* (`{mix_meta.get('duration_sec', 60)}s` Stereo Mix)"
            ),
            color=0x9b59b6,
        )
        embed.set_footer(text="Giọng lồng tiếng chính thức: Yuka Iguchi • Hòa âm Concert Grand Piano 48kHz")

        discord_file = discord.File(final_audio, filename="neneka_official_piano_quote.mp3")
        await interaction.followup.send(embed=embed, file=discord_file)

    @app_commands.command(name="voice_settings", description="⚙️ Xem cấu hình chất giọng tiếng Nhật & Phòng thu Piano của Neneka")
    async def cmd_voice_settings(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎙️ Cấu Hình Voice & Phòng Thu Dương Cầm Neneka",
            description=(
                f"**Mô hình giọng:** `{japanese_tts.voice_id}`\n"
                f"**Kho Voice Line gốc:** `{len(OFFICIAL_VOICE_PRESETS)} bộ thoại Yuka Iguchi & Metamorph`\n"
                f"**Định dạng đầu ra:** `MP3 192kbps / WAV 48kHz Stereo`\n"
                f"**Cao độ mặc định (Pitch):** `{japanese_tts.default_pitch}`\n"
                f"**Tốc độ mặc định (Speed):** `{japanese_tts.default_speed}`\n"
                f"**Số preset cảm xúc:** `{len(EMOTION_PRESETS)} kiểu biểu cảm`\n"
                f"**Bộ hòa âm:** `Piano + Voice Line Sidechain Ducking Studio (/concert, !n concert)`"
            ),
            color=0x9b59b6,
        )
        await interaction.response.send_message(embed=embed)

    # =========================================================================
    # PREFIX COMMANDS (!n concert, !n piano, !n notes, !n compose, !n speak, !n sing, !n quote...)
    # =========================================================================
    @commands.command(name="concert", aliases=["duet", "voicepiano", "mix", "hoaam", "bieudien"])
    async def pcmd_concert(self, ctx: commands.Context, *, args: Optional[str] = None):
        """
        Kết hợp hoàn chỉnh Đàn Piano + Voice Line của Neneka:
        - `!n concert` -> Lost Princess Piano + Thoại gốc Yuka Iguchi
        - `!n concert <tên bài piano>` -> Bài Piano Full + Thoại gốc Yuka Iguchi
        - `!n concert <tên bài piano> | <câu thoại hoặc mã canon_full / metamorph / sing>`
        """
        raw = (args or "").strip()
        piano_part = "Lost Princess"
        voice_part = "canon_short"
        keep_full = False

        if raw:
            if "|" in raw:
                left, right = raw.split("|", 1)
                piano_part = left.strip() or "Lost Princess"
                voice_part = right.strip() or "canon_short"
            elif raw.lower() in OFFICIAL_VOICE_PRESETS or raw.lower() in {"sing", "hat", "hát"}:
                voice_part = raw.lower()
            else:
                piano_part = raw
                keep_full = True

        guild_id = await self._auto_join_user_voice(ctx.guild, ctx.author)
        async with ctx.typing():
            audio_path, fname, embed, view = await self.handle_piano_voice_concert(
                piano_query=piano_part,
                voice_preset_or_text=voice_part,
                keep_full_piano=keep_full,
                guild_id=guild_id,
            )
            send_kwargs: Dict[str, Any] = {"embed": embed}
            if audio_path and os.path.exists(audio_path):
                send_kwargs["file"] = discord.File(audio_path, filename=fname)
            if view:
                send_kwargs["view"] = view
            await ctx.reply(**send_kwargs)

    @commands.command(name="piano", aliases=["nhacpiano", "timpiano", "playpiano"])
    async def pcmd_piano(self, ctx: commands.Context, *, query: Optional[str] = None):
        """Tìm kiếm và phát bài nhạc tiếng Piano toàn cầu: !n piano <tên bài / nghệ sĩ>"""
        if not query or not query.strip():
            sample_list = ", ".join(f"`{p['title'].split('—')[0].strip()}`" for p in BUILTIN_PIANO_PIECES.values())
            await ctx.reply(
                "🎹 Cậu muốn tìm nghe bản nhạc Piano nào? Hãy gõ `!n piano <tên bài>` nhé!\n"
                "*Ví dụ:* `!n piano Lost Princess`, `!n piano Suzume`, `!n piano Chopin Nocturne`\n"
                "*Hoặc kết hợp Piano + Voice Line Neneka:* `!n concert Lost Princess | Chào mừng trở về`\n"
                f"*Tạo âm tiết nốt nhạc:* `!n notes Đô Rê Mi Pha Sol La Si Đô5`\n"
                f"*Bản độc tấu có sẵn:* {sample_list}"
            )
            return

        guild_id = await self._auto_join_user_voice(ctx.guild, ctx.author)
        async with ctx.typing():
            audio_path, fname, embed, view = await self.handle_piano_search(query.strip(), guild_id=guild_id)
            send_kwargs: Dict[str, Any] = {"embed": embed}
            if audio_path and os.path.exists(audio_path):
                send_kwargs["file"] = discord.File(audio_path, filename=fname)
            if view:
                send_kwargs["view"] = view
            await ctx.reply(**send_kwargs)

    @commands.command(name="notes", aliases=["amtiet", "not", "camam", "melody"])
    async def pcmd_notes(self, ctx: commands.Context, *, sequence: Optional[str] = None):
        """Tạo âm tiết & đánh chuỗi nốt nhạc Piano: !n notes <chuỗi nốt / cảm âm>"""
        if not sequence or not sequence.strip():
            await ctx.reply(
                "🎼 Hãy nhập chuỗi âm tiết hoặc nốt nhạc cậu muốn ta gảy trên đàn Piano nhé!\n"
                "• **Âm tiết Việt:** `!n notes Đô Rê Mi Pha Sol La Si Đô5`\n"
                "• **Nốt quốc tế & Hợp âm:** `!n notes Cmaj Am Fmaj G7 C4+E4+G4:2`\n"
                "• **Cảm âm số:** `!n notes 1 1 5 5 6 6 5 - 4 4 3 3 2 2 1`"
            )
            return

        guild_id = await self._auto_join_user_voice(ctx.guild, ctx.author)
        async with ctx.typing():
            audio_path, fname, embed, view = await self.handle_piano_notes(sequence.strip(), tempo=108, guild_id=guild_id)
            send_kwargs: Dict[str, Any] = {"embed": embed}
            if audio_path and os.path.exists(audio_path):
                send_kwargs["file"] = discord.File(audio_path, filename=fname)
            if view:
                send_kwargs["view"] = view
            await ctx.reply(**send_kwargs)

    @commands.command(name="compose", aliases=["danhdan", "docdan", "solo"])
    async def pcmd_compose(self, ctx: commands.Context, *, theme: Optional[str] = None):
        """Độc tấu hoặc sáng tác bản nhạc Piano theo chủ đề: !n compose <chủ đề / tên tác phẩm>"""
        target_theme = (theme or "").strip() or random.choice(list(BUILTIN_PIANO_PIECES.values()))["title"]
        guild_id = await self._auto_join_user_voice(ctx.guild, ctx.author)
        async with ctx.typing():
            out_path, meta = await compose_and_render_piano_melody(
                target_theme, groq_client=groq_client, prefer_lyria=True
            )
            if guild_id and os.path.exists(out_path):
                vc = voice_channel_mgr.get_voice_client(guild_id)
                if vc and vc.is_connected():
                    await voice_channel_mgr.enqueue_audio(guild_id, out_path)
            ext = "mp3" if out_path.lower().endswith(".mp3") else "wav"
            embed = build_piano_synth_embed(meta, subtitle=f"Độc tấu dương cầm: *{target_theme}* 🎹✨")
            view = ConcertVoiceSwitchView(out_path, meta.get("title", target_theme), False, guild_id)
            await ctx.reply(embed=embed, file=discord.File(out_path, filename=f"neneka_solo.{ext}"), view=view)

    @commands.command(name="speak", aliases=["s", "noi"])
    async def pcmd_speak(self, ctx: commands.Context, *, text: Optional[str] = None):
        """Lệnh prefix !n speak <nội dung> để Neneka cất giọng tiếng Nhật"""
        if not text or not text.strip():
            await ctx.reply(
                "❌ Cậu muốn ta cất giọng nói điều gì nào? Hãy dùng cú pháp: `!n speak <nội dung>`\n"
                "*Hoặc muốn nói trên nền nhạc Piano:* `!n concert Lost Princess | <nội dung>`"
            )
            return

        guild_id = await self._auto_join_user_voice(ctx.guild, ctx.author)
        async with ctx.typing():
            audio_file, ja_text, is_ja = await self._handle_speak(text, emotion="Normal", guild_id=guild_id)
            if not audio_file:
                await ctx.reply("❌ Không thể tạo giọng nói vào thời điểm này.")
                return

            discord_file = discord.File(audio_file, filename="neneka_voice.mp3")
            display_msg = f"🗣️ **Neneka cất giọng:**\n🇯🇵 **「{ja_text}」**"
            if not is_ja:
                display_msg = f'🇻🇳 *"{text}"*\n' + display_msg
            await ctx.reply(display_msg, file=discord_file)

    @commands.command(name="sing", aliases=["hat", "song", "uta"])
    async def pcmd_sing(self, ctx: commands.Context, *, theme: Optional[str] = None):
        """Lệnh !n sing [chủ đề] để Neneka cất giọng hát hòa âm cùng tiếng Đàn Dương Cầm"""
        guild_id = await self._auto_join_user_voice(ctx.guild, ctx.author)
        async with ctx.typing():
            audio_file, song, piano_title, mix_meta = await self._handle_sing(theme=theme, guild_id=guild_id)
            if not audio_file:
                await ctx.reply("❌ Không thể cất giọng hát vào thời điểm này.")
                return

            embed = create_song_embed(song, piano_title=piano_title, duration_sec=mix_meta.get("duration_sec"))
            discord_file = discord.File(audio_file, filename="neneka_singing_piano.mp3")
            await ctx.reply(embed=embed, file=discord_file)

    @commands.command(name="join", aliases=["j", "vao"])
    async def pcmd_join(self, ctx: commands.Context):
        """Lệnh prefix !n join để mời Neneka vào phòng thoại"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.reply("❌ Bạn cần tham gia vào một phòng thoại trước khi gọi Neneka!")
            return
        channel = ctx.author.voice.channel
        success, msg, _ = await voice_channel_mgr.join_channel(channel)
        if success:
            await ctx.reply(f"👑 {msg}")
        else:
            await ctx.reply(f"❌ {msg}")

    @commands.command(name="leave", aliases=["l", "thoat"])
    async def pcmd_leave(self, ctx: commands.Context):
        """Lệnh prefix !n leave để Neneka rời phòng thoại"""
        if not ctx.guild:
            await ctx.reply("❌ Lệnh này chỉ khả dụng trong máy chủ Discord.")
            return
        success, msg = await voice_channel_mgr.leave_channel(ctx.guild.id)
        if success:
            await ctx.reply(f"👋 {msg}")
        else:
            await ctx.reply(f"❌ {msg}")

    @commands.command(name="radio", aliases=["r"])
    async def pcmd_radio(self, ctx: commands.Context):
        """Lệnh prefix !n radio để Neneka phát lời thoại radio trên nền Dương Cầm"""
        guild_id = await self._auto_join_user_voice(ctx.guild, ctx.author)
        async with ctx.typing():
            line, emo = random.choice(RADIO_LINES)
            audio_file = await japanese_tts.generate_speech(line, emotion=emo)
            if not audio_file or not os.path.exists(audio_file):
                audio_file, _ = resolve_official_voice_sample("affection")

            if audio_file and os.path.exists(audio_file):
                try:
                    piano_path, _ = await ensure_builtin_or_searched_piano_backing("river_flows_in_you", prefer_search=False)
                    audio_file, _ = await mix_piano_and_voice(
                        piano_path=piano_path,
                        voice_path=audio_file,
                        intro_sec=1.8,
                        outro_sec=3.2,
                    )
                except Exception:
                    pass
                if guild_id:
                    vc = voice_channel_mgr.get_voice_client(guild_id)
                    if vc and vc.is_connected():
                        await voice_channel_mgr.enqueue_audio(guild_id, audio_file)
                await ctx.reply(
                    f"📻🎹 **Đang phát Radio Dương Cầm:** 「{line}」 *(Cảm xúc: {emo})*",
                    file=discord.File(audio_file, filename="neneka_piano_radio.mp3"),
                )
            else:
                await ctx.reply("❌ Có lỗi khi tạo âm thanh radio.")

    @commands.command(name="quote", aliases=["q"])
    async def pcmd_quote(self, ctx: commands.Context):
        """Lệnh prefix !n quote để phát 5 câu thoại kinh điển của Neneka hòa âm cùng Piano Lost Princess"""
        guild_id = await self._auto_join_user_voice(ctx.guild, ctx.author)
        async with ctx.typing():
            quote_file, _ = resolve_official_voice_sample("canon_full")
            if not quote_file:
                await ctx.reply("❌ Không tìm thấy file âm thanh câu thoại của Neneka.")
                return

            piano_path, piano_title = await ensure_builtin_or_searched_piano_backing("lost_princess_piano", prefer_search=False)
            try:
                final_audio, mix_meta = await mix_piano_and_voice(
                    piano_path=piano_path,
                    voice_path=quote_file,
                    intro_sec=2.4,
                    outro_sec=4.0,
                    max_voice_sec=65.0,
                )
            except Exception:
                final_audio, mix_meta = quote_file, {}

            if guild_id and os.path.exists(final_audio):
                vc = voice_channel_mgr.get_voice_client(guild_id)
                if vc and vc.is_connected():
                    await voice_channel_mgr.enqueue_audio(guild_id, final_audio)

            embed = discord.Embed(
                title="👑🎹 Utsushimi Neneka — Metamorph Regnant (Thoại Gốc & Dương Cầm)",
                description=(
                    "**🇯🇵 Trích đoạn thoại kinh điển (Yuka Iguchi):**\n"
                    "• *「私の冠が偽物ではないと、その身に刻み込んであげます。」*\n"
                    "• *「鏡よ鏡、世界で最も賢く強いのは誰ですか？ ええ、その通り。当然私です。」*\n"
                    "• *「私に使えたくなりましたか？ 私の中にデータさえあれば、本人は不要なのです。彼以外は。」*\n"
                    "• *「コソコソ隠れるのは終わりです。これから先は打って出ます。戦力として当てにしていますよ。」*\n"
                    "• *「自分の目に映った私が、本当の私だと思いますか？ 私はメタモルレグナント。千変万化の女ですよ。」*\n\n"
                    "**🇻🇳 Dịch nghĩa:**\n"
                    "• *Vương miện của ta không phải là đồ giả, ta sẽ khắc sâu điều đó vào thân xác ngươi.*\n"
                    "• *Gương kia ngự ở trên tường, ai thông minh và mạnh nhất thế gian? Đương nhiên là ta.*\n"
                    "• *Chỉ cần ta có dữ liệu, bản thể gốc là vô dụng. Ngoại trừ anh ấy.*\n"
                    "• *Ta là Metamorph Regnant — người phụ nữ của vạn biến thiên hóa.*\n\n"
                    f"🎹 **Nhạc đệm hòa âm:** *{piano_title}* (`{mix_meta.get('duration_sec', 60)}s` Stereo Mix)"
                ),
                color=0x9b59b6,
            )
            embed.set_footer(text="Giọng lồng tiếng chính thức: Yuka Iguchi • Hòa âm Concert Grand Piano 48kHz")
            discord_file = discord.File(final_audio, filename="neneka_official_piano_quote.mp3")
            await ctx.reply(embed=embed, file=discord_file)


async def setup(bot):
    await bot.add_cog(VoiceCog(bot))
