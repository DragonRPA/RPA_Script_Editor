"""
UBUS Contract RPA & Ollama Pipeline - Scenario Recorder & Model
시나리오 JSON 관리, 1회 실행/반복 루프 구분, 녹화 세션 제어
"""

import json
import os
import time
from typing import Dict, List, Any, Optional

DEFAULT_SCENARIO: Dict[str, Any] = {
    "scenario_name": "UBUS 계약서 자동 첨부",
    "setup_steps": [
        {
            "id": "setup_1",
            "title": "ERP 로그인 화면 접속",
            "action": "GOTO",
            "target": "",
            "value": "{{ERP_URL}}"
        },
        {
            "id": "setup_2",
            "title": "아이디 입력",
            "action": "FILL",
            "target": "input[placeholder*='아이디'], input[name='id'], [aria-label*='ID']",
            "value": "{{USER_ID}}"
        },
        {
            "id": "setup_3",
            "title": "비밀번호 입력",
            "action": "FILL",
            "target": "input[placeholder*='비밀번호'], input[type='password']",
            "value": "{{USER_PW}}"
        },
        {
            "id": "setup_4",
            "title": "로그인 버튼 클릭",
            "action": "CLICK",
            "target": "button:has-text('로그인')",
            "value": ""
        },
        {
            "id": "setup_5",
            "title": "메뉴 이동: 계약",
            "action": "CLICK",
            "target": "a:has-text('계약'), span:has-text('계약')",
            "value": ""
        },
        {
            "id": "setup_6",
            "title": "메뉴 이동: 계약조회",
            "action": "CLICK",
            "target": "a:has-text('계약조회'), span:has-text('계약조회')",
            "value": ""
        }
    ],
    "loop_steps": [
        {
            "id": "loop_1",
            "title": "계약조회 화면 이동",
            "action": "GOTO",
            "target": "",
            "value": "{{ERP_URL}}/contract/list"
        },
        {
            "id": "loop_2",
            "title": "계약번호 검색어 입력",
            "action": "FILL",
            "target": "label:has-text('계약번호') + input, input[name*='contract']",
            "value": "{{계약번호}}"
        },
        {
            "id": "loop_3",
            "title": "조회 버튼 클릭",
            "action": "CLICK",
            "target": "button:has-text('조회')",
            "value": ""
        },
        {
            "id": "loop_4",
            "title": "조회 결과 1행 더블클릭",
            "action": "DBLCLICK",
            "target": "table tbody tr:first-child",
            "value": ""
        },
        {
            "id": "loop_5",
            "title": "계약서 파일 첨부 주입",
            "action": "SET_FILES",
            "target": "input[type='file']",
            "value": "{{첨부파일_경로}}"
        },
        {
            "id": "loop_6",
            "title": "저장 버튼 클릭",
            "action": "CLICK",
            "target": "button:has-text('저장')",
            "value": ""
        },
        {
            "id": "loop_7",
            "title": "저장 완료 대기",
            "action": "WAIT_TIME",
            "target": "",
            "value": "1000"
        }
    ]
}


class ScenarioManager:
    """시나리오 파일(scenario.json) 관리 및 CRUD 클래스"""

    def __init__(self, filepath: str = "scenario.json"):
        self.filepath = os.path.abspath(filepath)
        self.data: Dict[str, Any] = self.load()

    def load(self) -> Dict[str, Any]:
        """시나리오 로드"""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[ScenarioManager] 시나리오 파일 로드 실패: {e}")
        return DEFAULT_SCENARIO.copy()

    def save(self, data: Optional[Dict[str, Any]] = None) -> bool:
        """시나리오 저장"""
        if data:
            self.data = data
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[ScenarioManager] 시나리오 저장 실패: {e}")
            return False

    def get_setup_steps(self) -> List[Dict[str, Any]]:
        return self.data.get("setup_steps", [])

    def get_loop_steps(self) -> List[Dict[str, Any]]:
        return self.data.get("loop_steps", [])

    def set_steps(self, setup_steps: List[Dict[str, Any]], loop_steps: List[Dict[str, Any]]):
        self.data["setup_steps"] = setup_steps
        self.data["loop_steps"] = loop_steps
        self.save()
