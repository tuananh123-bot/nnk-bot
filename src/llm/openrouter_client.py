# src/llm/openrouter_client.py
"""
Deprecated: OpenRouter client đã được thay thế bằng Venice AI (src.llm.venice_client).
Module này cung cấp alias tương thích ngược để không gây lỗi import cũ.
"""

from src.llm.venice_client import VeniceClient, get_venice_client

OpenRouterClient = VeniceClient
get_openrouter_client = get_venice_client
