# src/voice/piano_search.py
"""
Hệ Thống Tìm Kiếm Toàn Bộ Bài Nhạc Tiếng Piano Trên Toàn Cầu (Global Piano Music Search Engine):
Kết hợp đồng thời 3 kho nhạc mở không cần API key để tìm bất kỳ bản nhạc Piano nào (Cổ điển, Anime OST,
J-Pop, V-Pop, K-Pop, US-UK Piano Cover, Game OST, Lo-fi Piano):
1. Deezer Global Music API — Stream trực tiếp file `.mp3` chất lượng cao + ảnh bìa HD.
2. Apple iTunes Global Music API — Kho >100 triệu bản thu Piano quốc tế + file `.m4a` chất lượng cao.
3. Internet Archive Open Audio — Các bản thu Piano cổ điển & độc tấu Full-Length miễn phí.
Tự động ưu tiên xếp hạng các bản thu Solo Piano / Piano Cover lên đầu và đính kèm menu chọn bài trực tiếp trên Discord!
"""

import asyncio
import hashlib
import logging
import os
import re
from typing import Dict, List, Optional, Any
from urllib.parse import quote_plus

import aiohttp

logger = logging.getLogger("Neneka.PianoSearch")

AUDIO_CACHE_DIR = os.path.abspath("audio_cache")
os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
MAX_AUDIO_DOWNLOAD_BYTES = 15 * 1024 * 1024  # Giới hạn an toàn 15MB cho Discord Attachment

PIANO_ARTIST_BOOST = (
    "piano", "animenz", "fonzi", "riyandi", "yiruma", "hisaishi", "chopin",
    "debussy", "beethoven", "mozart", "liszt", "satie", "rousseau", "kassia",
    "theishter", "marasy", "ru's piano", "pan piano", "sakamoto", "steinway",
)


def build_piano_search_query(raw_query: str) -> str:
    """Đảm bảo truy vấn luôn hướng tới phiên bản tiếng đàn Piano của bài hát."""
    q = (raw_query or "").strip()
    if not q:
        return "solo piano anime classical"
    # Lọc các cụm từ khẩu lệnh tiếng Việt thừa ở đầu câu
    q = re.sub(
        r"^(?:tìm\s+kiếm|tìm\s+bài\s+nhạc|tìm\s+nhạc|tìm\s+bài|mở\s+nhạc|mở\s+bài|phát\s+nhạc|phát\s+bài|cho\s+nghe)\s+",
        "",
        q,
        flags=re.IGNORECASE,
    ).strip()
    if "piano" not in q.lower() and "dương cầm" not in q.lower():
        return f"{q} piano"
    q = re.sub(r"dương cầm", "piano", q, flags=re.IGNORECASE)
    return q


def _score_piano_relevance(track: Dict[str, Any], original_query: str) -> int:
    """Chấm điểm độ khớp để đưa các bản độc tấu Piano / Piano Cover chuẩn nhất lên đầu."""
    score = 0
    title_l = (track.get("title") or "").lower()
    artist_l = (track.get("artist") or "").lower()
    album_l = (track.get("album") or "").lower()
    combined = f"{title_l} {artist_l} {album_l}"

    if "piano" in title_l:
        score += 35
    if "piano" in album_l:
        score += 20
    if any(p in combined for p in PIANO_ARTIST_BOOST):
        score += 25
    if any(k in title_l for k in ("solo", "instrumental", "cover", "version", "arrangement", "nocturne", "sonata")):
        score += 12

    # Cộng điểm nếu khớp từ khóa tên bài gốc của người dùng
    clean_orig = re.sub(r"\bpiano\b", "", (original_query or "").lower()).strip()
    for word in [w for w in re.split(r"\W+", clean_orig) if len(w) >= 2]:
        if word in title_l:
            score += 18
        elif word in artist_l:
            score += 10

    # Ưu tiên định dạng .mp3 để tương thích 100% mọi thiết bị Discord
    if (track.get("audio_ext") or "") == "mp3":
        score += 8
    if track.get("is_full_track"):
        score += 10

    return score


