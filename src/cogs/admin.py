# src/cogs/admin.py
import discord
from discord import app_commands
from discord.ext import commands

from src.config import settings
from src.autonomous.proactive_engine import proactive_engine
from src.database.connection import db_manager
from src.cache.redis_client import cache

class AdminCog(commands.Cog):
    """Lệnh quản trị, cấu hình và giám sát trạng thái bot"""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="autochat", description="⚙️ Bật hoặc tắt tự động trò chuyện trong kênh này (Yêu cầu quyền Manage Channels)")
    @app_commands.describe(status="Trạng thái: on (bật), off (tắt)")
    @app_commands.choices(status=[
        app_commands.Choice(name="✅ Bật tự động trả lời trong kênh", value="on"),
        app_commands.Choice(name="❎ Tắt tự động trả lời trong kênh", value="off")
    ])
    @commands.has_permissions(manage_channels=True)
    async def cmd_autochat(self, interaction: discord.Interaction, status: str):
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ Bạn cần quyền `Manage Channels` để thực hiện thao tác này.", ephemeral=True)
            return

        cid = interaction.channel_id
        if status == "on":
            proactive_engine.add_allowed_channel(cid)
            await interaction.response.send_message(f"✅ Đã **BẬT** chế độ tự động trò chuyện trong {interaction.channel.mention}!\nNeneka sẽ tham gia hội thoại mà không cần tag.")
        else:
            proactive_engine.remove_allowed_channel(cid)
            await interaction.response.send_message(f"❎ Đã **TẮT** chế độ tự động trò chuyện trong {interaction.channel.mention}.\nNeneka sẽ chỉ phản hồi khi được @mention.")

    @app_commands.command(name="autonomous", description="⚙️ Cấu hình chế độ chủ động tương tác của Neneka")
    @app_commands.describe(mode="Chọn chế độ hoạt động")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Mode A: Mention Only (Chỉ trả lời khi được gọi)", value="MENTION"),
        app_commands.Choice(name="Mode B: Auto Chat (Tự động trò chuyện trong kênh cấp phép)", value="AUTO_CHAT"),
        app_commands.Choice(name="Mode C: Autonomous Character (Chủ động mở lời & chào đón)", value="AUTONOMOUS")
    ])
    @commands.has_permissions(administrator=True)
    async def cmd_autonomous(self, interaction: discord.Interaction, mode: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Bạn cần quyền `Administrator` để đổi chế độ của bot.", ephemeral=True)
            return

        success = proactive_engine.set_mode(mode)
        if success:
            await interaction.response.send_message(f"👑 Đã chuyển đổi chế độ hoạt động sang: **{mode}**.")
        else:
            await interaction.response.send_message("❌ Chế độ không hợp lệ.", ephemeral=True)

    @app_commands.command(name="admin", description="🛠️ Bảng điều khiển quản trị và trạng thái hệ thống")
    @commands.has_permissions(administrator=True)
    async def cmd_admin(self, interaction: discord.Interaction):
        db_type = "Async SQLite (Local Fallback)" if db_manager.is_sqlite_fallback else "PostgreSQL (Production)"
        cache_type = "In-Memory RAM" if cache._use_fallback else "Redis (Live)"

        embed = discord.Embed(
            title="🛠️ Bảng Quản Trị Hệ Thống - Neneka Autonomous AI",
            color=0x2ecc71
        )
        embed.add_field(name="🤖 Chế Độ Hoạt Động", value=f"`{proactive_engine.mode}`", inline=True)
        embed.add_field(name="🧠 Mô Hình Groq", value=f"`{settings.GROQ_MODEL}`", inline=True)
        embed.add_field(name="🗄️ Database", value=f"`{db_type}`", inline=False)
        embed.add_field(name="⚡ Bộ Nhớ Cache", value=f"`{cache_type}`", inline=True)
        embed.add_field(name="📋 Số Kênh Auto-chat", value=f"`{len(proactive_engine.allowed_channels)}` kênh", inline=True)
        embed.set_footer(text=f"Antigravity Neneka Engine • Ping: {round(self.bot.latency * 1000)}ms")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))

