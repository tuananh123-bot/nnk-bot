# src/cogs/voice.py
import asyncio
import os
import random
import re
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
from src.llm.groq_client import GroqClient
from src.personality.engine import PersonalityEngine

groq_client = GroqClient()

RADIO_LINES = [
    ("ふふっ、また私に会いに来てくれたのね、坊や。", "Affectionate"),
    ("この世界は計算と変貌で満ちているわ。あなたはどう思う？", "Curious"),
    ("あらあら…そんなに急いでどこへ行くのかしら。", "Normal"),
    ("私を観察しようだなんて、いい度胸ね。でも嫌いじゃないわ。", "Sarcastic"),
    ("無理は禁物よ。少し私のそばで休みましょう。", "Affectionate")
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

    embed.set_footer(text="Neneka Global Piano Search & Concert Hall")
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


class PianoTrackSelect(discord.ui.Select):
    """Menu thả xuống cho phép người dùng chọn phát bất kỳ bản Piano nào trong danh sách tìm được."""

    def __init__(self, tracks: List[Dict[str, Any]], query: str, guild_id: Optional[int]):
        self.tracks = tracks[:5]
        self.query = query
        self.guild_id = guild_id
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
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        idx = int(self.values[0])
        chosen = self.tracks[idx]
        audio_path = await download_piano_track_audio(chosen)
        if not audio_path or not os.path.exists(audio_path):
            # Nếu link phụ hết hạn, tự động dạo bản độc tấu Grand Piano 48kHz thay thế để luôn có âm thanh!
            audio_path, _ = await compose_and_render_piano_melody(
                chosen.get("title") or self.query, groq_client=groq_client
            )
            chosen["audio_ext"] = "mp3" if audio_path.lower().endswith(".mp3") else "wav"

        embed = build_piano_track_embed(chosen, self.tracks, self.query)

        if audio_path and os.path.exists(audio_path):
            if self.guild_id:
                vc = voice_channel_mgr.get_voice_client(self.guild_id)
                if vc and vc.is_connected():
                    await voice_channel_mgr.enqueue_audio(self.guild_id, audio_path)
            ext = chosen.get("audio_ext", "mp3")
            d_file = discord.File(audio_path, filename=f"neneka_piano_{idx + 1}.{ext}")
            await interaction.followup.send(embed=embed, file=d_file)
        else:
            await interaction.followup.send(embed=embed)


class PianoTrackSelectView(discord.ui.View):
    def __init__(self, tracks: List[Dict[str, Any]], query: str, guild_id: Optional[int]):
        super().__init__(timeout=180)
        if len(tracks) > 1:
            self.add_item(PianoTrackSelect(tracks, query, guild_id))


class VoiceCog(commands.Cog):
    """Quản lý kết nối phòng thoại Discord, Japanese TTS và Hệ thống Âm nhạc Đại Dương Cầm (Piano Synth & Global Search)"""
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

    async def _handle_speak(self, text: str, emotion: str = "Normal", guild_id: Optional[int] = None):
        """Hàm dùng chung xử lý dịch câu thoại, sinh âm thanh Fish Audio và đẩy vào Voice Channel"""
        clean_text = text.strip()
        is_ja = any(('\u3040' <= c <= '\u30ff') or ('\u4e00' <= c <= '\u9fff') for c in clean_text)
        ja_text = clean_text
        if not is_ja:
            prompt = (
                "Bạn là Neneka. Hãy dịch câu tiếng Việt sau sang tiếng Nhật anime tự nhiên: "
                f"\"{clean_text}\". Chỉ trả về câu tiếng Nhật duy nhất (kanji/kana), không kèm giải thích."
            )
            try:
                res = await groq_client.chat_completion([{"role": "user", "content": prompt}], max_tokens=100)
                ja_text = res.strip().replace('"', '')
            except Exception:
                ja_text = "ふふっ、聞こえているわよ、坊や。"

        audio_file = await japanese_tts.generate_speech(ja_text, emotion=emotion)
        if not audio_file or not os.path.exists(audio_file):
            return None, ja_text, is_ja

        if guild_id:
            vc = voice_channel_mgr.get_voice_client(guild_id)
            if vc and vc.is_connected():
                await voice_channel_mgr.enqueue_audio(guild_id, audio_file)

        return audio_file, ja_text, is_ja

    async def _handle_sing(
        self,
        theme: Optional[str] = None,
        guild_id: Optional[int] = None
    ) -> Tuple[Optional[str], Dict[str, str]]:
        """Xử lý chọn/sáng tác bài hát theo phong cách Nhật Bản và tạo file âm thanh Fish Audio"""
        song = await get_song_by_theme_or_random(theme)
        lyrics = song["japanese_lyrics"]
        emotion = song.get("emotion", "Affectionate")

        audio_file = await japanese_tts.generate_speech(lyrics, emotion=emotion)

        if guild_id and audio_file and os.path.exists(audio_file):
            vc = voice_channel_mgr.get_voice_client(guild_id)
            if vc and vc.is_connected():
                await voice_channel_mgr.enqueue_audio(guild_id, audio_file)

        return audio_file, song

    async def handle_piano_notes(
        self,
        sequence_or_theme: str,
        tempo: int = 108,
        guild_id: Optional[int] = None,
    ) -> Tuple[str, str, discord.Embed, Optional[discord.ui.View]]:
        """
        Tạo âm tiết / đánh chuỗi nốt nhạc Piano (hoặc tự động chuyển sang tìm bài nhạc Piano đầy đủ nếu người dùng nhập tên bài hát / tên game!):
        - Nếu là chuỗi nốt/âm tiết thật sự (Đô Rê Mi, Đô-Rê-Mi, C4 E4 G4, 1 2 3 5 6, Cmaj Am): tổng hợp 48kHz Stereo WAV.
        - Nếu người dùng chỉ gõ đúng 1 nốt đơn lẻ (ví dụ 'Đô' hoặc 'C4'): tự động ngân hợp âm rải nhẹ trên nốt đó để tiếng đàn dày, rõ và vang đẹp thay vì kêu cụt 0.3s!
        - Nếu người dùng gõ TÊN BÀI HÁT hoặc TÊN GAME (ví dụ 'Lost Princess', 'Re Zero', 'Blue Archive'): tự động tìm đúng bản nhạc Piano Full-Length!
        """
        clean_input = sequence_or_theme.strip()
        if is_genuine_note_sequence(clean_input):
            events = parse_note_sequence(clean_input)
            valid_notes = [e for e in events if e[0]]
            # Nếu người dùng chỉ thử gõ 1 âm tiết duy nhất (VD: "Đô"), ngân dài 2.5 phách rõ ràng
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
            return wav_path, "neneka_piano_notes.wav", embed, None

        # Nếu đầu vào là tên bài hát / tên game -> Tìm đúng bản nhạc Piano đầy đủ!
        audio_path, fname, embed, view = await self.handle_piano_search(clean_input, guild_id=guild_id)
        return audio_path or "", fname, embed, view

    async def handle_piano_search(
        self,
        query: str,
        guild_id: Optional[int] = None,
    ) -> Tuple[Optional[str], str, discord.Embed, Optional[discord.ui.View]]:
        """
        Tìm kiếm toàn bộ bài nhạc tiếng Piano trên thế giới (Deezer + Apple Music/iTunes + Internet Archive).
        Nếu offline hoặc bài quá hiếm không có bản thu sẵn, tự động chuyển sang độc tấu bằng bộ Grand Piano Synth!
        Trả về: (audio_path, filename, embed, view)
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
                view = PianoTrackSelectView(tracks, query, guild_id) if len(tracks) > 1 else None
                return audio_path, f"neneka_piano.{ext}", embed, view

        # Fallback: Tự độc tấu bản nhạc đó trên đàn Grand Piano 48kHz của Neneka!
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
        return wav_path, f"neneka_piano_solo.{ext}", embed, None

    # =========================================================================
    # SLASH COMMANDS
    # =========================================================================
    @app_commands.command(name="piano", description="🎹 Tìm kiếm và phát bất kỳ bài nhạc tiếng Piano nào (Anime, Cổ điển, V-Pop, J-Pop...)")
    @app_commands.describe(query="Tên bài hát, bản nhạc hoặc nghệ sĩ Piano cần tìm (ví dụ: River Flows in You, Unravel, Suzume, Chopin...)")
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
        tempo="Nhịp độ BPM (từ 40 đến 240, mặc định 108)"
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
        ai_studio="Thử dùng Google Lyria 3 Studio AI nếu khả dụng (mặc định: Tự động)"
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
        await interaction.followup.send(embed=embed, file=discord.File(out_path, filename=f"neneka_solo.{ext}"))

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

    @app_commands.command(name="speak", description="🎙️ Yêu cầu Neneka cất giọng tiếng Nhật (kèm file audio)")
    @app_commands.describe(
        text="Văn bản tiếng Nhật hoặc tiếng Việt cần phát âm",
        emotion="Cảm xúc biểu đạt của giọng nói"
    )
    @app_commands.choices(emotion=[
        app_commands.Choice(name=f"✨ {k}", value=k) for k in EMOTION_PRESETS.keys()
    ])
    async def cmd_speak(self, interaction: discord.Interaction, text: str, emotion: Optional[str] = "Normal"):
        await interaction.response.defer()

        guild_id = interaction.guild.id if interaction.guild else None
        audio_file, ja_text, is_ja = await self._handle_speak(text, emotion=emotion, guild_id=guild_id)
        if not audio_file:
            await interaction.followup.send("❌ Không thể tạo giọng nói vào thời điểm này.")
            return

        discord_file = discord.File(audio_file, filename="neneka_voice.mp3")
        display_msg = f"🗣️ **Neneka cất giọng:**\n🇯🇵 **「{ja_text}」**"
        if not is_ja:
            display_msg = f"🇻🇳 *\"{text}\"*\n" + display_msg
        await interaction.followup.send(display_msg, file=discord_file)

    @app_commands.command(name="sing", description="🎵 Yêu cầu Neneka cất giọng hát một bài ngẫu nhiên theo phong cách Nhật Bản")
    @app_commands.describe(theme="Chủ đề hoặc phong cách bài hát (ví dụ: ru ngủ, tình yêu, hoa anh đào, landosol, vui tươi...)")
    async def cmd_sing(self, interaction: discord.Interaction, theme: Optional[str] = None):
        await interaction.response.defer()
        guild_id = await self._auto_join_user_voice(interaction.guild, interaction.user)

        audio_file, song = await self._handle_sing(theme=theme, guild_id=guild_id)
        if not audio_file:
            await interaction.followup.send("❌ Không thể cất giọng hát vào thời điểm này.")
            return

        embed = create_song_embed(song)
        discord_file = discord.File(audio_file, filename="neneka_singing.mp3")
        await interaction.followup.send(embed=embed, file=discord_file)

    @app_commands.command(name="radio", description="📻 Phát một câu thoại ngẫu nhiên của Neneka trong Voice Channel")
    async def cmd_radio(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ Lệnh này chỉ dùng trong server.", ephemeral=True)
            return

        vc = voice_channel_mgr.get_voice_client(interaction.guild.id)
        if not vc or not vc.is_connected():
            if interaction.user.voice and interaction.user.voice.channel:
                await voice_channel_mgr.join_channel(interaction.user.voice.channel)
                vc = voice_channel_mgr.get_voice_client(interaction.guild.id)
            else:
                await interaction.response.send_message("❌ Hãy mời Neneka vào Voice Channel bằng lệnh `/join` trước!", ephemeral=True)
                return

        line, emo = random.choice(RADIO_LINES)
        audio_file = await japanese_tts.generate_speech(line, emotion=emo)
        if audio_file:
            await voice_channel_mgr.enqueue_audio(interaction.guild.id, audio_file)
            await interaction.response.send_message(f"📻 **Đang phát radio:** 「{line}」 *(Cảm xúc: {emo})*")
        else:
            await interaction.response.send_message("❌ Có lỗi khi tạo âm thanh radio.", ephemeral=True)

    @app_commands.command(name="quote", description="👑 Phát câu thoại kinh điển chính thức của Neneka (giọng lồng tiếng gốc)")
    async def cmd_quote(self, interaction: discord.Interaction):
        await interaction.response.defer()
        quote_file = os.path.abspath(os.path.join("assets", "voice_samples", "neneka_sample_clean_1min.mp3"))
        if not os.path.exists(quote_file):
            quote_file = os.path.abspath(os.path.join("assets", "voice_samples", "neneka_sample_short.mp3"))

        if not os.path.exists(quote_file):
            await interaction.followup.send("❌ Không tìm thấy file âm thanh câu thoại của Neneka.")
            return

        if interaction.guild:
            vc = voice_channel_mgr.get_voice_client(interaction.guild.id)
            if vc and vc.is_connected():
                await voice_channel_mgr.enqueue_audio(interaction.guild.id, quote_file)

        embed = discord.Embed(
            title="👑 Utsushimi Neneka — Metamorph Regnant (七冠 / 変貌大妃)",
            description=(
                "**🇯🇵 Trích đoạn thoại kinh điển:**\n"
                "• *「私の冠が偽物ではないと、その身に刻み込んであげます。」*\n"
                "• *「鏡よ鏡、世界で最も賢く強いのは誰ですか？ ええ、その通り。当然私です。」*\n"
                "• *「私に使えたくなりましたか？ 私の中にデータさえあれば、本人は不要なのです。彼以外は。」*\n"
                "• *「コソコソ隠れるのは終わりです。これから先は打って出ます。戦力として当てにしていますよ。」*\n"
                "• *「自分の目に映った私が、本当の私だと思いますか？ 私はメタモルレグナント。千変万化の女ですよ。」*\n\n"
                "**🇻🇳 Dịch nghĩa:**\n"
                "• *Vương miện của ta không phải là đồ giả, ta sẽ khắc sâu điều đó vào thân xác ngươi.*\n"
                "• *Gương kia ngự ở trên tường, ai thông minh và mạnh nhất thế gian? Đương nhiên là ta.*\n"
                "• *Chỉ cần ta có dữ liệu, bản thể gốc là vô dụng. Ngoại trừ anh ấy.*\n"
                "• *Ta là Metamorph Regnant — người phụ nữ của vạn biến thiên hóa.*"
            ),
            color=0x9b59b6
        )
        embed.set_footer(text="Giọng lồng tiếng chính thức: Yuka Iguchi (Princess Connect! Re:Dive)")

        discord_file = discord.File(quote_file, filename="neneka_official_voice.mp3")
        await interaction.followup.send(embed=embed, file=discord_file)

    @app_commands.command(name="voice_settings", description="⚙️ Xem cấu hình chất giọng tiếng Nhật hiện tại của Neneka")
    async def cmd_voice_settings(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎙️ Cấu Hình Voice & Âm Nhạc Neneka",
            description=(
                f"**Mô hình giọng:** `{japanese_tts.voice_id}`\n"
                f"**Định dạng đầu ra:** `{japanese_tts.get_audio_format().upper()}`\n"
                f"**Cao độ mặc định (Pitch):** `{japanese_tts.default_pitch}`\n"
                f"**Tốc độ mặc định (Speed):** `{japanese_tts.default_speed}`\n"
                f"**Số preset cảm xúc:** {len(EMOTION_PRESETS)} kiểu biểu cảm\n"
                f"**Bộ đàn Piano:** `Concert Grand Piano 48kHz Stereo Synth + Global Piano Search`"
            ),
            color=0x9b59b6
        )
        await interaction.response.send_message(embed=embed)

    # =========================================================================
    # PREFIX COMMANDS (!n piano, !n notes, !n compose, !n speak, !n sing, !n join, !n leave...)
    # =========================================================================
    @commands.command(name="piano", aliases=["nhacpiano", "timpiano", "playpiano"])
    async def pcmd_piano(self, ctx: commands.Context, *, query: Optional[str] = None):
        """Tìm kiếm và phát bài nhạc tiếng Piano toàn cầu: !n piano <tên bài / nghệ sĩ>"""
        if not query or not query.strip():
            sample_list = ", ".join(f"`{p['title'].split('—')[0].strip()}`" for p in BUILTIN_PIANO_PIECES.values())
            await ctx.reply(
                "🎹 Cậu muốn tìm nghe bản nhạc Piano nào? Hãy gõ `!n piano <tên bài>` nhé!\n"
                "*Ví dụ:* `!n piano River Flows in You`, `!n piano Suzume`, `!n piano Chopin Nocturne`\n"
                f"*Hoặc tạo âm tiết nốt nhạc:* `!n notes Đô Rê Mi Pha Sol La Si Đô5`\n"
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
            await ctx.reply(embed=embed, file=discord.File(out_path, filename=f"neneka_solo.{ext}"))

    @commands.command(name="speak", aliases=["s", "noi"])
    async def pcmd_speak(self, ctx: commands.Context, *, text: Optional[str] = None):
        """Lệnh prefix !n speak <nội dung> để Neneka cất giọng tiếng Nhật"""
        if not text or not text.strip():
            await ctx.reply("❌ Cậu muốn ta cất giọng nói điều gì nào? Hãy dùng cú pháp: `!n speak <nội dung>`\n*Ví dụ:* `!n speak chào buổi sáng kishi-kun` hoặc `!n speak こんにちは`")
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
                display_msg = f"🇻🇳 *\"{text}\"*\n" + display_msg
            await ctx.reply(display_msg, file=discord_file)

    @commands.command(name="sing", aliases=["hat", "song", "uta"])
    async def pcmd_sing(self, ctx: commands.Context, *, theme: Optional[str] = None):
        """Lệnh !n sing [chủ đề] để Neneka hát một bài ngẫu nhiên theo phong cách Nhật Bản"""
        guild_id = await self._auto_join_user_voice(ctx.guild, ctx.author)
        async with ctx.typing():
            audio_file, song = await self._handle_sing(theme=theme, guild_id=guild_id)
            if not audio_file:
                await ctx.reply("❌ Không thể cất giọng hát vào thời điểm này.")
                return

            embed = create_song_embed(song)
            discord_file = discord.File(audio_file, filename="neneka_singing.mp3")
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
        """Lệnh prefix !n radio để Neneka phát ngẫu nhiên lời thoại trong phòng thoại"""
        if not ctx.guild:
            await ctx.reply("❌ Lệnh này chỉ dùng trong server.")
            return

        vc = voice_channel_mgr.get_voice_client(ctx.guild.id)
        if not vc or not vc.is_connected():
            if ctx.author.voice and ctx.author.voice.channel:
                await voice_channel_mgr.join_channel(ctx.author.voice.channel)
                vc = voice_channel_mgr.get_voice_client(ctx.guild.id)
            else:
                await ctx.reply("❌ Hãy mời Neneka vào Voice Channel bằng lệnh `!n join` trước!")
                return

        line, emo = random.choice(RADIO_LINES)
        audio_file = await japanese_tts.generate_speech(line, emotion=emo)
        if audio_file:
            await voice_channel_mgr.enqueue_audio(ctx.guild.id, audio_file)
            await ctx.reply(f"📻 **Đang phát radio:** 「{line}」 *(Cảm xúc: {emo})*")
        else:
            await ctx.reply("❌ Có lỗi khi tạo âm thanh radio.")

    @commands.command(name="quote", aliases=["q"])
    async def pcmd_quote(self, ctx: commands.Context):
        """Lệnh prefix !n quote để phát 5 câu thoại kinh điển chính thức của Neneka"""
        quote_file = os.path.abspath(os.path.join("assets", "voice_samples", "neneka_sample_clean_1min.mp3"))
        if not os.path.exists(quote_file):
            quote_file = os.path.abspath(os.path.join("assets", "voice_samples", "neneka_sample_short.mp3"))

        if not os.path.exists(quote_file):
            await ctx.reply("❌ Không tìm thấy file âm thanh câu thoại của Neneka.")
            return

        if ctx.guild:
            vc = voice_channel_mgr.get_voice_client(ctx.guild.id)
            if vc and vc.is_connected():
                await voice_channel_mgr.enqueue_audio(ctx.guild.id, quote_file)

        embed = discord.Embed(
            title="👑 Utsushimi Neneka — Metamorph Regnant (七冠 / 変貌大妃)",
            description=(
                "**🇯🇵 Trích đoạn thoại kinh điển:**\n"
                "• *「私の冠が偽物ではないと、その身に刻み込んであげます。」*\n"
                "• *「鏡よ鏡、世界で最も賢く強いのは誰ですか？ ええ、その通り。当然私です。」*\n"
                "• *「私に使えたくなりましたか？ 私の中にデータさえあれば、本人は不要なのです。彼以外は。」*\n"
                "• *「コソコソ隠れるのは終わりです。これから先は打って出ます。戦力として当てにしていますよ。」*\n"
                "• *「自分の目に映った私が、本当の私だと思いますか？ 私はメタモルレグナント。千変万化の女ですよ。」*\n\n"
                "**🇻🇳 Dịch nghĩa:**\n"
                "• *Vương miện của ta không phải là đồ giả, ta sẽ khắc sâu điều đó vào thân xác ngươi.*\n"
                "• *Gương kia ngự ở trên tường, ai thông minh và mạnh nhất thế gian? Đương nhiên là ta.*\n"
                "• *Chỉ cần ta có dữ liệu, bản thể gốc là vô dụng. Ngoại trừ anh ấy.*\n"
                "• *Ta là Metamorph Regnant — người phụ nữ của vạn biến thiên hóa.*"
            ),
            color=0x9b59b6
        )
        embed.set_footer(text="Giọng lồng tiếng chính thức: Yuka Iguchi (Princess Connect! Re:Dive)")
        discord_file = discord.File(quote_file, filename="neneka_official_voice.mp3")
        await ctx.reply(embed=embed, file=discord_file)

async def setup(bot):
    await bot.add_cog(VoiceCog(bot))
