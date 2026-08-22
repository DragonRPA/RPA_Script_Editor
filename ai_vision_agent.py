"""
Universal RPA - Evidence-Based Hybrid Vision AI RPA Code & Selector Generator
Google Gemini (클라우드 초고속) + Local Ollama (100% 무료 / 로컬 오프라인) 듀얼 엔진
- 최상위 메인 탭(First-Class Tab)으로 승격 탑재 (새 모달 팝업 불필요)
- 열려있는 윈도우 창(HWND) 선택 및 실시간 DOM/UI 컨트롤 수집
- 유형별 조작 객체(입력창, 버튼, 그리드 등) 탭뷰 인스펙터
- 3~4줄 컴팩트 자연어 요구사항 입력
- 마지막 사용 설정(URL, AI 엔진, 모델) 영구 자동 기억
"""

import os
import sys
import json
import base64
import threading
import time
import ctypes
from typing import Dict, Any, Optional, Tuple, Callable, List

import requests
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ImageGrab

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False

from dom_harvester import DOMHarvester


class WindowEnumerator:
    """Windows 활성 윈도우 핸들(HWND) 및 타이틀 안전 열거자"""

    @classmethod
    def get_open_windows(cls) -> List[Tuple[int, str]]:
        windows = []
        user32 = ctypes.windll.user32
        GW_CHILD = 5
        GW_HWNDNEXT = 2

        hwnd = user32.GetDesktopWindow()
        hwnd = user32.GetWindow(hwnd, GW_CHILD)

        while hwnd:
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value.strip()
                    if title and title not in ['Program Manager', 'Default IME', 'MSCTFIME UI', 'Settings']:
                        # 브라우저 및 주요 프로그램 우선 식별
                        icon_tag = "🪟"
                        if any(kw in title.lower() for kw in ["chrome", "edge", "whale", "firefox", "brave"]):
                            icon_tag = "🌐"
                        elif any(kw in title.lower() for kw in ["excel", "hwp", "word", "erp", "더존", "sap"]):
                            icon_tag = "📊"
                        windows.append((hwnd, f"{icon_tag} {title}"))
            hwnd = user32.GetWindow(hwnd, GW_HWNDNEXT)

        return windows


class GeminiVisionAgent:
    """Google Gemini 멀티모달 비전 API 통신 매니저 (클라우드)"""

    SYSTEM_INSTRUCTION = """당신은 세계 최고 권위의 엔터프라이즈 파이썬 RPA 및 웹/데스크톱 자동화 아키텍트입니다.
사용자가 제공한 [화면 스크린샷 이미지], [대상 웹 URL/창], [실시간 수집된 UI 객체 카탈로그], [자연어 요구사항]을 정밀 분석하여, 실무 현장에서 100% 오류 없이 즉시 실행 가능한 완성형 파이썬 Playwright / Windows UIA 자동화 코드를 작성하십시오.

[필수 엔지니어링 표준 수칙]
1. 🔍 증거 기반(Evidence-Based) 셀렉터 1:1 매핑:
   - 함께 제공된 [실시간 수집된 UI 객체 카탈로그] 속의 실제 id, name, placeholder, class, label 힌트를 스크린샷 이미지와 1:1로 정확히 대조하십시오.
   - 추측이나 환각(Hallucination)에 의한 가상 속성을 쓰지 말고, 카탈로그에 실제로 존재하는 고유 속성을 기반으로 셀렉터를 작성하십시오.

2. 🖥️ 브라우저 기동 및 전체화면 (Playwright):
   - 브라우저 실행 시 반드시 최대화 및 가상 뷰포트 해제 적용:
     ```python
     browser = playwright.chromium.launch(headless=False, args=["--start-maximized"])
     context = browser.new_context(no_viewport=True)
     page = context.new_page()
     ```
   - 대상 URL이 주어지면 `page.goto("{target_url}")` 및 `page.wait_for_load_state("domcontentloaded")`를 선행하십시오.

3. 🎯 견고한 다중 Fallback 셀렉터 (Locators):
   - 클래스명이 동적으로 변하거나 난독화되어 있어도 절대 깨지지 않도록 다중 후보군(Placeholder, Label 인접 인풋, Name, Role, ARIA, 텍스트)을 결합한 복합 셀렉터를 사용하십시오.
   - 모든 요소 조작 전 `locator.wait_for(state="visible", timeout=5000)` 가시성 대기를 기본 적용하십시오.

4. 📊 실시간 콘솔 로깅 및 예외 처리:
   - 각 작업 단계마다 `print(">>> [단계 진행] ...")` 로그를 남기고, 적절한 `page.wait_for_timeout(...)`을 배치하여 안정성을 확보하십시오.

5. 📦 출력 포맷:
   - 다른 설명 없이 오직 완성된 파이썬 코드 블록(```python ... ```)을 최우선으로 출력하고, 코드 블록 하단에 사용된 핵심 셀렉터 분석 요약을 간결하게 첨부하십시오.
"""

    @classmethod
    def call_gemini_vision(cls, api_key: str, image_path: str, user_prompt: str,
                           target_url: str = "", model: str = "gemini-2.5-flash", page_html: str = "") -> Tuple[str, str]:
        if not api_key:
            raise ValueError("Google Gemini API Key가 설정되지 않았습니다.")

        if not os.path.exists(image_path):
            raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        mime_type = "image/png"
        if image_path.lower().endswith(".jpg") or image_path.lower().endswith(".jpeg"):
            mime_type = "image/jpeg"
        elif image_path.lower().endswith(".webp"):
            mime_type = "image/webp"

        prompt_text = ""
        if target_url:
            prompt_text += f"### [대상 웹페이지 URL / 창]\n{target_url}\n\n"
        if page_html:
            prompt_text += f"### [실시간 수집된 실제 UI 조작 객체 카탈로그]\n{page_html[:4500]}\n\n"
        prompt_text += f"### [자연어 자동화 요구사항]\n{user_prompt}\n\n"
        prompt_text += "위 화면 스크린샷과 UI 객체 카탈로그, URL, 요구사항을 바탕으로 최적의 셀렉터와 파이썬 Playwright RPA 코드를 작성해 주십시오."

        parts = [
            {
                "inline_data": {
                    "mime_type": mime_type,
                    "data": img_b64
                }
            },
            {
                "text": prompt_text
            }
        ]

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "system_instruction": {
                "parts": [{"text": cls.SYSTEM_INSTRUCTION}]
            },
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 4096
            }
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=40)
        if resp.status_code != 200:
            err_msg = resp.text
            try:
                err_json = resp.json()
                err_msg = err_json.get("error", {}).get("message", resp.text)
            except Exception:
                pass
            raise RuntimeError(f"Gemini API 오류 ({resp.status_code}): {err_msg}")

        data = resp.json()
        try:
            full_text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raise RuntimeError(f"Gemini 응답 파싱 실패: {data}")

        code = ""
        if "```python" in full_text:
            code = full_text.split("```python")[1].split("```")[0].strip()
        elif "```" in full_text:
            code = full_text.split("```")[1].split("```")[0].strip()
        else:
            code = full_text.strip()

        return code, full_text


