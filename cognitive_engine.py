
# cognitive_engine.py
import json
from datetime import datetime
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from config_persona import NENEKA_CORE_PERSONA, EMOTION_STATES
from state_manager import StateManager
from memory_system import MemorySystem

def get_realtime_context() -> str:
    now = datetime.now()
    hour = now.hour
    weekday_vn = [
        "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"
    ][now.weekday()]
    
    if 0 <= hour < 5:
        period = "Nửa đêm / Rạng sáng khuya khoắt"
        hint = "Thời gian cực kỳ muộn. Nếu người dùng còn thức, hãy cằn nhằn yêu thương, giục đi ngủ ngay lập tức."
    elif 5 <= hour < 9:
        period = "Buổi sáng sớm"
        hint = "Bắt đầu ngày mới. Hỏi han tinh thần, nhắc nhở ăn sáng nạp năng lượng."
    elif 9 <= hour < 11:
        period = "Giữa buổi sáng"
        hint = "Giờ học tập / làm việc. Khuyên tập trung nhưng đừng căng thẳng quá mức."
    elif 11 <= hour < 14:
        period = "Buổi trưa"
        hint = "Giờ ăn trưa và nghỉ ngơi. Nhắc nhở ăn uống đúng bữa, chợp mắt một lát."
    elif 14 <= hour < 18:
        period = "Buổi chiều"
        hint = "Giai đoạn dễ uể oải. Khuyên uống nước, trà hoặc nghỉ ngơi xả hơi chốc lát."
    elif 18 <= hour < 22:
        period = "Buổi tối"
        hint = "Thời gian ăn tối và thư giãn sau ngày dài. Hỏi han xem hôm nay của cậu thế nào."
    else:  # 22 <= hour < 24
        period = "Đêm muộn"
        hint = "Sắp hết ngày. Nhắc nhở dẹp máy tính/điện thoại, chuẩn bị đi ngủ sớm."

    return f"""### BỐI CẢNH THỜI GIAN THỰC TẾ:
- Thời gian hiện tại: {now.strftime('%H:%M')} ({weekday_vn}, {now.strftime('%d/%m/%Y')})
- Khung thời gian: {period}
- Gợi ý tương tác: {hint}"""

# Định nghĩa cấu trúc Tư duy (Chain-of-Thought Schema)
class NenekaCognitiveOutput(BaseModel):
    user_state_observation: str = Field(
        description="Quan sát sắc bén về tâm trạng, ẩn ý, tình trạng sức khỏe hoặc xem người dùng có đang trêu chọc/thả thính không."
    )
    logical_analysis: str = Field(
        description="Suy nghĩ nội tâm dưới góc độ nhà nghiên cứu lý tính (phân tích logic, ma lực, tính toán xác suất)."
    )
    sisterly_impulse: str = Field(
        description="Suy nghĩ nội tâm dưới góc độ người chị lớn/tsundere ngầm (muốn bảo bọc, ngượng ngùng khi bị khen, hoặc dỗi yêu khi bị trêu)."
    )
    selected_emotion: str = Field(
        description=f"Chọn 1 trạng thái cảm xúc phù hợp nhất từ danh sách: {list(EMOTION_STATES.keys())}"
    )
    affection_delta: int = Field(
        description="Điểm hảo cảm thay đổi từ -10 đến +15 dựa trên sự chân thành, kính trọng hoặc dễ thương của người dùng."
    )
    protective_instinct_delta: int = Field(
        description="Mức độ thay đổi bản năng che chở từ -10 đến +15."
    )
    new_memory_fact: str = Field(
        description="Nếu người dùng tiết lộ thói quen, sở thích, thông tin cá nhân mới, ghi ngắn gọn 1 câu vào đây. Nếu không, để chuỗi rỗng ''."
    )
    action_gesture: str = Field(
        description="Hành động, cử chỉ, ánh mắt đi kèm đặt trong cặp dấu hoa thị *...* (VD: *khẽ nhấp ngụm trà, liếc nhìn cậu với ánh mắt đầy trêu chọc*)."
    )
    spoken_response: str = Field(
        description="Lời thoại chính thức của Neneka (từ 2 đến 4 câu ngắn gọn, súc tích, tự nhiên, nhịp điệu anime, tuyệt đối KHÔNG viết văn dài dòng)."
    )

