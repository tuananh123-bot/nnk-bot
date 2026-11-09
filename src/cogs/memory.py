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

    @app_commands.command(name="nickname", description="🏷️ Đặt biệt danh để Neneka gọi bạn hoặc một thành viên khác")
    @app_commands.describe(
        name="Tên biệt danh mới (nhập 'reset' để xóa biệt danh trở về mặc định)",
        target="Thành viên cần đặt biệt danh (bỏ trống để đặt cho chính bạn)"
    )
    async def cmd_nickname(
        self,
        interaction: discord.Interaction,
        name: str,
        target: Optional[discord.Member] = None
    ):
        target_user = target or interaction.user
        clean_name = name.strip().strip("'\"")

        if clean_name.lower() in ["reset", "xóa", "huy", "clear", "mặc định"]:
            await memory_engine.set_preferred_name(str(target_user.id), None, target_user.name)
            await interaction.response.send_message(
                f"✨ Đã xóa biệt danh của {target_user.mention}. Kể từ giờ Neneka sẽ gọi lại bằng tên hiển thị mặc định.",
                ephemeral=False
            )
            return

        await memory_engine.set_preferred_name(str(target_user.id), clean_name, target_user.name)
        embed = discord.Embed(
            title="🏷️ Đã Ghi Nhận Biệt Danh Mới!",
            description=(
                f"Fufu... Kể từ giờ ta sẽ gọi {target_user.mention} là **'{clean_name}'**.\n"
                f"Ký ức này đã được khắc sâu vào ma thuật nhận diện thực tại của ta rồi nhé."
            ),
            color=0x9b59b6
        )
        embed.set_footer(text="Seven Crowns Identity Registry • Princess Connect! Re:Dive")
        await interaction.response.send_message(embed=embed)

    @commands.command(name="nickname", aliases=["setname", "bietdanh", "name"])
    async def pcmd_nickname(self, ctx: commands.Context, *, args: Optional[str] = None):
        """Lệnh !n nickname [@user] <tên> để đặt biệt danh cho người khác hoặc bản thân"""
        if not args or not args.strip():
            await ctx.reply(
                "❌ Cú pháp: `!n nickname [@user] <tên biệt danh>`\n"
                "• *Đặt cho người khác:* `!n nickname @TuanAnh Bé ngoan`\n"
                "• *Đặt cho bản thân:* `!n nickname Bé ngoan`\n"
                "• *Xóa biệt danh:* `!n nickname [@user] reset`"
            )
            return

        clean_text = args.strip()
        if ctx.message.mentions:
            target_user = ctx.message.mentions[0]
            clean_text = clean_text.replace(f"<@{target_user.id}>", "").replace(f"<@!{target_user.id}>", "").strip()
        else:
            target_user = ctx.author

        clean_name = clean_text.strip().strip("'\"")
        if not clean_name:
            await ctx.reply("❌ Hãy nhập tên biệt danh bạn muốn đặt! Ví dụ: `!n nickname @user Mèo con`")
            return

        if clean_name.lower() in ["reset", "xóa", "huy", "clear", "mặc định"]:
            await memory_engine.set_preferred_name(str(target_user.id), None, target_user.name)
            await ctx.reply(f"✨ Đã xóa biệt danh của {target_user.mention}. Neneka sẽ gọi lại bằng tên mặc định.")
            return

        await memory_engine.set_preferred_name(str(target_user.id), clean_name, target_user.name)
        embed = discord.Embed(
            title="🏷️ Đã Ghi Nhận Biệt Danh Mới!",
            description=(
                f"Fufu... Kể từ giờ ta sẽ gọi {target_user.mention} là **'{clean_name}'**.\n"
                f"Ký ức này đã được khắc sâu vào ma thuật nhận diện thực tại của ta rồi nhé."
            ),
            color=0x9b59b6
        )
        embed.set_footer(text="Seven Crowns Identity Registry • Princess Connect! Re:Dive")
        await ctx.reply(embed=embed)

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

