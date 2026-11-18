# src/cogs/image_gen.py
"""
Cog xử lý tính năng tạo ảnh AI (Text-to-Image).
Hỗ trợ đa nhà cung cấp:
1. Google Gemini Nano Banana (Flash Image: gemini-2.5-flash-image / gemini-nano-banana-2.1) - Dùng cho tranh thông thường
2. Uncensored AI API (https://api.uncensored.com) - Model: seedream-v5 - Dùng cho tranh 18+ / Uncensored
3. AI Horde Distributed Cluster (https://aihorde.net) - SDXL / Pony / Anime - Dự phòng miễn phí không giới hạn
Hỗ trợ cả Slash command (/imagine, /draw) và tiền tố (!n draw, !n imagine).
"""

import io
import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.config import settings
from src.llm.gemini_image_client import gemini_image_client
from src.llm.horde_client import horde_client
from src.llm.uncensored_image_client import uncensored_image_client
from src.cogs.chat import _nsfw_runtime_channels

logger = logging.getLogger("Neneka.ImageGen")


class ImageGenCog(commands.Cog):
    """Quản lý tính năng vẽ tranh & tạo ảnh nghệ thuật của Thất Vương Neneka."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_channel_nsfw(self, channel: Optional[discord.abc.GuildChannel]) -> bool:
        """Kiểm tra xem kênh có được phép tạo ảnh 18+/NSFW không."""
        if not channel:
            return False
        # Discord native NSFW flag
        if hasattr(channel, "is_nsfw") and channel.is_nsfw():
            return True
        # Cấu hình bot NSFW channels
        ch_id = getattr(channel, "id", 0)
        if ch_id in settings.nsfw_channel_id_list or ch_id in _nsfw_runtime_channels:
            return True
        return False

    @app_commands.command(
        name="imagine",
        description="🎨 Vẽ tranh và tạo ảnh AI (Google Nano Banana 🍌 / Uncensored AI / AI Horde)"
    )
    @app_commands.describe(
        prompt="Mô tả bức tranh bạn muốn Neneka phác họa (tiếng Anh hoặc tiếng Việt)",
        orientation="Định dạng khung hình: portrait (dọc), landscape (ngang), square (vuông)",
        style="Phong cách: anime (mặc định), realistic (chân thực), cinematic (điện ảnh)",
        provider="Nhà cung cấp: auto (tự động), nanobanana (Google Nano Banana), uncensored, horde"
    )
    @app_commands.choices(
        orientation=[
            app_commands.Choice(name="📱 Khung Dọc (Portrait - 9:16)", value="portrait"),
            app_commands.Choice(name="🖼️ Khung Ngang (Landscape - 16:9)", value="landscape"),
            app_commands.Choice(name="⏹️ Khung Vuông (Square - 1:1)", value="square"),
        ],
        style=[
            app_commands.Choice(name="🌸 Anime Nghệ Thuật (Mặc định)", value="anime"),
            app_commands.Choice(name="📸 Chân Thực / Photorealistic", value="realistic"),
            app_commands.Choice(name="🎬 Điện Ảnh / Cinematic Warm", value="cinematic"),
        ],
        provider=[
            app_commands.Choice(name="✨ Tự Động (Tranh thường: Nano Banana 🍌, 18+: Uncensored AI)", value="auto"),
            app_commands.Choice(name="🍌 Google Nano Banana (Gemini Flash Image)", value="nanobanana"),
            app_commands.Choice(name="🔞 Uncensored AI (seedream-v5)", value="uncensored"),
            app_commands.Choice(name="🌸 AI Horde Cluster (Anime / SDXL / Pony)", value="horde"),
        ]
    )
    async def cmd_imagine_slash(
        self,
        interaction: discord.Interaction,
        prompt: str,
        orientation: Optional[str] = "portrait",
        style: Optional[str] = "anime",
        provider: Optional[str] = "auto",
    ):
        await interaction.response.defer(thinking=True)
        await self._process_image_generation(
            reply_target=interaction.followup,
            author=interaction.user,
            channel=interaction.channel,
            prompt=prompt,
            orientation=orientation or "portrait",
            style=style or "anime",
            provider=provider or "auto",
        )

    @app_commands.command(name="draw", description="🖌️ Phác họa nhanh một bức tranh theo yêu cầu bằng ma lực Metamorphose")
    @app_commands.describe(prompt="Mô tả bức tranh bạn muốn vẽ")
    async def cmd_draw_slash(self, interaction: discord.Interaction, prompt: str):
        await interaction.response.defer(thinking=True)
        await self._process_image_generation(
            reply_target=interaction.followup,
            author=interaction.user,
            channel=interaction.channel,
            prompt=prompt,
            orientation="portrait",
            style="anime",
            provider="auto",
        )

    @commands.command(name="draw", aliases=["imagine", "paint", "art"])
    async def cmd_draw_prefix(self, ctx: commands.Context, *, prompt: Optional[str] = None):
        """Lệnh tiền tố vẽ ảnh: !n draw <mô tả> hoặc !n imagine <mô tả>."""
        if not prompt:
            await ctx.reply(
                "Fufu... Cậu muốn ta vẽ gì nào? Hãy miêu tả chi tiết nhé, ví dụ: `!n draw neneka enjoying tea in the royal garden`."
            )
            return

        async with ctx.typing():
            await self._process_image_generation(
                reply_target=ctx,
                author=ctx.author,
                channel=ctx.channel,
                prompt=prompt,
                orientation="portrait",
                style="anime",
                provider="auto",
            )

    async def _process_image_generation(
        self,
        reply_target,
        author: discord.User,
        channel,
        prompt: str,
        orientation: str = "portrait",
        style: str = "anime",
        provider: str = "auto",
    ):
        has_gemini = gemini_image_client.is_available()
        has_uncensored = uncensored_image_client.is_available()
        has_horde = horde_client.is_available()

        if not has_gemini and not has_uncensored and not has_horde:
            msg = (
                "⚠️ *Chưa có API Key tạo ảnh nào được cấu hình.* "
                "Vui lòng thiết lập `GEMINI_API_KEY`, `UNCENSORED_API_KEY` hoặc `AI_HORDE_API_KEY` trong file `.env`."
            )
            if hasattr(reply_target, "send"):
                await reply_target.send(msg)
            else:
                await reply_target.reply(msg)
            return

        # Tính toán kích thước theo orientation
        if orientation == "landscape":
            width, height = 768, 512
        elif orientation == "square":
            width, height = 512, 512
        else:
            width, height = 512, 768

        # Tùy biến prompt theo phong cách
        enhanced_prompt = prompt.strip()
        if style == "cinematic":
            enhanced_prompt += ", cinematic lighting, warm golden tones, film grain, highly detailed, 8k resolution"
        elif style == "realistic":
            enhanced_prompt += ", photorealistic, realistic skin texture, soft shadows, sharp focus, 8k uhd"
        else:
            enhanced_prompt += ", anime aesthetic, vibrant colors, detailed illustration, pixiv trending"

        is_nsfw = self._is_channel_nsfw(channel)

        result = None
        used_provider_name = ""
        fallback_happened = False
        error_reasons = []

        # 1. Tranh thông thường: Ưu tiên Google Nano Banana (nếu không phải 18+ hoặc khi người dùng chỉ định nanobanana)
        use_nano_banana = (provider == "nanobanana") or (provider == "auto" and not is_nsfw and has_gemini)

        if use_nano_banana and has_gemini:
            try:
                result = await gemini_image_client.generate_image(
                    prompt=enhanced_prompt,
                    orientation=orientation,
                )
                used_provider_name = result.get("provider", "Google Nano Banana 🍌")
            except Exception as e:
                err_str = str(e)
                logger.warning(f"Google Nano Banana image gen thất bại: {err_str}")
                error_reasons.append(f"Google Nano Banana: {err_str}")

                if provider == "auto":
                    fallback_happened = True
                    logger.info("Nano Banana không khả dụng, đang tự động fallback sang Horde / Uncensored AI...")
                elif provider == "nanobanana":
                    err_msg = f"❌ *Google Nano Banana gặp lỗi:* `{err_str}`"
                    if "ResourceExhausted" in err_str or "quota" in err_str.lower():
                        err_msg += "\n💡 *Gợi ý:* Hạn mức Nano Banana trong ngày đã tạm hết. Bạn có thể dùng `/imagine provider:horde` để vẽ qua AI Horde hoàn toàn miễn phí!"
                    if hasattr(reply_target, "send"):
                        await reply_target.send(err_msg)
                    else:
                        await reply_target.reply(err_msg)
                    return

        # 2. Tranh 18+ / Uncensored AI: Nếu là kênh NSFW hoặc người dùng chỉ định uncensored, hoặc auto fallback
        if not result and has_uncensored:
            try_uncensored = (provider == "uncensored") or (provider == "auto" and (is_nsfw or fallback_happened or not has_gemini))
            if try_uncensored:
                try:
                    result = await uncensored_image_client.generate_image(
                        prompt=enhanced_prompt,
                        model=settings.UNCENSORED_IMAGE_MODEL or "seedream-v5",
                        timeout_seconds=90,
                    )
                    used_provider_name = f"Uncensored AI ({result.get('model', 'seedream-v5')})"
                except Exception as e:
                    err_str = str(e)
                    logger.warning(f"Uncensored AI image gen thất bại: {err_str}")
                    error_reasons.append(f"Uncensored AI: {err_str}")
                    if provider == "auto" and has_horde:
                        fallback_happened = True
                        logger.info("Đang tự động fallback sang AI Horde Cluster...")
                    elif provider == "uncensored":
                        err_msg = f"❌ *Uncensored AI không thể hoàn thành yêu cầu:* `{err_str}`"
                        if "credit" in err_str.lower():
                            err_msg += "\n💡 *Gợi ý:* Tài khoản Uncensored AI hiện chưa có đủ credit. Bạn có thể dùng `/imagine provider:horde` hoặc `!n draw` để dùng cluster AI Horde miễn phí!"
                        if hasattr(reply_target, "send"):
                            await reply_target.send(err_msg)
                        else:
                            await reply_target.reply(err_msg)
                        return

        # 3. AI Horde (Dự phòng miễn phí cuối cùng hoặc khi người dùng chỉ định horde)
        if not result and has_horde:
            try_horde = (provider == "horde") or (provider == "auto") or fallback_happened
            if try_horde:
                try:
                    result = await horde_client.generate_image(
                        prompt=enhanced_prompt,
                        width=width,
                        height=height,
                        is_nsfw=is_nsfw,
                        timeout_seconds=120,
                    )
                    used_provider_name = f"AI Horde ({result.get('model', 'Horde Diffusion')})"
                except TimeoutError:
                    err_msg = (
                        "*khẽ đặt tách trà xuống, ánh mắt có chút tiếc nuối* Fufu... Các thợ vẽ phân tán trên mạng lưới AI Horde "
                        "đang bận rộn xử lý hàng đợi quá đông nên lượt vẽ này bị quá hạn. Cậu chờ một chút rồi thử lại xem sao nhé?"
                    )
                    if hasattr(reply_target, "send"):
                        await reply_target.send(err_msg)
                    else:
                        await reply_target.reply(err_msg)
                    return
                except Exception as e:
                    logger.error(f"Lỗi khi tạo ảnh qua AI Horde: {e}")
                    error_reasons.append(f"AI Horde: {e}")

        # 4. Kết quả thành công (Hỗ trợ cả file attachment bytes và image URL)
        if result and (result.get("image_bytes") or result.get("img_url")):
            file = None
            embed = discord.Embed(
                title="✨ Ma Lực Thực Tại • Phác Họa Hoàn Tất",
                description=f"*{author.mention}, ảo ảnh mà cậu mong ước đã được dệt thành hình:*\n> **Prompt:** {prompt}",
                color=0x9b59b6,
            )

            if result.get("image_bytes"):
                file = discord.File(io.BytesIO(result["image_bytes"]), filename="neneka_art.png")
                embed.set_image(url="attachment://neneka_art.png")
            elif result.get("img_url"):
                embed.set_image(url=result["img_url"])

            embed.add_field(name="📐 Kích Thước", value=f"`{width}x{height}` ({orientation})", inline=True)
            embed.add_field(name="🎨 Worker / Model", value=f"`{result.get('model', 'AI Model')}`", inline=True)
            if result.get("seed"):
                embed.add_field(name="🌱 Seed", value=f"`{result.get('seed')}`", inline=True)

            footer_text = f"Seven Crowns Metamorphose Art • Powered by {used_provider_name}"
            if fallback_happened:
                footer_text += " (Đã tự động chuyển đổi sang kênh dự phòng)"
            embed.set_footer(text=footer_text)

            send_kwargs = {"embed": embed}
            if file:
                send_kwargs["file"] = file

            if hasattr(reply_target, "send"):
                await reply_target.send(**send_kwargs)
            else:
                await reply_target.reply(**send_kwargs)
            return

        # 5. Tất cả provider đều thất bại
        joined_errors = " | ".join(error_reasons) if error_reasons else "Không nhận được phản hồi hợp lệ."
        err_msg = f"❌ *Ma lực bị phân tán khi tạo ảnh:* `{joined_errors}`"
        if hasattr(reply_target, "send"):
            await reply_target.send(err_msg)
        else:
            await reply_target.reply(err_msg)


async def setup(bot: commands.Bot):
    await bot.add_cog(ImageGenCog(bot))