async def _search_deezer(session: aiohttp.ClientSession, query: str, limit: int = 8) -> List[Dict[str, Any]]:
    url = f"https://api.deezer.com/search?q={quote_plus(query)}&limit={limit}"
    results: List[Dict[str, Any]] = []
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            for item in data.get("data", []):
                preview = item.get("preview")
                if not preview:
                    continue
                title = item.get("title") or "Piano Track"
                artist = (item.get("artist") or {}).get("name") or "Unknown Pianist"
                album_obj = item.get("album") or {}
                results.append({
                    "source": "Deezer Hi-Fi",
                    "title": title,
                    "artist": artist,
                    "album": album_obj.get("title") or "",
                    "duration_sec": int(item.get("duration") or 0),
                    "audio_url": preview,
                    "audio_ext": "mp3",
                    "page_url": item.get("link") or f"https://www.youtube.com/results?search_query={quote_plus(title + ' ' + artist + ' piano')}",
                    "youtube_url": f"https://www.youtube.com/results?search_query={quote_plus(title + ' ' + artist + ' piano')}",
                    "artwork_url": album_obj.get("cover_big") or album_obj.get("cover_medium") or "",
                    "is_full_track": False,
                })
    except Exception as e:
        logger.debug(f"Deezer piano search lỗi nhẹ: {e}")
    return results


async def _search_itunes(session: aiohttp.ClientSession, query: str, limit: int = 8) -> List[Dict[str, Any]]:
    url = f"https://itunes.apple.com/search?term={quote_plus(query)}&media=music&entity=song&limit={limit}"
    results: List[Dict[str, Any]] = []
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)
            for item in data.get("results", []):
                preview = item.get("previewUrl")
                if not preview:
                    continue
                title = item.get("trackName") or "Piano Piece"
                artist = item.get("artistName") or "Unknown Pianist"
                art = (item.get("artworkUrl100") or "").replace("100x100bb", "600x600bb")
                ext = "mp3" if preview.lower().endswith(".mp3") else "m4a"
                dur_ms = int(item.get("trackTimeMillis") or 0)
                results.append({
                    "source": "Apple Music / iTunes",
                    "title": title,
                    "artist": artist,
                    "album": item.get("collectionName") or "",
                    "duration_sec": dur_ms // 1000 if dur_ms else 0,
                    "audio_url": preview,
                    "audio_ext": ext,
                    "page_url": item.get("trackViewUrl") or f"https://www.youtube.com/results?search_query={quote_plus(title + ' ' + artist + ' piano')}",
                    "youtube_url": f"https://www.youtube.com/results?search_query={quote_plus(title + ' ' + artist + ' piano')}",
                    "artwork_url": art,
                    "is_full_track": False,
                })
    except Exception as e:
        logger.debug(f"iTunes piano search lỗi nhẹ: {e}")
    return results


async def _search_internet_archive_full_piano(
    session: aiohttp.ClientSession, query: str, limit: int = 3
) -> List[Dict[str, Any]]:
    """Tìm các bản thu Piano Full-Length miễn phí trên Internet Archive."""
    clean_q = re.sub(r'["\'()]', " ", query).strip()
    ia_q = f"mediatype:(audio) AND format:(VBR MP3) AND (piano) AND ({clean_q})"
    url = (
        f"https://archive.org/advancedsearch.php?q={quote_plus(ia_q)}"
        f"&fl[]=identifier,title,creator&rows={limit}&page=1&output=json"
    )
    results: List[Dict[str, Any]] = []
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)
            docs = (data.get("response") or {}).get("docs") or []
            for doc in docs[:2]:
                ident = doc.get("identifier")
                if not ident:
                    continue
                meta_url = f"https://archive.org/metadata/{ident}"
                async with session.get(meta_url) as m_resp:
                    if m_resp.status != 200:
                        continue
                    m_data = await m_resp.json(content_type=None)
                    files = m_data.get("files") or []
                    mp3_file = None
                    for f in files:
                        fname = f.get("name") or ""
                        fsize = int(f.get("size") or 0)
                        if fname.lower().endswith(".mp3") and 20_000 < fsize <= MAX_AUDIO_DOWNLOAD_BYTES:
                            mp3_file = f
                            break
                    if not mp3_file:
                        continue
                    fname = mp3_file["name"]
                    title = mp3_file.get("title") or doc.get("title") or fname
                    creator = doc.get("creator")
                    if isinstance(creator, list):
                        creator = ", ".join(creator)
                    artist = creator or "Solo Piano Archive"
                    dur_raw = mp3_file.get("length") or "0"
                    try:
                        dur_sec = int(float(dur_raw))
                    except ValueError:
                        dur_sec = 0
                    results.append({
                        "source": "Internet Archive (Full Piano MP3)",
                        "title": str(title),
                        "artist": str(artist),
                        "album": str(doc.get("title") or "Open Piano Collection"),
                        "duration_sec": dur_sec,
                        "audio_url": f"https://archive.org/download/{ident}/{quote_plus(fname).replace('+', '%20')}",
                        "audio_ext": "mp3",
                        "page_url": f"https://archive.org/details/{ident}",
                        "youtube_url": f"https://www.youtube.com/results?search_query={quote_plus(str(title) + ' piano')}",
                        "artwork_url": f"https://archive.org/services/img/{ident}",
                        "is_full_track": True,
                    })
    except Exception as e:
        logger.debug(f"Internet Archive piano search lỗi nhẹ: {e}")
    return results


