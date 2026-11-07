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
    """Quản lý kết nối phòng thoại Discord và hệ thống Japanese TTS"""
    def __init__(self, bot):
        self.bot = bot

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

        # Dịch sang tiếng Nhật nếu nhập tiếng Việt
        is_ja = any(('\u3040' <= c <= '\u30ff') or ('\u4e00' <= c <= '\u9fff') for c in text)
        ja_text = text
        if not is_ja:
            prompt = (
                "Bạn là Neneka. Hãy dịch câu tiếng Việt sau sang tiếng Nhật anime tự nhiên: "
                f"\"{text}\". Chỉ trả về câu tiếng Nhật duy nhất (kanji/kana), không kèm giải thích."
            )
            try:
                res = await groq_client.chat_completion([{"role": "user", "content": prompt}], max_tokens=100)
                ja_text = res.strip().replace('"', '')
            except Exception:
                ja_text = "ふふっ、聞こえているわよ、坊や。"

        audio_file = await japanese_tts.generate_speech(ja_text, emotion=emotion)
        if not audio_file or not os.path.exists(audio_file):
            await interaction.followup.send("❌ Không thể tạo giọng nói vào thời điểm này.")
            return

        # Phát trên Voice Channel nếu bot đang trong phòng thoại
        if interaction.guild:
            vc = voice_channel_mgr.get_voice_client(interaction.guild.id)
            if vc and vc.is_connected():
                await voice_channel_mgr.enqueue_audio(interaction.guild.id, audio_file)

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

async def setup(bot):
    await bot.add_cog(VoiceCog(bot))

