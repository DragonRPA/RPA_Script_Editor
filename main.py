"""
UBUS Contract RPA & Ollama Pipeline - Main Entry Point
"""

import sys
import os

# 작업 디렉토리 경로 등록
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from gui_app import main

if __name__ == "__main__":
    main()
