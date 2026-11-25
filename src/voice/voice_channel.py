# src/voice/voice_channel.py
import io
import os
import shutil
import wave
import asyncio
import logging
from typing import Dict, Optional, List, Tuple
import discord

from src.voice.japanese_tts import japanese_tts

logger = logging.getLogger("Neneka.VoiceChannel")


def resolve_ffmpeg_executable() -> Optional[str]:
    """Tìm đường dẫn binary FFmpeg hệ thống hoặc FFmpeg tích hợp sẵn trong `imageio-ffmpeg`."""
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass
    return None


class VoiceChannelManager:
    """
    Quản lý kết nối Voice Channel và hàng đợi phát âm thanh của Neneka:
    - Tự động dùng FFmpeg hệ thống hoặc FFmpeg đóng gói sẵn (`imageio-ffmpeg`) để phát mọi file MP3/M4A/WAV đầy đủ!
    - Dự phòng `discord.PCMAudio` cho file WAV 48kHz Stereo.
    """
    def __init__(self):
        self._voice_clients: Dict[int, discord.VoiceClient] = {}
        self._queues: Dict[int, asyncio.Queue] = {}
        self._is_playing: Dict[int, bool] = {}

    @property
    def ffmpeg_executable(self) -> Optional[str]:
        return resolve_ffmpeg_executable()

    @property
    def has_ffmpeg(self) -> bool:
        return self.ffmpeg_executable is not None

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

    def _build_wav_pcm_source(self, wav_path: str) -> Optional[discord.PCMAudio]:
        """Đọc file WAV 48kHz 16-bit Stereo thành nguồn `discord.PCMAudio`."""
        try:
            with wave.open(wav_path, "rb") as wf:
                if wf.getnchannels() == 2 and wf.getsampwidth() == 2 and wf.getframerate() == 48000:
                    pcm_bytes = wf.readframes(wf.getnframes())
                    return discord.PCMAudio(io.BytesIO(pcm_bytes))
        except Exception as e:
            logger.debug(f"Không thể tạo PCMAudio trực tiếp từ WAV '{wav_path}': {e}")
        return None

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

            source = None
            ffmpeg_exe = self.ffmpeg_executable
            if ffmpeg_exe:
                source = discord.FFmpegPCMAudio(audio_file, executable=ffmpeg_exe)
            elif audio_file.lower().endswith(".wav"):
                source = self._build_wav_pcm_source(audio_file)

            if source is None:
                logger.warning("Không tìm thấy bộ giải mã âm thanh cho Voice Channel.")
                continue

            finished_event = asyncio.Event()

            def after_play(error):
                if error:
                    logger.error(f"Lỗi khi phát âm thanh Voice Channel: {error}")
                finished_event.set()

            try:
                vc.play(source, after=after_play)
                await finished_event.wait()
            except Exception as e:
                logger.error(f"Exception khi play audio: {e}")
                break

        self._is_playing[guild_id] = False


voice_channel_mgr = VoiceChannelManager()
