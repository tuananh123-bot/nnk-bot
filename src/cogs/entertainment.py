# src/cogs/entertainment.py
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.config import settings
from src.bond.engine import BondEngine
from src.entertainment.fortune import get_daily_fortune
from src.entertainment.mirror_game import start_mirror_game
from src.voice.sleep_manager import sleep_manager

bond_engine = BondEngine()

class EntertainmentCog(commands.Cog):
    """Quản lý các tính năng giải trí ma thuật của Neneka: Gieo quẻ, Mini-game Gương Ảo Ảnh và Ru ngủ ban đêm"""
    def __init__(self, bot):
        self.bot = bot

    # =========================================================================
    # 1. GIEO QUẺ VẬN MỆNH MỖI NGÀY (/fortune, /daily, !n fortune, !n daily)
    # =========================================================================
    @app_commands.command(name="fortune", description="🔮 Gieo quẻ vận mệnh mỗi ngày và nhận điểm gắn kết từ Thất Vương Neneka")
    async def cmd_fortune(self, interaction: discord.Interaction):
        await self._handle_fortune(interaction.user, interaction.response.send_message)

    @app_commands.command(name="daily", description="✨ Điểm danh mỗi ngày và bói vận thế hôm nay cùng Neneka")
    async def cmd_daily(self, interaction: discord.Interaction):
        await self._handle_fortune(interaction.user, interaction.response.send_message)

    @commands.command(name="fortune", aliases=["daily", "gieoque", "boi", "que"])
    async def pcmd_fortune(self, ctx):
        """Gieo quẻ vận mệnh mỗi ngày (!n fortune / !n daily / !n gieoque)"""
        await self._handle_fortune(ctx.author, ctx.reply)

    async def _handle_fortune(self, user: discord.User | discord.Member, send_func):
        is_creator = (str(user.id) == str(settings.CREATOR_USER_ID))
        fortune, is_cached = get_daily_fortune(
            discord_user_id=str(user.id),
            username=user.display_name,
            is_creator=is_creator
        )

        embed = discord.Embed(
            title=f"🔮 Quẻ Vận Mệnh Hôm Nay • {fortune['badge']}",
            description=f"**Ngày {fortune['date_str']} • Quẻ số phận của {user.mention}:**\n*{fortune.get('description', '')}*",
            color=fortune["color"]
        )

        embed.add_field(name="📜 Quẻ Bản Mệnh", value=f"**{fortune['title']}** - **{fortune['kanji']}**", inline=True)
        embed.add_field(name="🍀 Chỉ Số Vận Khí", value=f"**{fortune['score']}%** / 100%", inline=True)
        embed.add_field(name="🎮 Vận May Gacha", value=f"`{fortune['gacha_luck']}`", inline=True)

        embed.add_field(name="🎨 Màu Sắc Hộ Mệnh", value=f"*{fortune['lucky_color']}*", inline=True)
        embed.add_field(name="🍽️ Món Ăn May Mắn", value=f"*{fortune['lucky_food']}*", inline=True)
        embed.add_field(name="🪄 Vật Phẩm May Mắn", value=f"*{fortune['lucky_item']}*", inline=True)

        embed.add_field(name="💜 Lời Phán Của Thất Vương", value=f"*{fortune['oracle']}*", inline=False)
        embed.add_field(name="🇯🇵 Lời Chúc Tiếng Nhật", value=f"「*{fortune['japanese_oracle']}*」", inline=False)

        # Xử lý điểm thưởng gắn kết
        if not is_cached:
            if not is_creator:
                lvl, pts, up = await bond_engine.add_bond_points(
                    str(user.id),
                    points=15,
                    event_type="DAILY_FORTUNE",
                    description="Gieo quẻ vận mệnh mỗi ngày"
                )
                embed.add_field(
                    name="🎁 Phần Thưởng Điểm Danh Hôm Nay",
                    value=f"+15 điểm gắn kết Bond! (Tổng: **{pts}** pts - Cấp {lvl})",
                    inline=False
                )
                if up:
                    embed.add_field(name="🎉 THĂNG CẤP GẮN KẾT!", value=f"Chúc mừng! Cậu vừa thăng tiến lên **Cấp {up}** cùng Neneka!", inline=False)
            else:
                embed.add_field(
                    name="👑 Đặc Quyền Đấng Sáng Tạo",
                    value="*Sheffy-sama sở hữu vận mệnh vĩnh cửu và ma lực toàn năng vô tận!*",
                    inline=False
                )
        else:
            embed.set_footer(text="Fufu... Hôm nay cậu đã khai mở quẻ rồi. Hãy kiên tâm giữ trọn vận khí nhé!")

        await send_func(embed=embed)

    # =========================================================================
    # 2. MINI-GAME GƯƠNG ẢO ẢNH (/mirror, !n mirror, !n phanthan)
    # =========================================================================
    @app_commands.command(name="mirror", description="🪞 Mini-game Gương Ảo Ảnh: Thử tài tinh mắt đoán bản thể chân chính của Neneka")
    async def cmd_mirror(self, interaction: discord.Interaction):
        embed, view, err = start_mirror_game(str(interaction.user.id), bond_engine)
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return
        await interaction.response.send_message(embed=embed, view=view)

    @commands.command(name="mirror", aliases=["phanthan", "guong", "clone"])
    async def pcmd_mirror(self, ctx):
        """Mini-game Gương Ảo Ảnh (!n mirror / !n phanthan / !n guong)"""
        embed, view, err = start_mirror_game(str(ctx.author.id), bond_engine)
        if err:
            await ctx.reply(err)
            return
        await ctx.reply(embed=embed, view=view)

    # =========================================================================
    # 3. CHẾ ĐỘ RU NGỦ BAN ĐÊM (/sleep, !n sleep, !n ngungon)
    # =========================================================================
    @app_commands.command(name="sleep", description="🌙 Chế độ ru ngủ ban đêm: Neneka kể chuyện và thì thầm lời ru tiếng Nhật êm đềm")
    @app_commands.describe(theme="Chủ đề ru ngủ (ví dụ: đếm cừu, ánh trăng, trà thảo mộc, gió đêm...)")
    async def cmd_sleep(self, interaction: discord.Interaction, theme: Optional[str] = None):
        await interaction.response.defer()
        guild = interaction.guild
        embed, audio_file, note = await sleep_manager.execute_sleep(interaction.user, theme=theme, guild=guild)

        if note:
            embed.description = f"{note}\n\n{embed.description}"

        if audio_file:
            discord_file = discord.File(audio_file, filename="neneka_lullaby.mp3")
            await interaction.followup.send(embed=embed, file=discord_file)
        else:
            await interaction.followup.send(embed=embed)

    @commands.command(name="sleep", aliases=["runguyen", "ngungon", "lullaby"])
    async def pcmd_sleep(self, ctx, *, theme: Optional[str] = None):
        """Chế độ ru ngủ ban đêm (!n sleep [chủ đề] / !n ngungon)"""
        async with ctx.typing():
            guild = ctx.guild
            embed, audio_file, note = await sleep_manager.execute_sleep(ctx.author, theme=theme, guild=guild)

            if note:
                embed.description = f"{note}\n\n{embed.description}"

            if audio_file:
                discord_file = discord.File(audio_file, filename="neneka_lullaby.mp3")
                await ctx.reply(embed=embed, file=discord_file)
            else:
                await ctx.reply(embed=embed)


async def setup(bot):
    await bot.add_cog(EntertainmentCog(bot))

