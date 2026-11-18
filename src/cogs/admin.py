# src/cogs/admin.py
import discord
from discord import app_commands
from discord.ext import commands

from src.config import settings
from src.autonomous.proactive_engine import proactive_engine
from src.database.connection import db_manager
from src.cache.redis_client import cache
from src.cogs.chat import _nsfw_runtime_channels
from src.llm.model_status import build_model_status_embed, get_active_models_info

class AdminCog(commands.Cog):
    """Lệnh quản trị, cấu hình và giám sát trạng thái bot"""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="autochat", description="⚙️ Bật hoặc tắt tự động trò chuyện trong kênh này (Yêu cầu quyền Manage Channels hoặc Creator)")
    @app_commands.describe(status="Trạng thái: on (bật), off (tắt)")
    @app_commands.choices(status=[
        app_commands.Choice(name="✅ Bật tự động trả lời trong kênh", value="on"),
        app_commands.Choice(name="❎ Tắt tự động trả lời trong kênh", value="off")
    ])
    async def cmd_autochat(self, interaction: discord.Interaction, status: str):
        is_creator = (str(interaction.user.id) == str(settings.CREATOR_USER_ID))
        if not is_creator and not (interaction.user.guild_permissions and interaction.user.guild_permissions.manage_channels):
            await interaction.response.send_message("❌ Bạn cần quyền `Manage Channels` để thực hiện thao tác này.", ephemeral=True)
            return

        cid = interaction.channel_id
        if status == "on":
            proactive_engine.add_allowed_channel(cid)
            await interaction.response.send_message(f"✅ Đã **BẬT** chế độ tự động trò chuyện trong {interaction.channel.mention}!\nNeneka sẽ tham gia hội thoại mà không cần tag.")
        else:
            proactive_engine.remove_allowed_channel(cid)
            await interaction.response.send_message(f"❎ Đã **TẮT** chế độ tự động trò chuyện trong {interaction.channel.mention}.\nNeneka sẽ chỉ phản hồi khi được @mention.")

    @app_commands.command(name="autonomous", description="⚙️ Cấu hình chế độ chủ động tương tác của Neneka (Admin hoặc Creator)")
    @app_commands.describe(mode="Chọn chế độ hoạt động")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Mode A: Mention Only (Chỉ trả lời khi được gọi)", value="MENTION"),
        app_commands.Choice(name="Mode B: Auto Chat (Tự động trò chuyện trong kênh cấp phép)", value="AUTO_CHAT"),
        app_commands.Choice(name="Mode C: Autonomous Character (Chủ động mở lời & chào đón)", value="AUTONOMOUS")
    ])
    async def cmd_autonomous(self, interaction: discord.Interaction, mode: str):
        is_creator = (str(interaction.user.id) == str(settings.CREATOR_USER_ID))
        if not is_creator and not (interaction.user.guild_permissions and interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("❌ Bạn cần quyền `Administrator` để đổi chế độ của bot.", ephemeral=True)
            return

        success = proactive_engine.set_mode(mode)
        if success:
            await interaction.response.send_message(f"👑 Đã chuyển đổi chế độ hoạt động sang: **{mode}**.")
        else:
            await interaction.response.send_message("❌ Chế độ không hợp lệ.", ephemeral=True)

    @app_commands.command(name="nsfw", description="🔞 Bật/Tắt chế độ nội dung 18+ cho kênh này (Admin hoặc Creator)")
    @app_commands.describe(action="Chọn hành động: enable (bật) hoặc disable (tắt)")
    @app_commands.choices(action=[
        app_commands.Choice(name="🔓 Bật NSFW cho kênh này", value="enable"),
        app_commands.Choice(name="🔒 Tắt NSFW cho kênh này", value="disable"),
        app_commands.Choice(name="📋 Xem trạng thái NSFW", value="status"),
    ])
    async def cmd_nsfw(self, interaction: discord.Interaction, action: str = "status"):
        is_creator = (str(interaction.user.id) == str(settings.CREATOR_USER_ID))
        has_perm = (
            is_creator or
            (interaction.user.guild_permissions and interaction.user.guild_permissions.manage_channels)
        )
        if not has_perm:
            await interaction.response.send_message(
                "❌ Bạn cần quyền `Manage Channels` hoặc là Người Sáng Tạo để quản lý NSFW.",
                ephemeral=True
            )
            return

        if not settings.NSFW_ENABLED:
            await interaction.response.send_message(
                "⚠️ Tính năng NSFW chưa được kích hoạt trong cấu hình bot (`NSFW_ENABLED=false`).\n"
                "Liên hệ Người Sáng Tạo để bật tính năng này.",
                ephemeral=True
            )
            return

        cid = interaction.channel_id
        if action == "enable":
            _nsfw_runtime_channels.add(cid)
            await interaction.response.send_message(
                f"🔓 Đã **BẬT** chế độ nội dung 18+ trong {interaction.channel.mention}.\n"
                "Neneka sẽ phản hồi các chủ đề nhạy cảm/người lớn tại kênh này.\n"
                "⚠️ *Đảm bảo kênh đã được đánh dấu NSFW trong cài đặt Discord.*",
                ephemeral=False
            )
        elif action == "disable":
            _nsfw_runtime_channels.discard(cid)
            await interaction.response.send_message(
                f"🔒 Đã **TẮT** chế độ nội dung 18+ trong {interaction.channel.mention}.\n"
                "Neneka sẽ trở về chế độ nội dung thông thường.",
                ephemeral=False
            )
        else:
            is_active = cid in _nsfw_runtime_channels or cid in settings.nsfw_channel_id_list
            status_str = "🔓 **ĐANG BẬT**" if is_active else "🔒 **ĐANG TẮT**"
            status_embed = build_model_status_embed(is_channel_nsfw=is_active)
            await interaction.response.send_message(
                f"📋 Trạng thái NSFW tại {interaction.channel.mention}: {status_str}\n"
                f"Tổng kênh NSFW (runtime): `{len(_nsfw_runtime_channels)}` kênh",
                embed=status_embed,
                ephemeral=True
            )

    @app_commands.command(name="admin", description="🛠️ Bảng điều khiển quản trị và trạng thái hệ thống")
    async def cmd_admin(self, interaction: discord.Interaction):
        is_creator = (str(interaction.user.id) == str(settings.CREATOR_USER_ID))
        if not is_creator and not (interaction.user.guild_permissions and interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("❌ Bạn cần quyền `Administrator` để xem bảng quản trị.", ephemeral=True)
            return
        db_type = "Async SQLite (Local Fallback)" if db_manager.is_sqlite_fallback else "PostgreSQL (Production)"
        cache_type = "In-Memory RAM" if cache._use_fallback else "Redis (Live)"
        models_info = get_active_models_info()

        embed = discord.Embed(
            title="🛠️ Bảng Quản Trị Hệ Thống - Neneka Autonomous AI",
            color=0x2ecc71
        )
        embed.add_field(name="🤖 Chế Độ Hoạt Động", value=f"`{proactive_engine.mode}`", inline=True)
        embed.add_field(
            name="🧠 Bot Thường (Groq)",
            value=f"`{models_info['normal_bot']['active_model']}` ({models_info['normal_bot']['status']})",
            inline=True
        )
        embed.add_field(
            name="🔞 Bot NSFW",
            value=f"`{models_info['nsfw_bot']['primary']['model']}` ({models_info['nsfw_bot']['primary']['status']})",
            inline=True
        )
        embed.add_field(name="🗄️ Database", value=f"`{db_type}`", inline=False)
        embed.add_field(name="⚡ Bộ Nhớ Cache", value=f"`{cache_type}`", inline=True)
        embed.add_field(name="📋 Số Kênh Auto-chat", value=f"`{len(proactive_engine.allowed_channels)}` kênh", inline=True)
        embed.set_footer(text=f"Antigravity Neneka Engine • Ping: {round(self.bot.latency * 1000)}ms")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))

