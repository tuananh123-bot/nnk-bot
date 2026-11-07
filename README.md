# 👑 Neneka Autonomous Discord AI (Princess Connect! Re:Dive)

> **Mô phỏng nhân vật AI tự trị (Autonomous Character Simulation) cho Utsushimi Neneka (ネネカ) - Thất Vương (Seven Crowns / Metamorph Monarch)**.

Dự án không chỉ là một chatbot thông thường mà là một hệ thống AI đa tầng với tính cách nhất quán, trí nhớ dài hạn riêng biệt cho từng người dùng, Bond System, quản lý trang phục, xác thực Canon Story và phát âm tiếng Nhật tự nhiên qua Voice Channel.

---

## 🏗️ Kiến Trúc Kỹ Thuật (Architecture)

```
d:\download\saber/
├── src/
│   ├── config.py                 # Cấu hình Pydantic BaseSettings, tải biến môi trường
│   ├── bot.py                    # Khởi tạo Discord Bot, nạp Cogs và đồng bộ Slash Commands
│   ├── database/
│   │   ├── connection.py         # Kết nối PostgreSQL Async (tự động fallback SQLite)
│   │   └── models.py             # 19 Bảng dữ liệu chuẩn quan hệ (Users, Memories, Bonds, v.v.)
│   ├── cache/
│   │   └── redis_client.py       # Bộ nhớ đệm Redis Async (tự động fallback RAM In-Memory)
│   ├── personality/
│   │   ├── engine.py             # Personality Engine (confidence, curiosity, affection, v.v.)
│   │   └── prompts.py            # Hệ thống System Prompts đa ngôn ngữ (VN, JA, EN)
│   ├── memory/
│   │   └── engine.py             # Trí nhớ dài hạn, ngắn hạn, trích xuất sự thật & bảo mật
│   ├── bond/
│   │   └── engine.py             # Bond System 7 cấp độ (0 đến 6+), chống spam, mở khóa danh xưng
│   ├── story/
│   │   ├── engine.py             # Canon Story Archive, tra cứu cốt truyện & chống bịa đặt
│   │   └── costumes.py           # Quản lý trang phục: Original, New Year, Alpha
│   ├── autonomous/
│   │   └── proactive_engine.py   # Chế độ A (Mention), B (Auto-chat), C (Autonomous) & Anti-Spam
│   ├── voice/
│   │   ├── base.py               # Interface BaseTTSProvider
│   │   ├── japanese_tts.py       # Japanese TTS Provider 10 Preset cảm xúc (Edge-TTS / Gemini)
│   │   └── voice_channel.py      # Quản lý phát âm thanh phòng thoại Discord & FFmpeg queue
│   ├── llm/
│   │   └── groq_client.py        # Async Groq Client (retry, exponential backoff, token limit)
│   └── cogs/                     # Modular Discord Cogs (character, bond, memory, voice, admin, chat)
├── tests/                        # 10 Bộ Test tự động kiểm thử toàn diện bằng Pytest
├── Dockerfile                    # Containerization với FFmpeg
├── docker-compose.yml            # PostgreSQL 16 + Redis 7 + Bot
├── main.py                       # Điểm khởi chạy ứng dụng
└── requirements.txt
```

---

## 🚀 Tính Năng Chính

### 1. Tính Cách Nhất Quán (Personality Engine)
- Sở hữu 8 biến trạng thái nội tâm: `confidence`, `curiosity`, `affection`, `trust`, `amusement`, `irritation`, `seriousness`, `emotional_state`.
- Phản xạ chân thực với điểm nhạy cảm Canon: Trêu chọc tuổi tác/chiều cao sẽ kích hoạt dỗi yêu sắc sảo (`annoyed_chilly`), khen ngợi kích hoạt `slight_tsundere`, than mệt kích hoạt bản năng bảo bọc `protective_sister`.
- Phản hồi đa ngữ tự nhiên: Tin nhắn người dùng bằng tiếng Việt trả lời tiếng Việt, tiếng Nhật trả lời tiếng Nhật, tiếng Anh trả lời tiếng Anh.

### 2. Trí Nhớ Dài Hạn (Long-Term Memory Engine)
- **Cô lập dữ liệu tuyệt đối:** Ký ức của người dùng A không bao giờ rò rỉ sang người dùng B hoặc máy chủ khác.
- **Truy xuất thông minh:** Chỉ chắt lọc những dữ kiện liên quan đến câu hỏi hiện tại, không đổ toàn bộ database vào prompt.
- **Quyền riêng tư:** Người dùng có thể xem (`/memory`), xóa (`/forget`) hoặc yêu cầu không theo dõi (`opt-out`).

