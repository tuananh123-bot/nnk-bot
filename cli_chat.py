# cli_chat.py
import os
import sys
from dotenv import load_dotenv
from config_persona import AFFECTION_TIERS, BOND_STORIES
from state_manager import StateManager
from memory_system import MemorySystem
from cognitive_engine import CognitiveEngine

def main():
    load_dotenv()
    gemini_key = os.getenv("GEMINI_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    if not gemini_key and not groq_key:
        print("[LỖI] Cần ít nhất GEMINI_API_KEY hoặc GROQ_API_KEY trong file .env!")
        return

    state_mgr = StateManager()
    memory_sys = MemorySystem()
    engine = CognitiveEngine(
        gemini_api_key=gemini_key,
        groq_api_key=groq_key,
        state_mgr=state_mgr,
        memory_sys=memory_sys
    )

    show_cot = True

    print("=" * 60)
    print("      NENEKA COGNITIVE CHATBOT (Princess Connect! Re:Dive)      ")
    print("=" * 60)
    print("Lệnh hỗ trợ:")
    print("  /status      : Xem trạng thái hảo cảm, cảm xúc hiện tại")
    print("  /gift <quà>  : Tặng điểm tâm, bánh ngọt, trà Landosol cho Neneka")
    print("  /bond [1-5]  : Xem danh sách hoặc đọc các mẩu truyện Ký ức đã mở khóa")
    print("  /cot         : Bật / Tắt hiển thị luồng suy nghĩ nội tâm (Chain of Thought)")
    print("  /reset       : Đặt lại trạng thái hảo cảm và ký ức")
    print("  /exit        : Thoát chương trình")
    print("-" * 60)
    print(state_mgr.render_affection_bar())
    print("-" * 60)

    while True:
        try:
            user_input = input("\n[Bạn]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nTạm biệt!")
            break

        if not user_input:
            continue

        if user_input.lower() in ["/exit", "/quit"]:
            print("Neneka: Fufu... Tạm biệt cậu.")
            break
        elif user_input.lower() == "/status":
            print("\n" + state_mgr.render_affection_bar())
            continue
        elif user_input.lower().startswith("/gift"):
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                print("\n[Hệ thống] Hãy nhập: /gift <tên món quà> (VD: /gift bánh crepe)")
                continue
            gift_name = parts[1].strip()
            print(f"\n*Đang tặng '{gift_name}' cho Neneka...*")
            try:
                result = engine.process_gift(gift_name)
                if show_cot:
                    print("\n" + "·" * 50)
                    print("🧠 [SUY NGHĨ NỘI TÂM (Chain of Thought)]:")
                    print(f"  • Quan sát: {result.user_state_observation}")
                    print(f"  • Lý trí:   {result.logical_analysis}")
                    print(f"  • Che chở:  {result.sisterly_impulse}")
                    print(f"  • Cảm xúc:  {result.selected_emotion} (Hảo cảm: +{result.affection_delta})")
                    print("·" * 50)
                print(f"\n[Neneka nhận quà]: {result.action_gesture} {result.spoken_response}")
                print(f"\n{state_mgr.render_affection_bar()}")
                if result.newly_unlocked_bonds:
                    for bid in result.newly_unlocked_bonds:
                        b = BOND_STORIES[bid]
                        print("\n" + "=" * 50)
                        print(f"🎉 [CHÚC MỪNG! MỞ KHÓA {b['title'].upper()}]")
                        print(f"{b['story']}")
                        print("=" * 50)
            except Exception as e:
                print(f"\n[Lỗi xử lý tặng quà]: {e}")
            continue
        elif user_input.lower().startswith("/bond"):
            parts = user_input.split()
            unlocked = state_mgr.state.unlocked_bonds
            if len(parts) == 1:
                print("\n📖 [DANH SÁCH KÝ ỨC LIÊN KẾT - BOND STORIES]:")
                for bid, info in BOND_STORIES.items():
                    if bid in unlocked:
                        status = "✅ ĐÃ MỞ KHÓA"
                        hint = f"Gõ /bond {bid} để đọc"
                    else:
                        status = f"🔒 KHÓA (Cần {info['req_affection']} điểm)"
                        hint = f"Hiện tại: {state_mgr.state.affection}/{info['req_affection']}"
                    print(f"  [{status}] {info['title']} - {hint}")
            else:
                try:
                    bid = int(parts[1])
                    if bid not in BOND_STORIES:
                        print("\n[Hệ thống] Chỉ có từ Bond 1 đến Bond 5.")
                    elif bid not in unlocked:
                        req = BOND_STORIES[bid]["req_affection"]
                        print(f"\n[Hệ thống] 🔒 Mẩu truyện này chưa mở khóa! Cần {req} điểm hảo cảm (hiện tại: {state_mgr.state.affection}/1000).")
                    else:
                        b = BOND_STORIES[bid]
                        print("\n" + "=" * 50)
                        print(f"✨ {b['title']}")
                        print(f"{b['story']}")
                        print("=" * 50)
                except ValueError:
                    print("\n[Hệ thống] Hãy nhập số thứ tự Bond hợp lệ (VD: /bond 1)")
            continue
        elif user_input.lower() == "/cot":
            show_cot = not show_cot
            print(f"\n[Hệ thống] Hiển thị Chain of Thought: {'BẬT' if show_cot else 'TẮT'}")
            continue
        elif user_input.lower() == "/reset":
            if os.path.exists(state_mgr.filepath):
                os.remove(state_mgr.filepath)
            if os.path.exists(memory_sys.filepath):
                os.remove(memory_sys.filepath)
            state_mgr.state = state_mgr._load_state()
            memory_sys.long_term_facts = []
            memory_sys.short_term_history = []
            print("\n[Hệ thống] Đã reset trạng thái và ký ức về mặc định!")
            print(state_mgr.render_affection_bar())
            continue

        print("\n*Neneka đang suy nghĩ...*")
        try:
            result = engine.process_message(user_input)

            if show_cot:
                print("\n" + "·" * 50)
                print("🧠 [SUY NGHĨ NỘI TÂM (Chain of Thought)]:")
                print(f"  • Quan sát: {result.user_state_observation}")
                print(f"  • Lý trí:   {result.logical_analysis}")
                print(f"  • Che chở:  {result.sisterly_impulse}")
                print(f"  • Cảm xúc:  {result.selected_emotion} (Hảo cảm: {result.affection_delta:+d} | Bảo bọc: {result.protective_instinct_delta:+d})")
                if result.new_memory_fact:
                    print(f"  • Ghi nhớ mới: \"{result.new_memory_fact}\"")
                print("·" * 50)

            print(f"\n[Neneka]: {result.action_gesture} {result.spoken_response}")
            print(f"\n{state_mgr.render_affection_bar()}")

        except Exception as e:
            print(f"\n[Lỗi xử lý]: {e}")

if __name__ == "__main__":
    main()

