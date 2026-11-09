# src/entertainment/mirror_game.py
import random
import time
from typing import Dict, Any, List, Optional
import discord

# Cooldown chống spam game: {user_id: last_played_timestamp}
_game_cooldowns: Dict[str, float] = {}
COOLDOWN_SECONDS = 30.0

MIRROR_SCENARIOS = [
    {
        "title": "🪞 Tam Diện Ảo Ảnh • Vườn Hồng Trà Landosol",
        "story": (
            "Neneka khẽ phẩy quyền trượng Metamorphose. Trong nháy mắt, 3 ảo ảnh giống hệt nhau "
            "cùng bước ra từ sương mù tím, mỉm cười tao nhã trước mặt cậu.\n\n"
            "Chỉ có **MỘT** bản thể chân chính đang cầm tách hồng trà nguyên chất thật sự. "
            "Cậu hãy dùng trực giác và sự quan sát nhạy bén để chọn ra Neneka thật nhé!"
        ),
        "options": [
            {
                "label": "Gương 1: Ảo ảnh Ánh Trăng (Bên Trái)",
                "hint": "Nụ cười khẽ khàng, tay áo khẽ lay động theo làn gió nhẹ.",
                "is_correct": False,
                "reveal_correct": "✨ *Chính xác!* Bản thể chân chính khẽ mỉm cười nhấp ngụm trà: 'Fufu... Tinh tường lắm. Ta cố ý làm lay động tay áo để thử cậu, vậy mà vẫn không qua mắt được cậu.'",
                "reveal_wrong": "💨 *Bụp!* Ảo ảnh tan biến thành khói bướm tím! Neneka thật xuất hiện từ phía sau: 'Fufu... Cậu nhìn nhầm rồi, đó chỉ là khúc xạ ánh sáng thôi nhé ~'"
            },
            {
                "label": "Gương 2: Ảo ảnh Tử Đằng (Ở Giữa)",
                "hint": "Ánh mắt điềm tĩnh, quyền trượng tỏa ra luồng ma lực màu thạch anh tím.",
                "is_correct": True,
                "reveal_correct": "✨ *Chính xác!* Bản thể chân chính khẽ mỉm cười nâng quyền trượng: 'Fufu... Tuyệt vời. Cậu đã nhận ra ma lực thực tại của ta giữa muôn ngàn ảo ảnh.'",
                "reveal_wrong": "💨 *Bụp!* Ảo ảnh biến thành một cánh bướm tím bay vút lên! Neneka thật khẽ cười: 'Ảo ảnh ở giữa chỉ là mồi nhử thôi cậu bé ngốc à ~'"
            },
            {
                "label": "Gương 3: Ảo ảnh Hoàng Kim (Bên Phải)",
                "hint": "Cử chỉ tao nhã, trên tay đang cầm một đĩa bánh macaron ngọt ngào.",
                "is_correct": False,
                "reveal_correct": "✨ *Chính xác!* Neneka thật cười khúc khích chia nửa chiếc bánh macaron cho cậu: 'Fufu... Đúng là chỉ có cậu mới nhận ra bản thể hảo ngọt này của ta.'",
                "reveal_wrong": "💨 *Bụp!* Đĩa bánh macaron hóa thành cánh hoa rơi lả tả! Neneka thật nhấp ngụm trà: 'Đĩa bánh hấp dẫn quá làm cậu mất tập trung rồi sao? Fufu ~'"
            }
        ]
    },
    {
        "title": "🪞 Tam Diện Ảo Ảnh • Mật Thất Thất Vương",
        "story": (
            "Dưới ánh đèn lồng tím của mật thất, Neneka tạo ra 3 chiếc gương không gian.\n"
            "Mỗi chiếc gương phản chiếu một lời thì thầm khác nhau. Hãy tìm chiếc gương dẫn lối tới nơi bản thể thật của Neneka đang ngự trị!"
        ),
        "options": [
            {
                "label": "Gương A: Gương Thạch Anh Tím",
                "hint": "Thì thầm: 'Thực tại là bức tranh do kẻ mạnh vẽ nên...'",
                "is_correct": True,
                "reveal_correct": "✨ *Chính xác!* Tấm gương mở ra lối vào cung điện: 'Fufu... Đúng vậy. Câu nói ấy chính là chân lý của ta. Cậu hiểu ta rất rõ đấy.'",
                "reveal_wrong": "💨 *Bụp!* Tấm gương vỡ òa thành hàng ngàn hạt sao! Neneka bước ra từ bóng tối: 'Sai rồi nhé, đó chỉ là vọng âm ta lưu lại thôi.'"
            },
            {
                "label": "Gương B: Gương Thủy Tinh Lam",
                "hint": "Thì thầm: 'Mọi ảo ảnh đều tan biến trước bình minh...'",
                "is_correct": False,
                "reveal_correct": "✨ *Chính xác!* Neneka thật bước ra vỗ tay tán thưởng: 'Fufu... Trực giác của cậu sắc bén hơn ta tưởng nhiều đấy.'",
                "reveal_wrong": "💨 *Bụp!* Mặt gương phẳng lặng tan thành nước! Neneka khẽ trêu: 'Cậu bị câu thì thầm đánh lừa rồi nhé ~'"
            },
            {
                "label": "Gương C: Gương Hoàng Ngọc Hổ Phách",
                "hint": "Thì thầm: 'Trà đã nguội rồi, cậu còn đợi gì nữa?'",
                "is_correct": False,
                "reveal_correct": "✨ *Chính xác!* Neneka mỉm cười rót đầy tách trà: 'Fufu... Đúng lúc lắm, ta vừa pha xong ấm trà mới.'",
                "reveal_wrong": "💨 *Bụp!* Tấm gương hóa thành làn gió thổi tắt ngọn nến! Neneka cười khúc khích: 'Ta chưa hề giục cậu uống trà đâu nhé, đồ ngốc ~'"
            }
        ]
    },
    {
        "title": "🎓 Trí Tuệ Landosol • Bí Mật Của Thất Vương",
        "story": (
            "Neneka khẽ nghiêng đầu, đôi mắt tím ánh lên nét tinh nghịch:\n"
            "*'Nếu đã tự xưng là người đồng hành của ta, liệu cậu có trả lời đúng câu hỏi thử thách này không nào?'*"
        ),
        "options": [
            {
                "label": "A. Metamorphose Regnant (Biến Hóa Thực Tại)",
                "hint": "Câu hỏi: Ma thuật tối thượng danh chấn Landosol của Neneka có tên là gì?",
                "is_correct": True,
                "reveal_correct": "✨ *Chính xác tuyệt đối!* 'Fufu... Tuyệt lắm! Metamorphose Regnant chính là tuyệt kỹ làm nên danh hiệu Thất Vương của ta.'",
                "reveal_wrong": "💨 *Sai rồi nhé!* 'Đó không phải là tên ma pháp của ta đâu. Cậu cần phải học thêm về Thất Vương nhiều đấy ~'"
            },
            {
                "label": "B. Absolute Zero (Băng Phong Tuyệt Đối)",
                "hint": "Lựa chọn năng lực băng phong.",
                "is_correct": False,
                "reveal_correct": "",
                "reveal_wrong": "💨 *Sai rồi nhé!* 'Băng phong là ma thuật tầm thường của người khác, ma pháp của ta là biến đổi bản chất thực tại cơ! Fufu ~'"
            },
            {
                "label": "C. Shadow Illusion (Ảo Ảnh Bóng Đêm)",
                "hint": "Lựa chọn năng lực bóng tối.",
                "is_correct": False,
                "reveal_correct": "",
                "reveal_wrong": "💨 *Sai rồi nhé!* 'Ta không dùng bóng tối thô sơ như vậy. Ma pháp của ta là Metamorphose Regnant hoa lệ kia! Fufu ~'"
            }
        ]
    }
]