### 3. Hệ Thống Gắn Kết (Bond System)
- Gồm 7 mốc quan hệ từ Cấp 0 (*Người Lạ*) đến Cấp 6+ (*Mối Quan Hệ Sâu Sắc*).
- Tích lũy điểm qua hội thoại ý nghĩa và tặng quà (`!n gift`), có cơ chế chống spam cày điểm.
- Mở khóa danh xưng đặc biệt (từ *Cậu* -> *Cậu nhóc / 坊や* -> *Cậu bé của ta* -> *Hiệp sĩ của ta / 私の騎士クン*).

### 4. Quản Lý Trang Phục & Cốt Truyện (Costume & Story)
- 3 Biến thể trang phục: **Original** (Thất Vương nguyên bản), **New Year** (Kimono đón xuân), **Alpha** (Nhà khoa học thế giới thực).
- Kiểm tra tính xác thực cốt truyện (`CANON`, `ORIGINAL_AI`, `UNKNOWN`) ngăn ngừa bịa đặt Lore sai lệch.

### 5. Giọng Nói Tiếng Nhật (Japanese Voice Engine & Voice Channel)
- Tách rời hoàn toàn khỏi LLM, tích hợp 10 Preset biểu cảm xúc cảm (`Normal`, `Happy`, `Curious`, `Sarcastic`, `Affectionate`, v.v.).
- Khả năng tham gia phòng thoại (`/join`), phát âm thanh (`/speak`), nghe radio (`/radio`) và rời phòng (`/leave`).

### 6. 3 Chế Độ Tự Trị (Autonomous Modes)
- **Mode A (Mention Only):** Chỉ trả lời khi được gọi tên hoặc dùng lệnh.
- **Mode B (Auto Chat):** Tự động tham gia thảo luận trong danh sách kênh được cấp phép.
- **Mode C (Autonomous Character):** Có thể chủ động mở lời hỏi han, chào đón thành viên quay lại dựa trên khung giờ và trạng thái cảm xúc.

---

## 🎮 Danh Sách Lệnh Discord

### Slash Commands (`/`)
| Lệnh | Mô tả |
|---|---|
| `/chat <lời nhắn>` | Trò chuyện trực tiếp cùng Neneka |
| `/neneka` | Xem hồ sơ nhân vật và trang phục hiện tại |
| `/costume [tên]` | Xem hoặc chuyển đổi trang phục (original, new_year, alpha) |
| `/bond [user]` | Kiểm tra cấp độ gắn kết và điểm hảo cảm |
| `/memory` | Xem danh sách ký ức dài hạn Neneka lưu về bạn |
| `/forget [id]` | Xóa một hoặc toàn bộ ký ức dài hạn |
| `/story [từ khóa]` | Tra cứu kho cốt truyện Canon và mẩu ký ức |
| `/speak <câu> [cảm xúc]` | Yêu cầu Neneka cất giọng tiếng Nhật (gửi file và phát trên VC) |
| `/join` / `/leave` | Mời Neneka tham gia hoặc rời khỏi Voice Channel |
| `/radio` | Phát một câu thoại ngẫu nhiên trong phòng thoại |
| `/autochat <on/off>` | Bật/tắt tự động trò chuyện trong kênh này (Yêu cầu Manage Channels) |
| `/autonomous <mode>` | Cấu hình chế độ A, B, hoặc C (Yêu cầu Administrator) |
| `/admin` | Xem trạng thái kết nối Database, Cache, mô hình LLM |

### Prefix Commands Kế Thừa (`!n` hoặc `n!`)
- `!n status` / `n! status`: Xem bảng trạng thái hảo cảm, cảm xúc.
- `!n gift <món quà>`: Tặng quà điểm tâm Landosol cho Neneka.
- `!n reset`: Làm mới ngữ cảnh hội thoại kênh hiện tại.
- `!n help`: Xem danh sách trợ giúp.

---

## ⚙️ Hướng Dẫn Cài Đặt & Khởi Chạy

### Cách 1: Chạy Cục Bộ (Local Machine)
1. Cài đặt Python 3.11+:
   ```powershell
   py -m pip install -r requirements.txt
   ```
2. Cấu hình file `.env`:
   ```env
   DISCORD_TOKEN=your_token_here
   GROQ_API_KEY=your_groq_key_here
   GROQ_MODEL=qwen/qwen3.8-27b
   AUTO_REPLY_CHANNELS=1546061652967948358
   ```
   *(Hệ thống sẽ tự động dùng SQLite và In-Memory Cache nếu PostgreSQL / Redis chưa chạy)*.
3. Khởi chạy:
   ```powershell
   py main.py
   ```

### Cách 2: Triển Khai Bằng Docker Compose (Khuyên dùng cho Production)
```bash
docker compose up -d --build
```

### Chạy Kiểm Thử Tự Động (Pytest)
```powershell
py -m pytest tests/ -v
```
*(15/15 tests kiểm thử toàn diện các module đều vượt qua thành công)*.