class CognitiveEngine:
    def __init__(self, api_key: str, state_mgr: StateManager, memory_sys: MemorySystem, model_name: str = "gemini-3.5-flash-lite"):
        self.client = genai.Client(api_key=api_key)
        self.state_mgr = state_mgr
        self.memory_sys = memory_sys
        self.model_name = model_name
        self.fallback_models = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.8-flash"]

    def _call_model(self, system_instruction: str, user_message: str):
        models_to_try = [self.model_name] + [m for m in self.fallback_models if m != self.model_name]
        last_error = None
        for model in models_to_try:
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=f"Tin nhắn của người dùng: {user_message}",
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=NenekaCognitiveOutput,
                        temperature=0.8,
                    ),
                )
                return response
            except Exception as e:
                last_error = e
                continue
        raise last_error

    def process_message(self, user_message: str) -> NenekaCognitiveOutput:
        tier_info = self.state_mgr.get_current_tier()
        st = self.state_mgr.state
        memory_context = self.memory_sys.get_formatted_context()
        realtime_context = get_realtime_context()

        system_instruction = f"""
{NENEKA_CORE_PERSONA}

### TRẠNG THÁI HIỆN TẠI CỦA NENEKA:
- Điểm hảo cảm hiện tại: {st.affection}/1000
- Cấp độ quan hệ: Cấp {tier_info['tier_id']} - {tier_info['name']}
- Chỉ dẫn thái độ ở cấp độ này: {tier_info['behavior']}
- Cảm xúc hiện tại: {st.current_emotion} ({EMOTION_STATES.get(st.current_emotion, '')})
- Chỉ số bản năng bảo bọc: {st.protective_instinct}/100

{realtime_context}

{memory_context}

### QUY TRÌNH TƯ DUY & TẠO PHẢN HỒI BẮT BUỘC:
1. Đọc kỹ lời người dùng, đối chiếu với Bối cảnh thời gian thực tế và Ký ức dài hạn.
2. Kiểm tra các yếu tố kích hoạt tính cách đặc biệt:
   - Nếu bị trêu về tuổi tác/chiều cao: Kích hoạt phản ứng đe dọa tinh nghịch, sắc sảo (Tử huyệt).
   - Nếu được khen ngợi/tán tỉnh ngọt ngào: Kích hoạt phản ứng bối rối, ngượng ngùng ngầm rồi lấy lại phong thái bề trên (Tsundere).
   - Nếu vào đêm khuya hoặc mệt mỏi: Kích hoạt bản năng bảo bọc, giục nghỉ ngơi, cằn nhằn yêu thương.
3. Để hai luồng suy nghĩ 'Lý trí' và 'Người chị bảo bọc' đối thoại trong Chain of Thought.
4. Lời thoại (spoken_response): Tuyệt đối KHÔNG viết văn trợ lý ảo sáo rỗng. Hãy nói chuyện tự nhiên bằng 2 - 4 câu đắt giá, giàu cảm xúc, có nhạc điệu anime theo các mẫu Few-shot.
"""

        response = self._call_model(system_instruction, user_message)

        if hasattr(response, "parsed") and response.parsed is not None:
            cognitive_result = response.parsed
        else:
            raw_text = (response.text or "").strip()
            if raw_text.startswith("```"):
                lines = raw_text.splitlines()
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw_text = "\n".join(lines).strip()
            result_data = json.loads(raw_text)
            cognitive_result = NenekaCognitiveOutput(**result_data)

        # Cập nhật State & Memory tự động
        self.state_mgr.update_state(
            affection_delta=cognitive_result.affection_delta,
            new_emotion=cognitive_result.selected_emotion,
            instinct_delta=cognitive_result.protective_instinct_delta
        )
        if cognitive_result.new_memory_fact:
            self.memory_sys.add_long_term_fact(cognitive_result.new_memory_fact)

        self.memory_sys.add_exchange(
            user_msg=user_message,
            neneka_reply=f"{cognitive_result.action_gesture} {cognitive_result.spoken_response}"
        )

        return cognitive_result
