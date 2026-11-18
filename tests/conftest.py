# tests/conftest.py
import sys
from unittest.mock import MagicMock

# Đảm bảo greenlet không gây crash trên Windows Python 3.14 khi chạy test
try:
    import greenlet
except Exception:
    mock_greenlet = MagicMock()
    mock_greenlet.getcurrent = MagicMock()
    mock_greenlet.GreenletExit = Exception
    mock_greenlet._C_API = MagicMock()
    sys.modules["greenlet"] = mock_greenlet
    sys.modules["greenlet._greenlet"] = mock_greenlet