class MirrorGameView(discord.ui.View):
    """View chứa các nút bấm tương tác cho Mini-game Gương Ảo Ảnh"""
    def __init__(self, author_id: str, scenario: Dict[str, Any], bond_engine):
        super().__init__(timeout=60.0)
        self.author_id = str(author_id)
        self.scenario = scenario
        self.bond_engine = bond_engine
        self.has_interacted = False

        # Xáo trộn vị trí đáp án ngẫu nhiên để tăng tính bất ngờ
        options = list(scenario["options"])
        random.shuffle(options)

        button_styles = [
            discord.ButtonStyle.primary,
            discord.ButtonStyle.secondary,
            discord.ButtonStyle.success
        ]

        for idx, opt in enumerate(options):
            btn = discord.ui.Button(
                label=opt["label"][:80],
                style=button_styles[idx % len(button_styles)],
                custom_id=f"mirror_{idx}"
            )
            # Gán callback cho từng nút
            btn.callback = self.make_callback(opt)
            self.add_item(btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.author_id:
            await interaction.response.send_message(
                "❌ Trò chơi ảo ảnh này đang dành riêng cho người đã gọi lệnh! Hãy dùng `/mirror` hoặc `!n mirror` để tự mở màn thử thách của riêng bạn nhé.",
                ephemeral=True
            )
            return False
        return True

    def make_callback(self, option: Dict[str, Any]):
        async def callback(interaction: discord.Interaction):
            if self.has_interacted:
                return
            self.has_interacted = True

            # Vô hiệu hóa toàn bộ buttons
            for item in self.children:
                item.disabled = True

            is_win = option.get("is_correct", False)
            if is_win:
                points = 20
                res_desc = option.get("reveal_correct") or "✨ Cậu đã đoán đúng bản thể thật của Neneka!"
                color = 0xf1c40f  # Vàng chiến thắng
                title = "🎉 BẠN ĐÃ NHÌN THẤU ẢO ẢNH NENEKA!"
            else:
                points = 5
                res_desc = option.get("reveal_wrong") or "💨 Tiếc quá, cậu đã chạm phải ảo ảnh biến hóa rồi ~"
                color = 0x9b59b6  # Tím trêu chọc
                title = "🎭 CẬU ĐÃ BỊ NENEKA ĐÁNH LỪA RỒI ~"

            # Cộng điểm gắn kết
            new_lvl, new_pts, level_up = await self.bond_engine.add_bond_points(
                self.author_id,
                points=points,
                event_type="MINIGAME",
                description=f"Chơi Gương Ảo Ảnh: {'Thắng' if is_win else 'Thua'}"
            )

            res_embed = discord.Embed(
                title=title,
                description=f"{res_desc}\n\n💜 **Phần thưởng gắn kết:** `+{points} điểm Bond` (Tổng: **{new_pts}** pts - Cấp {new_lvl})",
                color=color
            )
            if level_up:
                res_embed.add_field(name="🎉 THĂNG CẤP GẮN KẾT!", value=f"Tuyệt vời! Cậu vừa thăng tiến lên **Cấp {level_up}** với Neneka!", inline=False)

            res_embed.set_footer(text="Seven Crowns Metamorphose Simulation • Princess Connect! Re:Dive")
            await interaction.response.edit_message(embed=res_embed, view=self)

        return callback

    async def on_timeout(self):
        # Khi hết giờ, tự động tắt nút
        for item in self.children:
            item.disabled = True


def start_mirror_game(user_id: str, bond_engine) -> Tuple[Optional[discord.Embed], Optional[MirrorGameView], Optional[str]]:
    """
    Bắt đầu một ván chơi Gương Ảo Ảnh:
    - Kiểm tra cooldown (30 giây)
    - Trả về (Embed câu đố, View chứa nút bấm, thông báo lỗi nếu có)
    """
    now = time.time()
    user_str = str(user_id)
    if user_str in _game_cooldowns:
        elapsed = now - _game_cooldowns[user_str]
        if elapsed < COOLDOWN_SECONDS:
            remaining = int(COOLDOWN_SECONDS - elapsed)
            return None, None, f"Fufu... Quyền trượng Metamorphose đang hồi phục ma lực ảo ảnh. Cậu vui lòng đợi thêm `{remaining}s` nữa nhé."

    _game_cooldowns[user_str] = now
    scenario = random.choice(MIRROR_SCENARIOS)

    embed = discord.Embed(
        title=scenario["title"],
        description=scenario["story"],
        color=0x9b59b6
    )

    for idx, opt in enumerate(scenario["options"], 1):
        embed.add_field(name=f"🔹 Lựa chọn {idx}", value=f"*{opt['hint']}*", inline=False)

    embed.set_footer(text="Bấm một trong các nút bên dưới để chọn • Thời gian chọn: 60 giây")
    view = MirrorGameView(user_id, scenario, bond_engine)
    return embed, view, None