class OllamaVisionAgent:
    """로컬 Ollama 멀티모달 비전 API 통신 매니저 (100% 무료 / 오프라인)"""

    SYSTEM_INSTRUCTION = """당신은 세계 최고 수준의 파이썬 RPA 및 웹/데스크톱 자동화 엔지니어링 전문가입니다.
제공된 [화면 스크린샷 이미지], [대상 URL/창], [실시간 UI 조작 객체 카탈로그], [자연어 요구사항]을 분석하여, 가장 견고하고 정확한 Playwright (웹) 또는 Windows UIA 자동화 코드를 작성하십시오.

[작성 규칙]
1. 제공된 [실시간 UI 조작 객체 카탈로그]의 id, name, placeholder, class 속성을 스크린샷과 대조하여 100% 정확한 실제 셀렉터를 추출하십시오.
2. Playwright 브라우저 기동 시 `browser = playwright.chromium.launch(headless=False, args=["--start-maximized"])`, `context = browser.new_context(no_viewport=True)`를 적용하십시오.
3. 대상 URL이 있으면 `page.goto("{target_url}")` 코드를 최상단에 작성하십시오.
4. 반드시 실행 가능한 완성된 파이썬 코드를 ```python ... ``` 블록으로 감싸서 출력하십시오."""

    @classmethod
    def list_installed_models(cls, ollama_url: str = "http://localhost:11434") -> List[str]:
        try:
            r = requests.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=3)
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                vision_keywords = ["vl", "vision", "llava", "minicpm", "moondream", "gemma"]
                def sort_key(m):
                    for kw in vision_keywords:
                        if kw in m.lower():
                            return 0
                    return 1
                return sorted(models, key=sort_key)
        except Exception:
            pass
        return ["qwen3-vl:4b", "llama3.2-vision", "llava", "qwen2.5:7b"]

    @classmethod
    def call_ollama_vision(cls, ollama_url: str, model: str, image_path: str,
                           user_prompt: str, target_url: str = "", page_html: str = "") -> Tuple[str, str]:
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        prompt_body = f"{cls.SYSTEM_INSTRUCTION}\n\n"
        if target_url:
            prompt_body += f"[대상 웹페이지 URL / 창]\n{target_url}\n\n"
        if page_html:
            prompt_body += f"[실시간 수집된 실제 UI 조작 객체 카탈로그]\n{page_html[:4500]}\n\n"
        prompt_body += f"[사용자 자연어 요구사항]\n{user_prompt}\n\n"
        prompt_body += "위 화면 스크린샷과 UI 객체 카탈로그에서 타겟 요소를 찾아 최적의 Playwright 셀렉터와 파이썬 실행 코드를 작성해 주십시오."

        url = f"{ollama_url.rstrip('/')}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt_body,
            "images": [img_b64],
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_predict": 4096
            }
        }

        resp = requests.post(url, json=payload, timeout=90)
        if resp.status_code != 200:
            raise RuntimeError(f"Ollama API 오류 ({resp.status_code}): {resp.text}")

        data = resp.json()
        full_text = data.get("response", "")

        code = ""
        if "```python" in full_text:
            code = full_text.split("```python")[1].split("```")[0].strip()
        elif "```" in full_text:
            code = full_text.split("```")[1].split("```")[0].strip()
        else:
            code = full_text.strip()

        return code, full_text


