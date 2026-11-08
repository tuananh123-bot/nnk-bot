# src/cogs/voice.py
import os
import random
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.voice.japanese_tts import japanese_tts, EMOTION_PRESETS
from src.voice.voice_channel import voice_channel_mgr
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

class VoiceCog(commands.Cog):
    """Quản lý kết nối phòng thoại Discord và hệ thống Japanese TTS (hỗ trợ cả Slash Commands và Prefix Commands !n)"""
    def __init__(self, bot):
        self.bot = bot

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

        # Phát trên Voice Channel nếu bot đang trong phòng thoại của guild
        if guild_id:
            vc = voice_channel_mgr.get_voice_client(guild_id)
            if vc and vc.is_connected():
                await voice_channel_mgr.enqueue_audio(guild_id, audio_file)

        return audio_file, ja_text, is_ja

    # =========================================================================
    # SLASH COMMANDS
    # =========================================================================
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

        # Phát vào Voice Channel nếu đang kết nối
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
            title="🎙️ Cấu Hình Voice Japanese Neneka",
            description=(
                f"**Mô hình giọng:** `{japanese_tts.voice_id}`\n"
                f"**Định dạng đầu ra:** `{japanese_tts.get_audio_format().upper()}`\n"
                f"**Cao độ mặc định (Pitch):** `{japanese_tts.default_pitch}`\n"
                f"**Tốc độ mặc định (Speed):** `{japanese_tts.default_speed}`\n"
                f"**Số preset cảm xúc:** {len(EMOTION_PRESETS)} kiểu biểu cảm"
            ),
            color=0x9b59b6
        )
        await interaction.response.send_message(embed=embed)

    # =========================================================================
    # PREFIX COMMANDS (!n speak, n!speak, !n join, !n leave, !n radio, !n quote)
    # =========================================================================
    @commands.command(name="speak", aliases=["s", "noi"])
    async def pcmd_speak(self, ctx: commands.Context, *, text: Optional[str] = None):
        """Lệnh prefix !n speak <nội dung> để Neneka cất giọng tiếng Nhật"""
        if not text or not text.strip():
            await ctx.reply("❌ Cậu muốn ta cất giọng nói điều gì nào? Hãy dùng cú pháp: `!n speak <nội dung>`\n*Ví dụ:* `!n speak chào buổi sáng kishi-kun` hoặc `!n speak こんにちは`")
            return

        # Tự động tham gia phòng thoại nếu người dùng đang trong phòng mà bot chưa vào
        if ctx.guild and ctx.author.voice and ctx.author.voice.channel:
            vc = voice_channel_mgr.get_voice_client(ctx.guild.id)
            if not vc or not vc.is_connected():
                await voice_channel_mgr.join_channel(ctx.author.voice.channel)

        async with ctx.typing():
            guild_id = ctx.guild.id if ctx.guild else None
            audio_file, ja_text, is_ja = await self._handle_speak(text, emotion="Normal", guild_id=guild_id)
            if not audio_file:
                await ctx.reply("❌ Không thể tạo giọng nói vào thời điểm này.")
                return

            discord_file = discord.File(audio_file, filename="neneka_voice.mp3")
            display_msg = f"🗣️ **Neneka cất giọng:**\n🇯🇵 **「{ja_text}」**"
            if not is_ja:
                display_msg = f"🇻🇳 *\"{text}\"*\n" + display_msg
            await ctx.reply(display_msg, file=discord_file)

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

    async def cmd_voice_settings(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎙️ Cấu Hình Voice Japanese Neneka",
            description=(
                f"**Mô hình giọng:** `{japanese_tts.voice_id}`\n"
                f"**Định dạng đầu ra:** `{japanese_tts.get_audio_format().upper()}`\n"
                f"**Cao độ mặc định (Pitch):** `{japanese_tts.default_pitch}`\n"
                f"**Tốc độ mặc định (Speed):** `{japanese_tts.default_speed}`\n"
                f"**Số preset cảm xúc:** {len(EMOTION_PRESETS)} kiểu biểu cảm"
            ),
            color=0x9b59b6
        )
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(VoiceCog(bot))

