# src/cogs/character.py
import discord
from typing import Optional
from discord import app_commands
from discord.ext import commands

from src.story.costumes import costume_mgr, COSTUME_VARIANTS
from src.story.engine import story_engine

class CharacterCog(commands.Cog):
    """Quản lý thông tin nhân vật, trang phục và kho dữ liệu cốt truyện"""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="neneka", description="👑 Xem hồ sơ nhân vật Thất Vương Utsushimi Neneka")
    async def cmd_neneka(self, interaction: discord.Interaction):
        costume = costume_mgr.get_current_costume(str(interaction.user.id))
        embed = discord.Embed(
            title=f"👑 Hồ Sơ Thất Vương: {costume['name']}",
            description=(
                f"**Danh hiệu:** {costume['title']}\n"
                f"**Tên tiếng Nhật:** {costume['japanese_name']}\n\n"
                f"**Mô tả:** {costume['visual_description']}\n\n"
                f"**Thần thái:** *{costume['personality_flair']}*"
            ),
            color=0x9b59b6
        )
        embed.add_field(name="🏛️ Danh hiệu Canon", value="Một trong Thất Vương (Seven Crowns) huyền thoại", inline=True)
        embed.add_field(name="🔮 Ma pháp", value="Biến Mạo (Metamorphose) & Phân thân hoàn hảo", inline=True)
        embed.set_footer(text="Princess Connect! Re:Dive • Seven Crowns Simulation")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="costume", description="👗 Xem danh sách hoặc thay đổi trang phục của Neneka")
    @app_commands.describe(variant="Chọn trang phục: original (Thất Vương), new_year (Tết Kimono), alpha (Thế giới thực)")
    @app_commands.choices(variant=[
        app_commands.Choice(name="👑 Thất Vương Nguyên Bản (Original)", value="original"),
        app_commands.Choice(name="🌸 Kimono Đón Xuân (New Year)", value="new_year"),
        app_commands.Choice(name="🔬 Nhà Khoa Học Thực Tại (Reality Alpha)", value="alpha"),
    ])
    async def cmd_costume(self, interaction: discord.Interaction, variant: Optional[str] = None):
        if not variant:
            embed = discord.Embed(
                title="👗 Tủ Trang Phục Của Neneka",
                description="Dùng `/costume <tên_trang_phục>` để thay đổi ngoại hình và ngữ điệu tương ứng của Neneka!",
                color=0x9b59b6
            )
            for c in costume_mgr.list_all_costumes():
                embed.add_field(
                    name=f"{c['icon']} {c['name']}",
                    value=f"*{c['visual_description']}*\n👉 Chọn mã: `{c['id'].replace('variant_neneka_', '')}`",
                    inline=False
                )
            await interaction.response.send_message(embed=embed)
            return

        selected = costume_mgr.set_user_costume(str(interaction.user.id), variant)
        if selected:
            await interaction.response.send_message(
                f"✨ {selected['icon']} **Đã chuyển trang phục thành: {selected['name']}!**\n"
                f"*{selected['personality_flair']}*"
            )
        else:
            await interaction.response.send_message("❌ Không tìm thấy trang phục hợp lệ.", ephemeral=True)

    @app_commands.command(name="story", description="📖 Tra cứu cốt truyện Canon và các mẩu truyện của Neneka")
    @app_commands.describe(query="Từ khóa tìm kiếm hoặc thể loại (Main, Character, Bond, Event, AI)")
    async def cmd_story(self, interaction: discord.Interaction, query: Optional[str] = None):
        if not query:
            stories = story_engine.list_by_category()
        else:
            stories = story_engine.search_stories(query)

        if not stories:
            await interaction.response.send_message(f"🔍 Không tìm thấy mẩu truyện nào khớp với từ khóa `{query}`.", ephemeral=True)
            return

        embed = discord.Embed(
            title="📖 Kho Dữ Liệu Ký Ức & Cốt Truyện Neneka",
            description=f"Tìm thấy **{len(stories)}** mẩu truyện được lưu trữ:",
            color=0x9b59b6
        )
        for s in stories[:5]:
            status_badge = "✅ CANON" if s["canon_status"] == "CANON" else "✨ ORIGINAL AI"
            embed.add_field(
                name=f"[{status_badge}] {s['title']} ({s['category']})",
                value=f"**Tập:** `{s['episode_id']}`\n*{s['summary']}*\n**Nhân vật liên quan:** {s['related_characters']}",
                inline=False
            )
        embed.set_footer(text="Princess Connect! Re:Dive • Canon Story Archive")
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(CharacterCog(bot))