class AIVisionFrame(ctk.CTkFrame):
    """
    메인 스튜디오 탭에 직접 내장되는 AI 비전 & DOM 분석기 프레임
    - 모달 팝업 없이 100% 통합 탭 뷰로 구동
    - 열려있는 윈도우 창 선택 및 실시간 DOM/UI 카탈로그 수집
    - 유형별 탭뷰 인스펙터
    - 코드 생성 ➔ 스크립트 에디터 / 봇 에디터 탭으로 원클릭 전송
    """

    _CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recorder_config.json")

    def __init__(self, parent, on_insert_code: Optional[Callable[[str], None]] = None,
                 on_add_to_bot: Optional[Callable[[Dict[str, Any]], None]] = None,
                 on_switch_tab: Optional[Callable[[str], None]] = None):
        super().__init__(parent, fg_color="transparent")

        self.parent_app = parent
        self.on_insert_code = on_insert_code
        self.on_add_to_bot = on_add_to_bot
        self.on_switch_tab = on_switch_tab

        self.current_image_path: Optional[str] = None
        self.preview_image_ref: Optional[ImageTk.PhotoImage] = None
        self.current_catalog: Dict[str, List[Dict[str, Any]]] = {}
        self.open_windows_list: List[Tuple[int, str]] = []

        self._build_ui()
        self._load_saved_configs()
        self._refresh_window_list()

    def _build_ui(self):
        # 1. 상단 AI 엔진 선택 및 설정 바
        top_ctrl = ctk.CTkFrame(self, corner_radius=6)
        top_ctrl.pack(fill="x", padx=6, pady=(4, 6))

        ctk.CTkLabel(top_ctrl, text="AI 엔진:", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(10, 4), pady=8)
        self.seg_engine = ctk.CTkSegmentedButton(
            top_ctrl, values=["☁️ Google Gemini (초고속)", "🦙 Local Ollama (100% 무료)"],
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._on_engine_changed
        )
        self.seg_engine.pack(side="left", padx=(0, 12), pady=6)

        self.engine_conf_frame = ctk.CTkFrame(top_ctrl, fg_color="transparent")
        self.engine_conf_frame.pack(side="left", fill="x", expand=True, padx=4)

        # [A] Gemini 설정 위젯들
        self.f_gemini = ctk.CTkFrame(self.engine_conf_frame, fg_color="transparent")
        ctk.CTkLabel(self.f_gemini, text="Key:", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(0, 4))
        self.ent_api_key = ctk.CTkEntry(self.f_gemini, height=28, width=200, placeholder_text="Gemini API Key", show="*")
        self.ent_api_key.pack(side="left", padx=(0, 4))
        self.ent_api_key.bind("<FocusOut>", lambda e: self._save_all_configs())

        btn_toggle_key = ctk.CTkButton(self.f_gemini, text="👁", width=28, height=28, fg_color="#444444", command=self._toggle_key_visibility)
        btn_toggle_key.pack(side="left", padx=(0, 4))

        btn_save_key = ctk.CTkButton(self.f_gemini, text="저장", width=50, height=28, fg_color="#2e7d32", command=self._save_all_configs)
        btn_save_key.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(self.f_gemini, text="모델:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.cbo_gemini_model = ctk.CTkComboBox(
            self.f_gemini, values=["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash"], width=145, height=28,
            command=lambda _: self._save_all_configs()
        )
        self.cbo_gemini_model.pack(side="left")
        self.cbo_gemini_model.set("gemini-2.5-flash")

        # [B] Ollama 설정 위젯들
        self.f_ollama = ctk.CTkFrame(self.engine_conf_frame, fg_color="transparent")
        ctk.CTkLabel(self.f_ollama, text="URL:", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(0, 4))
        self.ent_ollama_url = ctk.CTkEntry(self.f_ollama, height=28, width=160)
        self.ent_ollama_url.pack(side="left", padx=(0, 4))
        self.ent_ollama_url.insert(0, "http://localhost:11434")
        self.ent_ollama_url.bind("<FocusOut>", lambda e: self._save_all_configs())

        btn_refresh_ollama = ctk.CTkButton(self.f_ollama, text="🔄 모델 조회", width=80, height=28, fg_color="#1f6aa5", command=self._refresh_ollama_models)
        btn_refresh_ollama.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(self.f_ollama, text="비전 모델:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.cbo_ollama_model = ctk.CTkComboBox(
            self.f_ollama, values=["qwen3-vl:4b", "gemma3:12b", "llava", "qwen2.5:7b"], width=145, height=28,
            command=lambda _: self._save_all_configs()
        )
        self.cbo_ollama_model.pack(side="left")
        self.cbo_ollama_model.set("qwen3-vl:4b")

        # 2. 본문 2분할 (좌: 3대 입력 칸 + 유형별 DOM 카탈로그 / 우: AI 생성 코드 뷰어)
        body = ctk.CTkFrame(self, corner_radius=6)
        body.pack(fill="both", expand=True, padx=6, pady=2)
        body.grid_columnconfigure(0, weight=1, minsize=520)
        body.grid_columnconfigure(1, weight=1, minsize=500)
        body.grid_rowconfigure(0, weight=1)

        # ---------------------------------------------------------------------
        # 좌측 패널: [1] 이미지 -> [2] 윈도우/URL 및 DOM 탭뷰 -> [3] 콤팩트 자연어
        # ---------------------------------------------------------------------
        left_f = ctk.CTkFrame(body, corner_radius=6)
        left_f.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")

        # [섹션 1] 이미지 지정 칸
        s1_head = ctk.CTkFrame(left_f, fg_color="transparent")
        s1_head.pack(fill="x", padx=8, pady=(4, 2))
        ctk.CTkLabel(s1_head, text="📸 [1/3] 타겟 화면 이미지 지정", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")

        cap_bar = ctk.CTkFrame(left_f, fg_color="transparent")
        cap_bar.pack(fill="x", padx=8, pady=(0, 2))

        btn_paste_clip = ctk.CTkButton(
            cap_bar, text="📋 붙여넣기 (Ctrl+V)", width=150, height=26,
            fg_color="#00695c", hover_color="#004d40", font=ctk.CTkFont(size=11, weight="bold"),
            command=self._paste_from_clipboard
        )
        btn_paste_clip.pack(side="left", padx=(0, 4))

        btn_cap_screen = ctk.CTkButton(
            cap_bar, text="📸 즉시 캡처", width=90, height=26,
            fg_color="#1f6aa5", hover_color="#144d75", font=ctk.CTkFont(size=11),
            command=self._capture_screen_now
        )
        btn_cap_screen.pack(side="left", padx=2)

        btn_browse_img = ctk.CTkButton(
            cap_bar, text="📁 파일 선택", width=85, height=26,
            fg_color="#444444", hover_color="#333333", font=ctk.CTkFont(size=11),
            command=self._browse_image_file
        )
        btn_browse_img.pack(side="left", padx=2)

        self.frame_preview = ctk.CTkFrame(left_f, height=75, fg_color="#181818", corner_radius=6)
        self.frame_preview.pack(fill="x", padx=8, pady=2)
        self.lbl_img_preview = ctk.CTkLabel(
            self.frame_preview, text="[클립보드 복사(Win+Shift+S) 후 Ctrl+V 또는 캡처/파일 선택]",
            font=ctk.CTkFont(size=11), text_color="#777777"
        )
        self.lbl_img_preview.pack(expand=True, pady=10)

        # [섹션 2] 열려있는 윈도우 창 선택 & 대상 URL & DOM 카탈로그
        s2_head = ctk.CTkFrame(left_f, fg_color="transparent")
        s2_head.pack(fill="x", padx=8, pady=(4, 2))
        ctk.CTkLabel(s2_head, text="🪟 [2/3] 열려있는 창 선택 & 실시간 DOM 수집", font=ctk.CTkFont(size=12, weight="bold"), text_color="#64b5f6").pack(side="left")

        # 윈도우 창 선택 드롭다운 행
        win_bar = ctk.CTkFrame(left_f, fg_color="transparent")
        win_bar.pack(fill="x", padx=8, pady=(0, 2))

        ctk.CTkLabel(win_bar, text="대상 창:", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(0, 4))
        self.cbo_windows = ctk.CTkComboBox(win_bar, values=["(열려있는 창을 검색 중...)"], height=28)
        self.cbo_windows.pack(side="left", fill="x", expand=True, padx=(0, 4))

        btn_refresh_wins = ctk.CTkButton(
            win_bar, text="🔄 창 갱신", width=75, height=28, fg_color="#333333",
            command=self._refresh_window_list
        )
        btn_refresh_wins.pack(side="right")

        # URL 입력 및 수집 트리거 행
        url_bar = ctk.CTkFrame(left_f, fg_color="transparent")
        url_bar.pack(fill="x", padx=8, pady=(2, 2))

        self.ent_target_url = ctk.CTkEntry(
            url_bar, height=28, placeholder_text="예: http://175.119.156.105:3000/contract/list"
        )
        self.ent_target_url.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.ent_target_url.bind("<FocusOut>", lambda e: self._save_all_configs())

        self.btn_harvest_dom = ctk.CTkButton(
            url_bar, text="🌐 실시간 DOM 수집 🔍", width=145, height=28,
            fg_color="#1f6aa5", hover_color="#144d75", font=ctk.CTkFont(size=11, weight="bold"),
            command=self._start_harvest_dom
        )
        self.btn_harvest_dom.pack(side="right")

        # ---------------------------------------------------------------------
        # 유형별 조작 가능 객체 탭뷰 (Tabview)
        # ---------------------------------------------------------------------
        self.lbl_dom_status = ctk.CTkLabel(
            left_f, text="📋 [페이지 내 전체 조작 가능 객체] (창 선택 또는 URL 입력 후 'DOM 수집' 클릭)",
            font=ctk.CTkFont(size=11, weight="bold"), text_color="#aaaaaa", anchor="w"
        )
        self.lbl_dom_status.pack(fill="x", padx=8, pady=(2, 0))

        self.tabview_dom = ctk.CTkTabview(left_f, height=180)
        self.tabview_dom.pack(fill="both", expand=True, padx=8, pady=(1, 2))

        self.tab_inputs = self.tabview_dom.add("📝 입력창 (0)")
        self.tab_buttons = self.tabview_dom.add("🔘 버튼 (0)")
        self.tab_selects = self.tabview_dom.add("🔽 드롭다운 (0)")
        self.tab_checks = self.tabview_dom.add("☑️ 체크/라디오 (0)")
        self.tab_grids = self.tabview_dom.add("📊 그리드 (0)")
        self.tab_links = self.tabview_dom.add("📑 링크/탭 (0)")

        self.scroll_frames = {
            "inputs": ctk.CTkScrollableFrame(self.tab_inputs, fg_color="transparent"),
            "buttons": ctk.CTkScrollableFrame(self.tab_buttons, fg_color="transparent"),
            "selects": ctk.CTkScrollableFrame(self.tab_selects, fg_color="transparent"),
            "checks_radios": ctk.CTkScrollableFrame(self.tab_checks, fg_color="transparent"),
            "grids": ctk.CTkScrollableFrame(self.tab_grids, fg_color="transparent"),
            "links": ctk.CTkScrollableFrame(self.tab_links, fg_color="transparent"),
        }
        for sf in self.scroll_frames.values():
            sf.pack(fill="both", expand=True)

        # ---------------------------------------------------------------------
        # 선택된 객체의 실시간 추천 셀렉터 표시 바
        # ---------------------------------------------------------------------
        sel_box = ctk.CTkFrame(left_f, corner_radius=6, fg_color="#181818")
        sel_box.pack(fill="x", padx=8, pady=(2, 4))

        ctk.CTkLabel(sel_box, text="🎯 선택된 셀렉터:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#64b5f6").pack(side="left", padx=(8, 4), pady=4)
        self.lbl_selected_sel = ctk.CTkEntry(sel_box, height=26, font=ctk.CTkFont(family="Consolas", size=11), fg_color="#262626")
        self.lbl_selected_sel.pack(side="left", fill="x", expand=True, padx=(0, 4), pady=4)
        self.lbl_selected_sel.insert(0, "(목록에서 원하는 요소를 클릭하면 셀렉터가 표시됩니다)")

        btn_copy_sel = ctk.CTkButton(sel_box, text="복사", width=45, height=26, font=ctk.CTkFont(size=10), fg_color="#444444", command=self._copy_selected_selector)
        btn_copy_sel.pack(side="right", padx=(0, 6), pady=4)

        btn_inject_prompt = ctk.CTkButton(sel_box, text="+ 요구사항에 추가", width=105, height=26, font=ctk.CTkFont(size=10), fg_color="#00695c", command=self._inject_selected_into_prompt)
        btn_inject_prompt.pack(side="right", padx=(0, 4), pady=4)

        # [섹션 3] 자연어 요구사항 입력 칸 (콤팩트 3~4줄 높이)
        s3_head = ctk.CTkFrame(left_f, fg_color="transparent")
        s3_head.pack(fill="x", padx=8, pady=(2, 1))
        ctk.CTkLabel(s3_head, text="✍️ [3/3] 자연어 자동화 요구사항 (3~4줄)", font=ctk.CTkFont(size=11, weight="bold"), text_color="#81c784").pack(side="left")

        self.txt_prompt = ctk.CTkTextbox(left_f, height=58, font=ctk.CTkFont(size=11))
        self.txt_prompt.pack(fill="x", padx=8, pady=(0, 4))
        self.txt_prompt.insert(
            "1.0",
            "아이디 입력창에 'admin', 비밀번호에 '1234'를 입력하고 로그인 버튼을 클릭해줘."
        )

        # 실행 버튼
        self.btn_generate = ctk.CTkButton(
            left_f, text="⚡ 증거 기반 AI 코드 생성 (Generate RPA Code)", height=36,
            fg_color="#00838f", hover_color="#006064", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._start_ai_generation
        )
        self.btn_generate.pack(fill="x", padx=8, pady=(2, 6))

        # ---------------------------------------------------------------------
        # 우측 패널: AI 생성 코드 & 상호작용 액션 툴바
        # ---------------------------------------------------------------------
        right_f = ctk.CTkFrame(body, corner_radius=6)
        right_f.grid(row=0, column=1, padx=(0, 6), pady=6, sticky="nsew")

        r_head = ctk.CTkFrame(right_f, fg_color="transparent")
        r_head.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(r_head, text="💻 AI가 생성한 완성형 RPA 코드", font=ctk.CTkFont(size=12, weight="bold"), text_color="#81c784").pack(side="left")

        self.txt_result_code = ctk.CTkTextbox(
            right_f, font=ctk.CTkFont(family="Consolas", size=12), fg_color="#181818"
        )
        self.txt_result_code.pack(fill="both", expand=True, padx=8, pady=4)

        b_bar = ctk.CTkFrame(right_f, fg_color="transparent")
        b_bar.pack(fill="x", padx=8, pady=(4, 8))

        btn_insert = ctk.CTkButton(
            b_bar, text="📋 스크립트 에디터로 전송 ➔", width=180, height=34,
            fg_color="#2e7d32", hover_color="#1b5e20", font=ctk.CTkFont(weight="bold"),
            command=self._do_insert_editor
        )
        btn_insert.pack(side="left", padx=(0, 4))

        btn_add_bot = ctk.CTkButton(
            b_bar, text="🤖 봇 에디터로 모듈 등록 ➔", width=180, height=34,
            fg_color="#6a1b9a", hover_color="#4a148c", font=ctk.CTkFont(weight="bold"),
            command=self._do_add_bot
        )
        btn_add_bot.pack(side="left", padx=4)

        btn_copy = ctk.CTkButton(
            b_bar, text="클립보드 복사", width=100, height=34,
            fg_color="#444444", hover_color="#333333", command=self._copy_result
        )
        btn_copy.pack(side="right")

    # =========================================================================
    # 열려있는 윈도우 창 목록 갱신
    # =========================================================================
    def _refresh_window_list(self):
        try:
            wins = WindowEnumerator.get_open_windows()
            self.open_windows_list = wins
            titles = [t for _, t in wins]
            if not titles:
                titles = ["(열려있는 활성 창이 없습니다)"]
            self.cbo_windows.configure(values=titles)
            if titles:
                # 브라우저 창 우선 선택
                default_choice = titles[0]
                for t in titles:
                    if "🌐" in t:
                        default_choice = t
                        break
                self.cbo_windows.set(default_choice)
        except Exception as e:
            self.cbo_windows.configure(values=[f"(창 목록 조회 오류: {e})"])

    # =========================================================================
    # 엔진 변경 및 모델 목록 갱신
    # =========================================================================
    def _on_engine_changed(self, choice: str):
        if "Gemini" in choice:
            self.f_ollama.pack_forget()
            self.f_gemini.pack(fill="x")
        else:
            self.f_gemini.pack_forget()
            self.f_ollama.pack(fill="x")
            self._refresh_ollama_models()
        self._save_all_configs()

    def _refresh_ollama_models(self):
        url = self.ent_ollama_url.get().strip() or "http://localhost:11434"
        models = OllamaVisionAgent.list_installed_models(url)
        if models:
            self.cbo_ollama_model.configure(values=models)
            if "qwen3-vl:4b" in models:
                self.cbo_ollama_model.set("qwen3-vl:4b")
            elif models:
                self.cbo_ollama_model.set(models[0])

    # =========================================================================
    # [실시간 DOM 수집] 활성 윈도우 / URL 수집 트리거
    # =========================================================================
    def _start_harvest_dom(self):
        url = self.ent_target_url.get().strip()
        selected_win_title = self.cbo_windows.get()

        if not url and not selected_win_title:
            messagebox.showwarning("입력 확인", "대상 웹 URL을 입력하거나 대상 창을 선택해 주십시오.")
            return

        self._save_all_configs()
        self.btn_harvest_dom.configure(text="⏳ DOM 수집 중...", state="disabled")
        self.lbl_dom_status.configure(text="⏳ 브라우저 세션 탐색 및 조작 가능 객체 수집 중...", text_color="#ffb74d")

        def _worker():
            try:
                res = DOMHarvester.harvest_live_dom(url, timeout_sec=15)
                self.after(0, lambda r=res: self._on_harvest_success(r))
            except Exception as e:
                self.after(0, lambda err=str(e): self._on_harvest_error(err))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_harvest_success(self, res: Dict[str, Any]):
        self.btn_harvest_dom.configure(text="🌐 실시간 DOM 수집 🔍", state="normal")
        catalog = res.get("catalog", {})
        self.current_catalog = catalog
        total_count = res.get("count", 0)
        sec = res.get("elapsed_sec", 0)
        engine = res.get("engine", "")

        self.lbl_dom_status.configure(
            text=f"✅ 총 {total_count}개 조작 가능 객체 수집 완료 ({sec}초, {engine})",
            text_color="#81c784"
        )

        for sf in self.scroll_frames.values():
            for w in sf.winfo_children():
                w.destroy()

        inputs = catalog.get("inputs", [])
        self._set_tab_title(self.tab_inputs, f"📝 입력창 ({len(inputs)})")
        for itm in inputs:
            self._render_element_card(self.scroll_frames["inputs"], itm, icon="📝", default_action="입력")

        buttons = catalog.get("buttons", [])
        self._set_tab_title(self.tab_buttons, f"🔘 버튼 ({len(buttons)})")
        for itm in buttons:
            self._render_element_card(self.scroll_frames["buttons"], itm, icon="🔘", default_action="클릭")

        selects = catalog.get("selects", [])
        self._set_tab_title(self.tab_selects, f"🔽 드롭다운 ({len(selects)})")
        for itm in selects:
            self._render_element_card(self.scroll_frames["selects"], itm, icon="🔽", default_action="선택")

        checks = catalog.get("checks_radios", [])
        self._set_tab_title(self.tab_checks, f"☑️ 체크/라디오 ({len(checks)})")
        for itm in checks:
            self._render_element_card(self.scroll_frames["checks_radios"], itm, icon="☑️", default_action="체크")

        grids = catalog.get("grids", [])
        self._set_tab_title(self.tab_grids, f"📊 그리드 ({len(grids)})")
        for itm in grids:
            self._render_element_card(self.scroll_frames["grids"], itm, icon="📊", default_action="더블클릭")

        links = catalog.get("links", [])
        self._set_tab_title(self.tab_links, f"📑 링크/탭 ({len(links)})")
        for itm in links:
            self._render_element_card(self.scroll_frames["links"], itm, icon="📑", default_action="클릭")

    def _set_tab_title(self, tab, new_title):
        try:
            for btn in self.tabview_dom._segmented_button._buttons_dict.values():
                if btn.cget("text").split(" ")[0] == new_title.split(" ")[0]:
                    btn.configure(text=new_title)
                    break
        except Exception:
            pass

    def _render_element_card(self, parent_frame, itm: Dict[str, Any], icon: str = "🔹", default_action: str = "클릭"):
        name = itm.get("label") or itm.get("text") or itm.get("type") or "요소"
        sel = itm.get("selector") or ""
        code = itm.get("playwrightCode") or ""

        card = ctk.CTkFrame(parent_frame, corner_radius=6, fg_color="#2b2b2b")
        card.pack(fill="x", pady=2, padx=2)

        top_r = ctk.CTkFrame(card, fg_color="transparent")
        top_r.pack(fill="x", padx=6, pady=(4, 2))

        ctk.CTkLabel(
            top_r, text=f"{icon} {name}", font=ctk.CTkFont(size=11, weight="bold"), text_color="#ffffff", anchor="w"
        ).pack(side="left", fill="x", expand=True)

        btn_pick = ctk.CTkButton(
            top_r, text="선택", width=45, height=22, font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#1f6aa5", hover_color="#144d75",
            command=lambda: self._select_element(name, sel, code)
        )
        btn_pick.pack(side="right", padx=2)

        bot_r = ctk.CTkFrame(card, fg_color="transparent")
        bot_r.pack(fill="x", padx=6, pady=(0, 4))

        ctk.CTkLabel(
            bot_r, text=f"셀렉터: {sel}", font=ctk.CTkFont(family="Consolas", size=10), text_color="#64b5f6", anchor="w"
        ).pack(side="left", fill="x", expand=True)

    def _select_element(self, name: str, sel: str, code: str):
        self.lbl_selected_sel.delete(0, "end")
        self.lbl_selected_sel.insert(0, code or f'page.locator("{sel}")')

    def _copy_selected_selector(self):
        sel_text = self.lbl_selected_sel.get().strip()
        if sel_text and not sel_text.startswith("("):
            self.clipboard_clear()
            self.clipboard_append(sel_text)
            messagebox.showinfo("복사 완료", "클립보드에 셀렉터 코드가 복사되었습니다!")

    def _inject_selected_into_prompt(self):
        sel_text = self.lbl_selected_sel.get().strip()
        if sel_text and not sel_text.startswith("("):
            self.txt_prompt.insert("end", f"\n- {sel_text}")

    def _on_harvest_error(self, err_msg: str):
        self.btn_harvest_dom.configure(text="🌐 실시간 DOM 수집 🔍", state="normal")
        self.lbl_dom_status.configure(text=f"❌ DOM 수집 실패: {err_msg[:45]}", text_color="#e57373")
        messagebox.showerror("DOM 수집 오류", f"대상 URL DOM 수집 실패:\n{err_msg}")

    # =========================================================================
    # [섹션 1] 클립보드 붙여넣기, 화면 캡처, 이미지 로드
    # =========================================================================
    def _paste_from_clipboard(self):
        try:
            clip_data = ImageGrab.grabclipboard()
            if isinstance(clip_data, Image.Image):
                temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures")
                os.makedirs(temp_dir, exist_ok=True)
                shot_path = os.path.join(temp_dir, f"clip_{int(time.time())}.png")
                clip_data.save(shot_path, "PNG")

                self.current_image_path = shot_path
                self._display_preview_image(shot_path)
                messagebox.showinfo("붙여넣기 성공", "📋 클립보드의 스크린샷 이미지가 성공적으로 로드되었습니다!")
                return
            elif isinstance(clip_data, list) and len(clip_data) > 0 and os.path.exists(clip_data[0]):
                p = clip_data[0]
                if p.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    self.current_image_path = p
                    self._display_preview_image(p)
                    messagebox.showinfo("파일 로드 성공", f"📋 클립보드의 이미지 파일이 로드되었습니다:\n{p}")
                    return

            messagebox.showwarning("붙여넣기 안내", "클립보드에 복사된 이미지가 없습니다.\n먼저 화면 캡처(Win+Shift+S)를 수행하신 후 붙여넣어 주십시오.")
        except Exception as e:
            messagebox.showerror("오류", f"클립보드 이미지 처리 실패: {e}")

    def _capture_screen_now(self):
        # 스튜디오 창을 잠시 내리고 캡처
        if self.parent_app and hasattr(self.parent_app, "withdraw"):
            self.parent_app.withdraw()
        time.sleep(0.3)

        temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures")
        os.makedirs(temp_dir, exist_ok=True)
        shot_path = os.path.join(temp_dir, f"screen_{int(time.time())}.png")

        try:
            if HAS_PYAUTOGUI:
                shot = pyautogui.screenshot()
                shot.save(shot_path)
            else:
                shot = ImageGrab.grab()
                shot.save(shot_path)

            self.current_image_path = shot_path
            self._display_preview_image(shot_path)
        except Exception as e:
            messagebox.showerror("캡처 오류", f"화면 캡처 실패: {e}")
        finally:
            if self.parent_app and hasattr(self.parent_app, "deiconify"):
                self.parent_app.deiconify()

    def _browse_image_file(self):
        p = filedialog.askopenfilename(filetypes=[("이미지 파일", "*.png;*.jpg;*.jpeg;*.webp")])
        if p:
            self.current_image_path = p
            self._display_preview_image(p)

    def _display_preview_image(self, path: str):
        try:
            pil_img = Image.open(path)
            pil_img.thumbnail((380, 70))
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)

            self.lbl_img_preview.configure(image=ctk_img, text="")
            self.lbl_img_preview.image = ctk_img
        except Exception as ex:
            self.lbl_img_preview.configure(text=f"미리보기 실패: {ex}")

    # =========================================================================
    # AI 코드 생성 실행
    # =========================================================================
    def _start_ai_generation(self):
        if not self.current_image_path or not os.path.exists(self.current_image_path):
            messagebox.showwarning("입력 확인", "[1단계: 타겟 화면 이미지]를 먼저 지정해 주십시오.\n(클립보드 붙여넣기, 즉시 캡처, 또는 파일 선택)")
            return

        prompt = self.txt_prompt.get("1.0", "end").strip()
        if not prompt:
            messagebox.showwarning("입력 확인", "[3단계: 자연어 자동화 요구사항]을 입력해 주십시오.")
            return

        target_url = self.ent_target_url.get().strip() or self.cbo_windows.get()
        catalog_summary = DOMHarvester.format_catalog_to_text(self.current_catalog)
        engine_choice = self.seg_engine.get()

        self._save_all_configs()

        if "Gemini" in engine_choice:
            api_key = self.ent_api_key.get().strip()
            if not api_key:
                messagebox.showwarning("입력 확인", "Google Gemini API Key를 먼저 입력해 주십시오.")
                return
            model = self.cbo_gemini_model.get()
            self.btn_generate.configure(text="⏳ Gemini 증거 기반 분석 중... (약 1~2초)", state="disabled")
            self.txt_result_code.delete("1.0", "end")
            self.txt_result_code.insert("1.0", f"// 🤖 Google Gemini ({model})에 이미지와 URL, 수집된 UI 객체 카탈로그를 대조 분석 중입니다...\n")

            def _worker_gemini():
                try:
                    code, full_text = GeminiVisionAgent.call_gemini_vision(
                        api_key=api_key,
                        image_path=self.current_image_path,
                        user_prompt=prompt,
                        target_url=target_url,
                        model=model,
                        page_html=catalog_summary
                    )
                    self.after(0, lambda c=code, f=full_text: self._on_generation_success(c, f, "Gemini"))
                except Exception as e:
                    self.after(0, lambda err=str(e): self._on_generation_error(err))

            threading.Thread(target=_worker_gemini, daemon=True).start()

        else:
            ollama_url = self.ent_ollama_url.get().strip() or "http://localhost:11434"
            model = self.cbo_ollama_model.get()
            self.btn_generate.configure(text="⏳ Ollama 증거 기반 비전 추론 중... (약 3~6초)", state="disabled")
            self.txt_result_code.delete("1.0", "end")
            self.txt_result_code.insert("1.0", f"// 🦙 Local Ollama ({model})에서 이미지와 수집된 UI 객체 카탈로그를 로컬 GPU로 추론 중입니다...\n// (100% 무료 / 사내 보안 유지 / 외부 유출 없음)\n")

            def _worker_ollama():
                try:
                    code, full_text = OllamaVisionAgent.call_ollama_vision(
                        ollama_url=ollama_url,
                        model=model,
                        image_path=self.current_image_path,
                        user_prompt=prompt,
                        target_url=target_url,
                        page_html=catalog_summary
                    )
                    self.after(0, lambda c=code, f=full_text: self._on_generation_success(c, f, f"Ollama ({model})"))
                except Exception as e:
                    self.after(0, lambda err=str(e): self._on_generation_error(err))

            threading.Thread(target=_worker_ollama, daemon=True).start()

    def _on_generation_success(self, code: str, full_text: str, engine_name: str):
        self.btn_generate.configure(text="⚡ 증거 기반 AI 코드 생성 (Generate RPA Code)", state="normal")
        self.txt_result_code.delete("1.0", "end")
        self.txt_result_code.insert("1.0", code)
        messagebox.showinfo("생성 완료", f"✅ {engine_name} 엔진이 수집된 UI 객체 카탈로그를 기반으로 100% 무결점 코드를 생성하였습니다!")

    def _on_generation_error(self, err_msg: str):
        self.btn_generate.configure(text="⚡ 증거 기반 AI 코드 생성 (Generate RPA Code)", state="normal")
        self.txt_result_code.delete("1.0", "end")
        self.txt_result_code.insert("1.0", f"[오류 발생]\n{err_msg}")
        messagebox.showerror("AI 생성 오류", f"코드 생성 실패:\n{err_msg}")

    # =========================================================================
    # 액션 버튼 핸들러 (스크립트 에디터 / 봇 에디터 탭으로 전송)
    # =========================================================================
    def _do_insert_editor(self):
        code = self.txt_result_code.get("1.0", "end").strip()
        if not code or code.startswith("//") or code.startswith("[오류"):
            messagebox.showwarning("안내", "전송할 유효한 생성 코드가 없습니다.")
            return

        if self.on_insert_code:
            self.on_insert_code(code)
            if self.on_switch_tab:
                self.on_switch_tab("script")
            messagebox.showinfo("전송 완료", "파이썬 스크립트 에디터 탭으로 코드가 전송되었습니다!")

    def _do_add_bot(self):
        code = self.txt_result_code.get("1.0", "end").strip()
        if not code or code.startswith("//") or code.startswith("[오류"):
            messagebox.showwarning("안내", "추가할 유효한 생성 코드가 없습니다.")
            return

        engine_str = "Gemini" if "Gemini" in self.seg_engine.get() else self.cbo_ollama_model.get()
        prompt_first_line = self.txt_prompt.get("1.0", "end").strip().splitlines()[0][:20]
        mod_data = {
            "name": f"ai_mod_{int(time.time())}",
            "title": f"AI 생성: {prompt_first_line}",
            "category": "웹조작",
            "description": f"증거기반 Vision AI 생성 모듈 ({engine_str})",
            "code": code
        }

        if self.on_add_to_bot:
            self.on_add_to_bot(mod_data)
            if self.on_switch_tab:
                self.on_switch_tab("bot")
            messagebox.showinfo("모듈 등록 완료", "🤖 봇 에디터 탭에 새 모듈 카드가 등록되었습니다!")

    def _copy_result(self):
        code = self.txt_result_code.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(code)

    def _toggle_key_visibility(self):
        if self.ent_api_key.cget("show") == "*":
            self.ent_api_key.configure(show="")
        else:
            self.ent_api_key.configure(show="*")

    # =========================================================================
    # 설정 자동 영구 저장 및 복원
    # =========================================================================
    def _load_saved_configs(self):
        k = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
        ollama_u = "http://localhost:11434"
        target_u = "http://175.119.156.105:3000/contract/list"
        last_engine = "☁️ Google Gemini (초고속)"
        last_gemini_model = "gemini-2.5-flash"
        last_ollama_model = "qwen3-vl:4b"

        for cfg_path in [
            self._CONFIG_FILE,
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "UBUS_contract", "config.json")
        ]:
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                        k = k or cfg.get("gemini_api_key", "")
                        ollama_u = cfg.get("ollama_url", ollama_u)
                        target_u = cfg.get("target_url") or cfg.get("erp_url") or target_u
                        last_engine = cfg.get("last_ai_engine", last_engine)
                        last_gemini_model = cfg.get("last_gemini_model", last_gemini_model)
                        last_ollama_model = cfg.get("last_ollama_model", last_ollama_model)
                except Exception:
                    pass

        if k:
            self.ent_api_key.insert(0, k)
        if ollama_u:
            self.ent_ollama_url.delete(0, "end")
            self.ent_ollama_url.insert(0, ollama_u)
        if target_u:
            self.ent_target_url.delete(0, "end")
            self.ent_target_url.insert(0, target_u)

        if last_engine:
            self.seg_engine.set(last_engine)
            self._on_engine_changed(last_engine)

        if last_gemini_model in ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash"]:
            self.cbo_gemini_model.set(last_gemini_model)

        if last_ollama_model:
            self.cbo_ollama_model.set(last_ollama_model)

    def _save_all_configs(self):
        data_to_save = {
            "gemini_api_key": self.ent_api_key.get().strip(),
            "ollama_url": self.ent_ollama_url.get().strip(),
            "target_url": self.ent_target_url.get().strip(),
            "last_ai_engine": self.seg_engine.get(),
            "last_gemini_model": self.cbo_gemini_model.get(),
            "last_ollama_model": self.cbo_ollama_model.get()
        }

        for cfg_path in [
            self._CONFIG_FILE,
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "UBUS_contract", "config.json")
        ]:
            try:
                data = {}
                if os.path.exists(cfg_path):
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                data.update(data_to_save)
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass


class AIVisionModal(ctk.CTkToplevel):
    """호환성을 위한 모달 래퍼 (기존 호출부 지원)"""

    def __init__(self, parent, on_insert_code: Optional[Callable[[str], None]] = None,
                 on_add_to_bot: Optional[Callable[[Dict[str, Any]], None]] = None):
        super().__init__(parent)
        self.title("🤖 증거 기반 Vision AI 셀렉터 & RPA 코드 생성기")
        self.geometry("1120x920")
        self.minsize(980, 740)
        self.attributes("-topmost", True)

        self.vision_frame = AIVisionFrame(
            self, on_insert_code=on_insert_code, on_add_to_bot=on_add_to_bot,
            on_switch_tab=lambda _: self.destroy()
        )
        self.vision_frame.pack(fill="both", expand=True, padx=4, pady=4)


def open_ai_vision_generator(parent, on_insert: Optional[Callable[[str], None]] = None,
                             on_add_bot: Optional[Callable[[Dict[str, Any]], None]] = None) -> AIVisionModal:
    modal = AIVisionModal(parent, on_insert_code=on_insert, on_add_to_bot=on_add_bot)
    return modal
