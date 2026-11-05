# Neneka Discord Bot (nnkbot)

Chatbot nhân vật **Utsushimi Neneka** (Princess Connect! Re:Dive) tích hợp Google Gemini AI và Discord.py.

## Tính năng
- **Nhập vai sinh động**: Hệ thống phản xạ, ngữ khí anime, cơ chế "tử huyệt" (dị ứng tuổi tác, chiều cao) và tsundere ngầm khi được khen ngợi.
- **Tư duy nhận thức (Chain-of-Thought)**: Xử lý hai chiều giữa Lý trí sắc sảo và Bản năng che chở của người chị lớn.
- **Trạng thái & Hảo cảm**: Hệ thống cấp độ quan hệ (5 bậc) và đo lường cảm xúc thời gian thực.
- **Ký ức dài hạn**: Ghi nhớ thói quen, thông tin người dùng qua các phiên trò chuyện.
- **Nhận thức thời gian thực**: Tự động nhận diện buổi sáng, trưa, tối, đêm khuya để tương tác phù hợp.
- **Hỗ trợ kênh tự động**: Tự động phản hồi không cần tag `@mention` trong kênh được cấu hình.

## Cài đặt & Chạy trên máy cá nhân

1. Cài đặt các thư viện:
```bash
pip install -r requirements.txt
```

2. Tạo file `.env` từ `.env.example` và điền token:
```env
DISCORD_TOKEN=your_token_here
GEMINI_API_KEY=your_gemini_key_here
AUTO_REPLY_CHANNELS=1546061652967948358
```

3. Khởi chạy:
- Chạy trên Discord: `python main.py` (hoặc click `run_discord.bat`)
- Chạy thử nghiệm trên Terminal: `python cli_chat.py` (hoặc click `run_cli.bat`)

## Lệnh trên Discord
- `!n status` : Xem thanh hảo cảm và cảm xúc hiện tại.
- `!n cot` : Bật/Tắt hiển thị suy nghĩ nội tâm (Chain-of-Thought).
- `!n reset` : Reset hảo cảm và ký ức về mặc định.
- `!n addchannel` : Thêm kênh vào danh sách tự động trả lời (không cần @mention).
- `!n removechannel` : Xóa kênh khỏi danh sách tự động trả lời.
- `!n listchannels` : Xem danh sách kênh tự động trả lời.
- `!n help` : Xem trợ giúp.
