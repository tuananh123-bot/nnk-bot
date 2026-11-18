# src/cogs/bond.py
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.bond.engine import BondEngine, BOND_TIERS

bond_engine = BondEngine()

def build_bond_embed(target: discord.abc.User, info: dict) -> discord.Embed:
    """Xây dựng Embed hiển thị thông tin gắn kết (Bond Profile) của người dùng với Neneka."""
    pts = info["points"]
    lvl = info["level"]
    next_pts = info["next_tier_points"]

    is_creator = info.get("is_creator", False)
    is_max_bond = info.get("is_max_bond", False)
    display_name = getattr(target, "display_name", str(target))

    if is_creator:
        bar = "█" * 12
        pts_val = f"[{bar}] **∞ / ∞ pts** (VĨNH CỬU)"
        color = 0xf1c40f
        title_text = f"👑 Đặc Quyền Gắn Kết - {display_name} (ĐẤNG SÁNG TẠO)"
    elif is_max_bond:
        bar = "█" * 12
        pts_val = f"[{bar}] **{pts} / {pts} pts** (TỐI THƯỢNG - MAX)"
        color = 0xff79c6
        title_text = f"💖 Cấp Độ Gắn Kết Tối Thượng - {display_name}"
    else:
        bar_total = 12
        if next_pts > 0:
            filled = min(bar_total, int((pts / next_pts) * bar_total))
        else:
            filled = bar_total
        bar = "█" * filled + "░" * (bar_total - filled)
        pts_val = f"[{bar}] **{pts}** / {next_pts} pts"
        color = 0xff79c6
        title_text = f"💜 Cấp Độ Gắn Kết - {display_name}"

    embed = discord.Embed(
        title=title_text,
        description=f"**{info['title']}**\n*{info['description']}*",
        color=color
    )
    embed.add_field(
        name="📊 Điểm Gắn Kết",
        value=pts_val,
        inline=False
    )
    embed.add_field(
        name="🗣️ Danh Xưng Neneka Dùng",
        value=f"Tiếng Việt: **\"{info['salutation']}\"**\nTiếng Nhật: **「{info['japanese_salutation']}」**",
        inline=True
    )

    unlocked_list = []
    for tier_idx, t_data in info["all_tiers"].items():
        if tier_idx <= lvl and t_data["unlocked_story"]:
            unlocked_list.append(f"• Cấp {tier_idx}: *{t_data['unlocked_story']}*")

    if unlocked_list:
        embed.add_field(
            name="✨ Ký Ức Đã Mở Khóa",
            value="\n".join(unlocked_list),
            inline=False
        )

    embed.set_footer(text="Bond System • Princess Connect! Re:Dive AI Simulation")
    return embed

class BondCog(commands.Cog):
    """Quản lý cấp độ gắn kết (Bond System) giữa người dùng và Neneka"""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="bond", description="💜 Xem cấp độ gắn kết và hảo cảm với Neneka")
    @app_commands.describe(user="Xem cấp bond của một thành viên khác (bỏ trống để xem của bạn)")
    async def cmd_bond(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        target = user or interaction.user
        info = await bond_engine.get_bond_info(str(target.id))
        embed = build_bond_embed(target, info)
        await interaction.response.send_message(embed=embed)

    @commands.command(name="bond", aliases=["coibond", "xembond", "checkbond", "haocam"])
    async def cmd_bond_prefix(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        """Xem cấp độ gắn kết và điểm hảo cảm của bạn hoặc người khác: !n bond [@người_dùng]"""
        target = user or ctx.author
        info = await bond_engine.get_bond_info(str(target.id))
        embed = build_bond_embed(target, info)
        await ctx.reply(embed=embed)

async def setup(bot):
    await bot.add_cog(BondCog(bot))

