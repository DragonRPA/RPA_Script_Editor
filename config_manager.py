"""
UBUS Contract RPA & Ollama Pipeline - Configuration Manager
로컬 설정(config.json) 입출력 및 마지막 사용 상태 영구 보존 모듈
"""

import json
import os
from typing import Dict, Any

DEFAULT_CONFIG: Dict[str, Any] = {
    "erp_url": "http://175.119.156.105:3000",
    "user_id": "",
    "user_pw": "",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "qwen2.5:7b",
    "extract_keywords": "계약번호",
    "input_dir": "C:/UBUS_PDF/1_대기",
    "ocr_done_dir": "C:/UBUS_PDF/2_OCR완료",
    "rpa_done_dir": "C:/UBUS_PDF/3_RPA완료",
    "error_dir": "C:/UBUS_PDF/4_오류격리",
    "headless": False,
    "rename_template": "{계약번호}.pdf",
    "max_retries": 3,
    "timeout_sec": 30,
    "neon_database_url": ""
}

CONFIG_FILE_NAME = "config.json"


class ConfigManager:
    """애플리케이션 설정 및 상태를 JSON 파일로 관리하는 클래스"""

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.join(base_dir, CONFIG_FILE_NAME)
        self.config: Dict[str, Any] = {}
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """로컬 config.json 파일에서 설정을 로드하고, 없을 경우 기본값으로 초기화"""
        config = DEFAULT_CONFIG.copy()
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    config.update(loaded)
            except Exception as e:
                print(f"[ConfigManager] 설정 로드 오류: {e}, 기본값 사용")
        else:
            self.save_config(config)
        return config

    def save_config(self, new_config: Dict[str, Any] = None) -> bool:
        """설정을 로컬 config.json 파일에 저장"""
        if new_config:
            self.config.update(new_config)
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[ConfigManager] 설정 저장 오류: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """설정값 조회"""
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        """설정값 업데이트 및 즉시 저장"""
        self.config[key] = value
        self.save_config()

    def get_keyword_list(self) -> list:
        """콤마로 구분된 키워드 문자열을 리스트로 파싱하여 반환"""
        raw = self.get("extract_keywords", "계약번호")
        if isinstance(raw, list):
            return [k.strip() for k in raw if k.strip()]
        return [k.strip() for k in raw.split(",") if k.strip()]