async def search_piano_songs(raw_query: str, limit: int = 6) -> List[Dict[str, Any]]:
    """
    Tìm kiếm bài nhạc tiếng Piano trên toàn cầu từ nhiều nguồn song song,
    chấm điểm độ chuẩn Piano và khử trùng lặp.
    """
    piano_query = build_piano_search_query(raw_query)
    timeout = aiohttp.ClientTimeout(total=6.5)
    headers = {"User-Agent": "Mozilla/5.0 NenekaPianoBot/2.0"}

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        deezer_res, itunes_res, ia_res = await asyncio.gather(
            _search_deezer(session, piano_query, limit=8),
            _search_itunes(session, piano_query, limit=8),
            _search_internet_archive_full_piano(session, raw_query or piano_query, limit=3),
            return_exceptions=True,
        )

    merged: List[Dict[str, Any]] = []
    for batch in (deezer_res, itunes_res, ia_res):
        if isinstance(batch, list):
            merged.extend(batch)

    # Khử trùng lặp theo (tên bài chuẩn hóa, nghệ sĩ chuẩn hóa)
    deduped: List[Dict[str, Any]] = []
    seen_keys = set()
    for t in merged:
        norm_key = (
            re.sub(r"\W+", "", (t.get("title") or "").lower())[:28],
            re.sub(r"\W+", "", (t.get("artist") or "").lower())[:18],
        )
        if norm_key in seen_keys:
            continue
        seen_keys.add(norm_key)
        t["relevance_score"] = _score_piano_relevance(t, raw_query)
        deduped.append(t)

    deduped.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    return deduped[: max(1, limit)]


async def download_piano_track_audio(track: Dict[str, Any]) -> Optional[str]:
    """Tải file âm thanh (.mp3 / .m4a) của bản nhạc Piano về cache để phát trên Discord."""
    audio_url = track.get("audio_url")
    if not audio_url:
        return None

    ext = track.get("audio_ext") or "mp3"
    digest = hashlib.md5(audio_url.encode("utf-8")).hexdigest()[:12]
    file_path = os.path.join(AUDIO_CACHE_DIR, f"piano_track_{digest}.{ext}")

    if os.path.exists(file_path) and os.path.getsize(file_path) > 1024:
        return file_path

    timeout = aiohttp.ClientTimeout(total=12.0)
    headers = {"User-Agent": "Mozilla/5.0 NenekaPianoBot/2.0"}
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(audio_url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.content.read(MAX_AUDIO_DOWNLOAD_BYTES + 1)
                if not data or len(data) > MAX_AUDIO_DOWNLOAD_BYTES:
                    return None
                with open(file_path, "wb") as f:
                    f.write(data)
                return file_path
    except Exception as e:
        logger.warning(f"Không thể tải audio từ '{audio_url}': {e}")
        return None


def format_duration_mmss(seconds: int) -> str:
    if not seconds or seconds <= 0:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"
