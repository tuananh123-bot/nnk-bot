# src/voice/voice_channel.py
import os
import shutil
import asyncio
import logging
from typing import Dict, Optional, List, Tuple
import discord

from src.voice.japanese_tts import japanese_tts

logger = logging.getLogger("Neneka.VoiceChannel")

class VoiceChannelManager:
    """
    Quản lý kết nối Voice Channel và hàng đợi phát âm thanh của Neneka
    - Kết nối và rời Voice Channel an toàn
    - Hàng đợi phát âm thanh (Audio Queue) tránh xung đột
    - Sử dụng FFmpegPCMAudio khi có FFmpeg, thông báo lịch thiệp nếu thiếu binary
    """
    def __init__(self):
        self._voice_clients: Dict[int, discord.VoiceClient] = {}  # guild_id -> VoiceClient
        self._queues: Dict[int, asyncio.Queue] = {}               # guild_id -> Queue[str]
        self._is_playing: Dict[int, bool] = {}

    @property
    def has_ffmpeg(self) -> bool:
        return shutil.which("ffmpeg") is not None

    async def join_channel(self, channel: discord.VoiceChannel) -> Tuple[bool, str, Optional[discord.VoiceClient]]:
        guild_id = channel.guild.id
        if guild_id in self._voice_clients and self._voice_clients[guild_id].is_connected():
            vc = self._voice_clients[guild_id]
            if vc.channel.id == channel.id:
                return True, "Neneka đã ở trong phòng này rồi.", vc
            await vc.move_to(channel)
            return True, f"Neneka đã chuyển sang phòng thoại {channel.name}.", vc

        try:
            vc = await channel.connect()
            self._voice_clients[guild_id] = vc
            self._queues[guild_id] = asyncio.Queue()
            self._is_playing[guild_id] = False
            return True, f"Neneka đã tham gia phòng thoại {channel.name}.", vc
        except Exception as e:
            logger.error(f"Lỗi khi tham gia voice channel {channel.name}: {e}")
            return False, f"Không thể tham gia phòng thoại: {e}", None

    async def leave_channel(self, guild_id: int) -> Tuple[bool, str]:
        if guild_id in self._voice_clients and self._voice_clients[guild_id].is_connected():
            vc = self._voice_clients[guild_id]
            await vc.disconnect(force=True)
            del self._voice_clients[guild_id]
            self._is_playing[guild_id] = False
            return True, "Neneka đã rời khỏi phòng thoại."
        return False, "Neneka hiện không ở trong phòng thoại nào."

    def get_voice_client(self, guild_id: int) -> Optional[discord.VoiceClient]:
        return self._voice_clients.get(guild_id)

    async def enqueue_audio(self, guild_id: int, audio_path: str):
        if guild_id not in self._queues:
            self._queues[guild_id] = asyncio.Queue()
        await self._queues[guild_id].put(audio_path)
        if not self._is_playing.get(guild_id, False):
            asyncio.create_task(self._process_queue(guild_id))

    async def _process_queue(self, guild_id: int):
        self._is_playing[guild_id] = True
        vc = self._voice_clients.get(guild_id)
        queue = self._queues.get(guild_id)

        if not vc or not queue:
            self._is_playing[guild_id] = False
            return

        while not queue.empty():
            audio_file = await queue.get()
            if not os.path.exists(audio_file):
                continue

            if not self.has_ffmpeg:
                logger.warning("FFmpeg chưa được cài đặt trên máy chủ. Bỏ qua phát trực tiếp trên VC.")
                break

            finished_event = asyncio.Event()

            def after_play(error):
                if error:
                    logger.error(f"Lỗi khi phát âm thanh Voice Channel: {error}")
                finished_event.set()

            try:
                source = discord.FFmpegPCMAudio(audio_file)
                vc.play(source, after=after_play)
                await finished_event.wait()
            except Exception as e:
                logger.error(f"Exception khi play audio: {e}")
                break

        self._is_playing[guild_id] = False

voice_channel_mgr = VoiceChannelManager()
