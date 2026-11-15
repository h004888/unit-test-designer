"""Cấu hình pytest cho unit-test-designer v2.

Thêm thư mục cha của package `utd` vào sys.path để test import được
mà không cần cài đặt package.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
