# Dockerfile for Neneka Autonomous Discord AI
FROM python:3.11-slim

# Cài đặt các gói hệ thống cần thiết (FFmpeg cho Discord Voice, build dependencies)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libffi-dev \
    gcc \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Sao chép và cài đặt Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Sao chép toàn bộ mã nguồn
COPY . .

# Khởi chạy bot
CMD ["python", "main.py"]

