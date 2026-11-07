# src/cogs/memory.py
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.memory.engine import MemoryEngine

memory_engine = MemoryEngine()

class MemoryCog(commands.Cog):
    """Quản lý và minh bạch ký ức dài hạn theo quy chuẩn bảo mật riêng tư"""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="memory", description="🧠 Xem những ký ức mà Neneka đã ghi nhớ về bạn")
    async def cmd_memory(self, interaction: discord.Interaction):
        mems = await memory_engine.get_user_memories(str(interaction.user.id))
        if not mems:
            await interaction.response.send_message(
                "Fufu... Ta chưa ghi nhận ký ức dài hạn đặc biệt nào về cậu cả. Hãy chia sẻ thêm sở thích hoặc câu chuyện của cậu nhé.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"🧠 Ký Ức Dài Hạn Của Neneka Về {interaction.user.display_name}",
            description=f"Neneka đang lưu giữ **{len(mems)}** dữ kiện quan trọng về cậu:",
            color=0x3498db
        )
        for m in mems[:8]:
            embed.add_field(
                name=f"[{m['category'].upper()}] (ID: `{m['id'][:8]}` - {m['created_at']})",
                value=f"• *{m['fact']}*",
                inline=False
            )
        embed.set_footer(text="Dùng lệnh /forget <id> để yêu cầu xóa một ký ức nếu bạn muốn.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="forget", description="🗑️ Yêu cầu Neneka xóa một hoặc toàn bộ ký ức về bạn")
    @app_commands.describe(memory_id="Nhập ID ký ức cần xóa (bỏ trống để xóa TOÀN BỘ ký ức)")
    async def cmd_forget(self, interaction: discord.Interaction, memory_id: Optional[str] = None):
        deleted = await memory_engine.delete_user_memory(str(interaction.user.id), memory_id)
        if deleted > 0:
            target_str = f"ký ức mang ID `{memory_id}`" if memory_id else "toàn bộ ký ức dài hạn"
            await interaction.response.send_message(
                f"✨ Đã xóa thành công **{deleted}** {target_str} khỏi cơ sở dữ liệu của Neneka.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("❌ Không tìm thấy ký ức nào phù hợp để xóa.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(MemoryCog(bot))

