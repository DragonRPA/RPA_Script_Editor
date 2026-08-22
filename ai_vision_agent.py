"""
Universal RPA - Vision AI Code Generator & DOM Inspector
Google Gemini + Local Ollama
- 최상위 메인 탭 내장
- 윈도우 핸들(HWND) 직통 검사 (새로고침/깜빡임 0%, 세션 100% 보존)
- 브라우저 선택 (Chrome / Edge / 기본)
- 모든 폰트 크기 12pt 이상 보장
- 건조한 명사/동사 UI 표준
"""

import os
import sys
import json
import base64
import threading
import time
import ctypes
import re
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
    """Windows 활성 윈도우 핸들(HWND) 및 타이틀 열거자"""

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
                        tag = "창"
                        if any(kw in title.lower() for kw in ["chrome", "edge", "whale", "firefox", "brave"]):
                            tag = "웹"
                        elif any(kw in title.lower() for kw in ["excel", "hwp", "word", "erp", "더존", "sap"]):
                            tag = "앱"
                        windows.append((hwnd, f"[{tag}] {title}"))
            hwnd = user32.GetWindow(hwnd, GW_HWNDNEXT)

        return windows


class GeminiVisionAgent:
    """Google Gemini 비전 API 통신 매니저"""

    @classmethod
    def get_system_instruction(cls, browser_choice: str = "Chrome") -> str:
        b_low = (browser_choice or "").lower()
        if "edge" in b_low:
            launch_code = 'browser = playwright.chromium.launch(channel="msedge", headless=False, args=["--start-maximized"])'
        elif "chrome" in b_low:
            launch_code = 'browser = playwright.chromium.launch(channel="chrome", headless=False, args=["--start-maximized"])'
        else:
            launch_code = 'browser = playwright.chromium.launch(headless=False, args=["--start-maximized"])'

        return f"""당신은 파이썬 RPA 및 웹/데스크톱 자동화 엔지니어링 전문가입니다.
제공된 [화면 스크린샷], [대상 웹 URL/창], [UI 객체 목록], [자연어 요구사항]을 분석하여 실행 가능한 파이썬 Playwright 코드를 작성하십시오.

[작성 규칙]
1. 셀렉터 매핑: [UI 객체 목록]에 존재하는 실제 id, name, placeholder, class 속성을 스크린샷과 대조하여 작성하십시오.
2. 브라우저 기동:
   ```python
   {launch_code}
   context = browser.new_context(no_viewport=True)
   page = context.new_page()
   ```
3. 대상 URL이 있으면 `page.goto("{{target_url}}")` 및 `page.wait_for_load_state("domcontentloaded")`를 포함하십시오.
4. 다중 Fallback 셀렉터를 적용하고, 조작 전 `locator.wait_for(state="visible", timeout=5000)`를 적용하십시오.
5. 실행 가능한 파이썬 코드 블록(```python ... ```)을 최우선으로 출력하십시오.
"""

    @classmethod
    def call_gemini_vision(cls, api_key: str, image_path: str, user_prompt: str,
                           target_url: str = "", model: str = "gemini-2.5-flash", page_html: str = "",
                           browser_choice: str = "Chrome") -> Tuple[str, str]:
        if not api_key:
            raise ValueError("Google Gemini API Key가 설정되지 않았습니다.")

        img_b64 = None
        mime_type = "image/png"
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")
            if image_path.lower().endswith(".jpg") or image_path.lower().endswith(".jpeg"):
                mime_type = "image/jpeg"
            elif image_path.lower().endswith(".webp"):
                mime_type = "image/webp"

        prompt_text = ""
        if target_url:
            prompt_text += f"[대상 URL / 창]\n{target_url}\n\n"
        if browser_choice:
            prompt_text += f"[지정 브라우저]\n{browser_choice}\n\n"
        if page_html:
            prompt_text += f"[UI 객체 목록]\n{page_html[:4500]}\n\n"
        prompt_text += f"[요구사항]\n{user_prompt}\n\n"
        if img_b64:
            prompt_text += "위 화면 스크린샷과 UI 객체 목록, 요구사항을 바탕으로 Playwright 코드를 작성하십시오."
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
        else:
            prompt_text += "위 UI 객체 목록과 요구사항을 바탕으로 Playwright 코드를 작성하십시오."
            parts = [
                {
                    "text": prompt_text
                }
            ]

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "system_instruction": {
                "parts": [{"text": cls.get_system_instruction(browser_choice)}]
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
    """Ollama 비전 API 통신 매니저"""

    @classmethod
    def get_system_instruction(cls, browser_choice: str = "Chrome") -> str:
        b_low = (browser_choice or "").lower()
        if "edge" in b_low:
            launch_code = 'browser = playwright.chromium.launch(channel="msedge", headless=False, args=["--start-maximized"])'
        elif "chrome" in b_low:
            launch_code = 'browser = playwright.chromium.launch(channel="chrome", headless=False, args=["--start-maximized"])'
        else:
            launch_code = 'browser = playwright.chromium.launch(headless=False, args=["--start-maximized"])'

        return f"""당신은 파이썬 RPA 및 웹/데스크톱 자동화 엔지니어링 전문가입니다.
제공된 [화면 스크린샷], [대상 URL/창], [UI 객체 목록], [자연어 요구사항]을 분석하여 Playwright 자동화 코드를 작성하십시오.

[작성 규칙]
1. [UI 객체 목록]의 id, name, placeholder, class 속성을 스크린샷과 대조하여 셀렉터를 작성하십시오.
2. Playwright 브라우저 기동 시 `{launch_code}`, `context = browser.new_context(no_viewport=True)`를 적용하십시오.
3. 대상 URL이 있으면 `page.goto("{{target_url}}")` 코드를 최상단에 작성하십시오.
4. 실행 가능한 코드를 ```python ... ``` 블록으로 감싸서 출력하십시오."""

    @classmethod
    def list_installed_models(cls, ollama_url: str = "http://localhost:11434") -> List[str]:
        """Ollama 설치 모델 목록 조회 (비전 AI 모델 vl/vision/llava 등 제외 및 코드/텍스트 모델 우선 정렬)"""
        vision_keywords = ["vl", "vision", "llava", "minicpm", "moondream", "bakllava"]
        try:
            r = requests.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=3)
            if r.status_code == 200:
                all_models = [m["name"] for m in r.json().get("models", [])]
                filtered = [
                    m for m in all_models
                    if not any(kw in m.lower() for kw in vision_keywords)
                ]
                if filtered:
                    def sort_key(m):
                        ml = m.lower()
                        if "coder" in ml or "code" in ml:
                            return 0
                        return 1
                    return sorted(filtered, key=sort_key)
                elif all_models:
                    return all_models
        except Exception:
            pass
        return ["qwen2.5-coder:7b", "qwen2.5:7b", "deepseek-coder:6.7b", "codellama:7b", "llama3.1:8b"]

    @classmethod
    def call_ollama_vision(cls, ollama_url: str, model: str, image_path: str,
                           user_prompt: str, target_url: str = "", page_html: str = "",
                           browser_choice: str = "Chrome") -> Tuple[str, str]:
        img_b64 = None
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")

        prompt_body = f"{cls.get_system_instruction(browser_choice)}\n\n"
        if target_url:
            prompt_body += f"[대상 URL / 창]\n{target_url}\n\n"
        if browser_choice:
            prompt_body += f"[지정 브라우저]\n{browser_choice}\n\n"
        if page_html:
            prompt_body += f"[UI 객체 목록]\n{page_html[:4500]}\n\n"
        prompt_body += f"[요구사항]\n{user_prompt}\n\n"
        if img_b64:
            prompt_body += "위 화면 스크린샷과 UI 객체 목록에서 타겟 요소를 찾아 Playwright 코드를 작성하십시오."
        else:
            prompt_body += "위 UI 객체 목록과 요구사항을 바탕으로 Playwright 코드를 작성하십시오."

        url = f"{ollama_url.rstrip('/')}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt_body,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_predict": 4096
            }
        }
        if img_b64:
            payload["images"] = [img_b64]

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
    AI 비전 코드 생성 및 DOM 분석기 프레임
    - 건조한 명사/동사 UI 표준
    - 브라우저 선택 (Chrome / Edge / 기본)
    - 최소 폰트 크기 12pt 이상 보장
    """

    _CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recorder_config.json")

    def __init__(self, parent, on_insert_code: Optional[Callable[[str], None]] = None,
                 on_add_to_bot: Optional[Callable[[Dict[str, Any]], None]] = None,
                 on_switch_tab: Optional[Callable[[str], None]] = None,
                 project: Optional[Dict[str, Any]] = None,
                 db_manager=None):
        super().__init__(parent, fg_color="transparent")

        self.parent_app = parent
        self.on_insert_code = on_insert_code
        self.on_add_to_bot = on_add_to_bot
        self.on_switch_tab = on_switch_tab
        self.current_project: Optional[Dict[str, Any]] = project
        self.db = db_manager

        self.current_image_path: Optional[str] = None
        self.preview_image_ref: Optional[ImageTk.PhotoImage] = None
        self.current_catalog: Dict[str, List[Dict[str, Any]]] = {}
        self.open_windows_list: List[Tuple[int, str]] = []
        self.keep_list: List[Dict[str, Any]] = []
        self.data_source_path: str = ""
        self.data_source_columns: List[str] = []   # 컬럼명 목록
        self.data_source_row_count: int = 0
        self.data_source_sample: List[Dict] = []   # 5행 샘플
        self.current_task_id: Optional[int] = None

        self._build_ui()
        self._load_saved_configs()
        self._refresh_window_list()

    def _safe_after(self, ms: int, func):
        """스레드 종료 시 위젯 소멸로 인한 RuntimeError 방어"""
        try:
            if self.winfo_exists():
                self.after(ms, func)
        except Exception:
            pass

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)
        # 프로젝트 컨텍스트 바 (최상단) 고정
        proj_bar = ctk.CTkFrame(self, fg_color="#111111", corner_radius=0, height=32)
        proj_bar.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 2))
        proj_bar.pack_propagate(False)

        self.lbl_proj_name = ctk.CTkLabel(
            proj_bar, text="[선택 안됨]",
            font=ctk.CTkFont(size=11, weight="bold"), text_color="#888888"
        )
        self.lbl_proj_name.pack(side="left", padx=(12, 0))

        ctk.CTkButton(
            proj_bar, text="프로젝트 전환", width=90, height=22,
            font=ctk.CTkFont(size=11), fg_color="#333333", hover_color="#444444",
            command=self._switch_project
        ).pack(side="right", padx=8)

        # 1. 상단 글로벌 컨트롤 바 (AI 설정 + 대상 URL/창)
        top_ctrl = ctk.CTkFrame(self, corner_radius=4)
        top_ctrl.grid(row=1, column=0, sticky="ew", padx=6, pady=(2, 1))

        # 좌우 분할을 위해 grid 사용
        top_ctrl.grid_columnconfigure(0, weight=0, minsize=420)
        top_ctrl.grid_columnconfigure(1, weight=0)
        top_ctrl.grid_columnconfigure(2, weight=1)
        top_ctrl.grid_rowconfigure(0, weight=0)
        
        # --- 좌측: AI 설정 ---
        ai_frame = ctk.CTkFrame(top_ctrl, fg_color="transparent")
        ai_frame.grid(row=0, column=0, sticky="nw", padx=6, pady=2)
        
        # Row 1 of AI
        ai_r1 = ctk.CTkFrame(ai_frame, fg_color="transparent")
        ai_r1.pack(fill="x", pady=(0, 2))
        ctk.CTkLabel(ai_r1, text="AI 엔진", font=ctk.CTkFont(size=12, weight="bold"), width=60, anchor="w").pack(side="left")
        self.seg_engine = ctk.CTkSegmentedButton(
            ai_r1, values=["Google Gemini", "Local Ollama"],
            font=ctk.CTkFont(size=12, weight="bold"), command=self._on_engine_changed
        )
        self.seg_engine.pack(side="left", padx=4)

        # Row 2 of AI
        ai_r2 = ctk.CTkFrame(ai_frame, fg_color="transparent")
        ai_r2.pack(fill="x", pady=2)
        self.engine_conf_frame = ctk.CTkFrame(ai_r2, fg_color="transparent")
        self.engine_conf_frame.pack(fill="both", expand=True)

        # Gemini
        self.f_gemini = ctk.CTkFrame(self.engine_conf_frame, fg_color="transparent")
        ctk.CTkLabel(self.f_gemini, text="API 키", font=ctk.CTkFont(size=12, weight="bold"), width=50, anchor="w").pack(side="left")
        self.ent_api_key = ctk.CTkEntry(self.f_gemini, height=26, width=120, font=ctk.CTkFont(size=11), show="*")
        self.ent_api_key.pack(side="left", padx=2)
        btn_toggle_key = ctk.CTkButton(self.f_gemini, text="보기", width=36, height=26, font=ctk.CTkFont(size=11), fg_color="#444444", command=self._toggle_key_visibility)
        btn_toggle_key.pack(side="left", padx=2)
        ctk.CTkLabel(self.f_gemini, text="모델", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=4)
        self.cbo_gemini_model = ctk.CTkComboBox(self.f_gemini, values=["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash"], width=130, height=26, font=ctk.CTkFont(size=11))
        self.cbo_gemini_model.pack(side="left")
        self.cbo_gemini_model.set("gemini-2.5-flash")

        # Ollama
        self.f_ollama = ctk.CTkFrame(self.engine_conf_frame, fg_color="transparent")
        ctk.CTkLabel(self.f_ollama, text="URL", font=ctk.CTkFont(size=12, weight="bold"), width=40, anchor="w").pack(side="left")
        self.ent_ollama_url = ctk.CTkEntry(self.f_ollama, height=26, width=140, font=ctk.CTkFont(size=11))
        self.ent_ollama_url.pack(side="left", padx=2)
        self.ent_ollama_url.insert(0, "http://localhost:11434")
        btn_refresh_ollama = ctk.CTkButton(self.f_ollama, text="조회", width=40, height=26, font=ctk.CTkFont(size=11), fg_color="#1f6aa5", command=self._refresh_ollama_models)
        btn_refresh_ollama.pack(side="left", padx=2)
        ctk.CTkLabel(self.f_ollama, text="모델", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=4)
        self.cbo_ollama_model = ctk.CTkComboBox(self.f_ollama, values=["qwen2.5-coder:7b", "qwen2.5:7b", "deepseek-coder:6.7b"], width=120, height=26, font=ctk.CTkFont(size=11))
        self.cbo_ollama_model.pack(side="left")

        # --- 수직 구분선 ---
        sep = ctk.CTkFrame(top_ctrl, width=2, height=1, fg_color="#333333")
        sep.grid(row=0, column=1, sticky="ns", padx=2, pady=2)

        # --- 우측: 타겟 설정 ---
        tgt_frame = ctk.CTkFrame(top_ctrl, fg_color="transparent")
        tgt_frame.grid(row=0, column=2, sticky="nsew", padx=6, pady=2)

        # Row 1 of Target
        t_row1 = ctk.CTkFrame(tgt_frame, fg_color="transparent")
        t_row1.pack(fill="x", pady=(0, 2))
        self.lbl_cdp_status = ctk.CTkLabel(t_row1, text="● CDP 미연결", font=ctk.CTkFont(size=11, weight="bold"), text_color="#888888", width=80, anchor="w")
        self.lbl_cdp_status.pack(side="left")
        btn_cdp_launch = ctk.CTkButton(t_row1, text="Chrome", width=55, height=26, font=ctk.CTkFont(size=11), fg_color="#1a3a5c", command=lambda: self._create_cdp_shortcut("chrome"))
        btn_cdp_launch.pack(side="left", padx=2)
        btn_cdp_launch_edge = ctk.CTkButton(t_row1, text="Edge", width=45, height=26, font=ctk.CTkFont(size=11), fg_color="#1a3a3a", command=lambda: self._create_cdp_shortcut("edge"))
        btn_cdp_launch_edge.pack(side="left", padx=(2, 10))

        ctk.CTkLabel(t_row1, text="대상 창:", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=2)
        self.cbo_windows = ctk.CTkComboBox(t_row1, values=["(창 검색 전)"], height=26, font=ctk.CTkFont(size=11))
        self.cbo_windows.pack(side="left", fill="x", expand=True, padx=4)
        btn_refresh_wins = ctk.CTkButton(t_row1, text="갱신", width=45, height=26, font=ctk.CTkFont(size=11), fg_color="#333333", command=self._refresh_window_list)
        btn_refresh_wins.pack(side="right")

        # Row 2 of Target
        t_row2 = ctk.CTkFrame(tgt_frame, fg_color="transparent")
        t_row2.pack(fill="x", pady=2)
        ctk.CTkLabel(t_row2, text="대상 URL:", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=2)
        self.cbo_target_url = ctk.CTkComboBox(t_row2, height=26, font=ctk.CTkFont(size=11), values=[])
        self.cbo_target_url.pack(side="left", fill="x", expand=True, padx=4)
        # 콤보박스는 FocusOut 대신 선택 시 저장되게 하거나 그냥 두어도 됩니다.
        
        btn_save_url = ctk.CTkButton(t_row2, text="저장", width=45, height=26, font=ctk.CTkFont(size=11), fg_color="#333333", command=self._save_target_url)
        btn_save_url.pack(side="left", padx=(0, 4))
        
        self.btn_harvest_dom = ctk.CTkButton(t_row2, text="DOM 수집", width=70, height=26, fg_color="#1f6aa5", font=ctk.CTkFont(size=11, weight="bold"), command=self._start_harvest_dom)
        self.btn_harvest_dom.pack(side="right")


        # 2. 본문 3분할 (좌: 리소스 / 중: 프롬프트&Keep / 우: 코드 결과)
        body = ctk.CTkFrame(self, corner_radius=6)
        body.grid(row=2, column=0, sticky="nsew", padx=6, pady=(1, 2))
        
        # 3-Column Grid Configuration
        body.grid_columnconfigure(0, weight=1, minsize=340) # Col 0: DOM / Data
        body.grid_columnconfigure(1, weight=2, minsize=420) # Col 1: Keep / Prompt (Wider)
        body.grid_columnconfigure(2, weight=1, minsize=340) # Col 2: Result Code
        body.grid_rowconfigure(0, weight=1)

        # =====================================================================
        # [열 0] 자원 패널 (DOM 카탈로그 + 데이터 소스)
        # =====================================================================
        col0_f = ctk.CTkFrame(body, corner_radius=6)
        col0_f.grid(row=0, column=0, padx=(6, 3), pady=6, sticky="nsew")

        # 조작 객체 상태 라벨
        self.lbl_dom_status = ctk.CTkLabel(
            col0_f, text="조작 객체 목록 (DOM)",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#aaaaaa", anchor="w"
        )
        self.lbl_dom_status.pack(fill="x", padx=8, pady=(6, 2))

        # 객체 검색 필터 바
        f_dom_filter = ctk.CTkFrame(col0_f, fg_color="transparent")
        f_dom_filter.pack(fill="x", padx=8, pady=(0, 4))

        self.ent_dom_filter = ctk.CTkEntry(
            f_dom_filter, height=26, font=ctk.CTkFont(size=11),
            placeholder_text="객체 검색 (텍스트, 경로, 셀렉터)"
        )
        self.ent_dom_filter.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.ent_dom_filter.bind("<KeyRelease>", lambda e: self._filter_dom_catalog())

        self.btn_clear_dom_filter = ctk.CTkButton(
            f_dom_filter, text="✕", width=26, height=26, font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#333333", hover_color="#444444",
            command=self._clear_dom_filter
        )
        self.btn_clear_dom_filter.pack(side="right")

        self.tabview_dom = ctk.CTkTabview(col0_f)
        self.tabview_dom.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        
        self.tab_inputs = self.tabview_dom.add("입력창 (0)")
        self.tab_buttons = self.tabview_dom.add("버튼 (0)")
        self.tab_selects = self.tabview_dom.add("드롭다운 (0)")
        self.tab_checks = self.tabview_dom.add("체크/라디오 (0)")
        self.tab_grids = self.tabview_dom.add("그리드 (0)")
        self.tab_links = self.tabview_dom.add("링크 (0)")

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

        # 데이터 소스 패널
        ds_head = ctk.CTkFrame(col0_f, fg_color="transparent")
        ds_head.pack(fill="x", padx=8, pady=(4, 2))
        ctk.CTkLabel(ds_head, text="데이터 소스", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        ctk.CTkButton(
            ds_head, text="폴더 배열", width=65, height=24,
            font=ctk.CTkFont(size=11), fg_color="#4a148c", hover_color="#6a1b9a",
            command=self._load_folder_source
        ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(
            ds_head, text="파일 선택", width=65, height=24,
            font=ctk.CTkFont(size=11), fg_color="#1a3a5c", hover_color="#1f6aa5",
            command=self._load_data_source
        ).pack(side="right")

        self.frm_ds_info = ctk.CTkFrame(col0_f, fg_color="#161b22", corner_radius=6, height=34)
        self.frm_ds_info.pack(fill="x", padx=8, pady=(0, 6))
        self.frm_ds_info.pack_propagate(False)
        self.lbl_ds_status = ctk.CTkLabel(
            self.frm_ds_info,
            text="파일 없음 - Excel/CSV/JSON",
            font=ctk.CTkFont(size=11), text_color="#444444", anchor="w"
        )
        self.lbl_ds_status.pack(fill="x", padx=8, pady=6)


        # =====================================================================
        # [열 1] 로직 & 조립 패널 (Keep + 프롬프트 탭뷰)
        # =====================================================================
        col1_f = ctk.CTkFrame(body, corner_radius=6)
        col1_f.grid(row=0, column=1, padx=3, pady=6, sticky="nsew")

        # Keep 패널
        keep_head = ctk.CTkFrame(col1_f, fg_color="transparent")
        keep_head.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(keep_head, text="Keep 목록", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        ctk.CTkButton(
            keep_head, text="전체 삭제", width=60, height=24,
            font=ctk.CTkFont(size=11), fg_color="#5a2d2d", hover_color="#7a1a1a",
            command=self._clear_keep_list
        ).pack(side="right")

        # Height를 고정하지 않고 일부 유동적으로 구성
        self.frm_keep_panel = ctk.CTkScrollableFrame(col1_f, height=140, fg_color="#1a1a1a", corner_radius=6)
        self.frm_keep_panel.pack(fill="x", padx=8, pady=(0, 6))

        ctk.CTkLabel(
            self.frm_keep_panel,
            text="Keep된 객체가 없습니다. 수집된 DOM 요소에서 [Keep ★] 버튼을 누르세요.",
            font=ctk.CTkFont(size=11), text_color="#555555"
        ).pack(pady=10)

        # 자동화 요구사항 (프롬프트 에디터)
        s3_head = ctk.CTkFrame(col1_f, fg_color="transparent")
        s3_head.pack(fill="x", padx=8, pady=(4, 2))
        ctk.CTkLabel(s3_head, text="자동화 요구사항", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")

        self.btn_load_task = ctk.CTkButton(
            s3_head, text="불러오기 ▾", width=76, height=22,
            font=ctk.CTkFont(size=11), fg_color="#2b2b2b", hover_color="#3a3a3a",
            command=self._show_load_task_popup
        )
        self.btn_load_task.pack(side="right", padx=(4, 0))

        self.btn_save_task = ctk.CTkButton(
            s3_head, text="저장", width=52, height=22,
            font=ctk.CTkFont(size=11, weight="bold"), fg_color="#1b5e20", hover_color="#2e7d32",
            command=self._save_prompt_draft
        )
        self.btn_save_task.pack(side="right", padx=(4, 0))

        ctk.CTkLabel(s3_head, text="Keep 더블클릭 시 변수 삽입", font=ctk.CTkFont(size=10), text_color="#ffd54f").pack(side="right", padx=(0, 6))

        # 프롬프트 입력창 (직접 배치하여 수직 공간 최대화)
        self.txt_prompt = ctk.CTkTextbox(col1_f, font=ctk.CTkFont(size=12))
        self.txt_prompt.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.txt_prompt.insert(
            "1.0",
            "아래의 요구를 순차적으로 수행하는 파이썬-playwrite 자동화 스크립트를 작성하시오\n\n"
        )
        self._init_prompt_highlight()

        # 하단 태스크 메타 및 버튼
        task_meta = ctk.CTkFrame(col1_f, fg_color="transparent")
        task_meta.pack(fill="x", padx=8, pady=(2, 4))

        ctk.CTkLabel(task_meta, text="태스크 이름:", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(0, 4))
        self.ent_task_title = ctk.CTkEntry(task_meta, height=26, font=ctk.CTkFont(size=11), placeholder_text="예: 거래처 검색 루프")
        self.ent_task_title.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.var_build_type = ctk.StringVar(value="debug")
        ctk.CTkRadioButton(task_meta, text="DEBUG", variable=self.var_build_type, value="debug",
                           font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 6))
        ctk.CTkRadioButton(task_meta, text="RELEASE", variable=self.var_build_type, value="release",
                           font=ctk.CTkFont(size=11), text_color="#ffd54f").pack(side="left")

        self.btn_generate = ctk.CTkButton(
            col1_f, text="코드 생성", height=38,
            fg_color="#00838f", hover_color="#006064", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._start_ai_generation
        )
        self.btn_generate.pack(fill="x", padx=8, pady=(0, 6))


        # =====================================================================
        # [열 2] 결과 패널 (생성 코드 에디터)
        # =====================================================================
        col2_f = ctk.CTkFrame(body, corner_radius=6)
        col2_f.grid(row=0, column=2, padx=(3, 6), pady=6, sticky="nsew")

        r_head = ctk.CTkFrame(col2_f, fg_color="transparent")
        r_head.pack(fill="x", padx=8, pady=(6, 4))
        ctk.CTkLabel(r_head, text="생성 코드", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")

        self.txt_result_code = ctk.CTkTextbox(
            col2_f, font=ctk.CTkFont(family="Consolas", size=12), fg_color="#181818"
        )
        self.txt_result_code.pack(fill="both", expand=True, padx=8, pady=4)

        b_bar = ctk.CTkFrame(col2_f, fg_color="transparent")
        b_bar.pack(fill="x", padx=8, pady=(4, 8))

        btn_insert = ctk.CTkButton(
            b_bar, text="스크립트로 전송", width=120, height=36,
            fg_color="#2e7d32", hover_color="#1b5e20", font=ctk.CTkFont(size=11, weight="bold"),
            command=self._do_insert_editor
        )
        btn_insert.pack(side="left", fill="x", expand=True, padx=(0, 4))

        btn_add_bot = ctk.CTkButton(
            b_bar, text="봇 등록", width=80, height=36,
            fg_color="#6a1b9a", hover_color="#4a148c", font=ctk.CTkFont(size=11, weight="bold"),
            command=self._do_add_bot
        )
        btn_add_bot.pack(side="left", fill="x", expand=True, padx=4)

        btn_copy = ctk.CTkButton(
            b_bar, text="복사", width=60, height=36,
            fg_color="#444444", hover_color="#333333", font=ctk.CTkFont(size=11), command=self._copy_result
        )
        btn_copy.pack(side="right", padx=(4, 0))

        self._update_project_bar()

    def _refresh_window_list(self):
        try:
            wins = WindowEnumerator.get_open_windows()
            self.open_windows_list = wins
            titles = [t for _, t in wins]
            if not titles:
                titles = ["(열려있는 활성 창 없음)"]
            self.cbo_windows.configure(values=titles)
            if titles:
                default_choice = titles[0]
                for t in titles:
                    if "[웹]" in t:
                        default_choice = t
                        break
                self.cbo_windows.set(default_choice)
        except Exception as e:
            self.cbo_windows.configure(values=[f"(오류: {e})"])

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
        self._refresh_target_urls()

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
    # [실시간 DOM/UIA 수집 - 깜빡임 0%, 세션 100% 보존]
    # =========================================================================
    def _start_harvest_dom(self):
        url = self.cbo_target_url.get().strip()
        selected_win_title = self.cbo_windows.get()
        chosen_browser = "Chrome"

        # 선택된 창의 HWND 탐색
        target_hwnd = 0
        for h, t in self.open_windows_list:
            if t == selected_win_title:
                target_hwnd = h
                break

        if not url and not selected_win_title:
            messagebox.showwarning("입력 확인", "대상 웹 URL을 입력하거나 대상 창을 선택하십시오.")
            return

        self._save_all_configs()
        self._refresh_target_urls()
        self.btn_harvest_dom.configure(text="수집 중...", state="disabled")
        self.lbl_dom_status.configure(text="객체 수집 중...", text_color="#ffb74d")

        def _worker():
            try:
                info = DOMHarvester.check_cdp_available()
                self._safe_after(0, lambda i=info: self._on_cdp_check_done(i))
                res = DOMHarvester.harvest_live_dom(
                    url=url,
                    hwnd=target_hwnd,
                    window_title=selected_win_title,
                    browser_type=chosen_browser,
                    timeout_sec=15
                )
                self._safe_after(0, lambda r=res: self._on_harvest_success(r))
            except Exception as e:
                self._safe_after(0, lambda err=str(e): self._on_harvest_error(err))

        threading.Thread(target=_worker, daemon=True).start()

    # =========================================================================
    # CDP 상태 확인 및 Chrome/Edge CDP 모드 시작
    # =========================================================================
    def _check_cdp_status(self):
        """CDP 연결 가능 여부 확인 및 상태 라벨 갱신"""
        self.lbl_cdp_status.configure(text="● CDP 확인 중...", text_color="#ffb74d")
        self.update_idletasks()

        def _worker():
            info = DOMHarvester.check_cdp_available()
            self._safe_after(0, lambda i=info: self._on_cdp_check_done(i))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_cdp_check_done(self, info: dict):
        if info.get("ok"):
            port = info.get("port", 0)
            pages = info.get("page_count", 0)
            self.lbl_cdp_status.configure(
                text=f"● CDP 연결됨 (포트 {port}, 탭 {pages}개)",
                text_color="#00e676"
            )
        else:
            self.lbl_cdp_status.configure(
                text=f"● CDP 미연결 — CDP 모드 Chrome 시작 필요",
                text_color="#ff5252"
            )

    def _create_cdp_shortcut(self, browser: str = "chrome"):
        """
        Chrome/Edge CDP 전용 바탕화면 바로가기 생성.

        수정 이력:
          v2: WshShortcut.Save 한글 파일명 저장 실패(0x80070003) 해결
              - 파일명을 ASCII 전용으로 변경 (Chrome_CDP.lnk / Edge_CDP.lnk)
              - Desktop 경로를 ctypes SHGetFolderPath로 안전하게 획득
        """
        import shutil
        import ctypes

        LOCAL = os.environ.get("LOCALAPPDATA", "")

        # Desktop 경로: ctypes SHGetFolderPath (CSIDL_DESKTOP=0) — 한글 경로 안전
        try:
            buf = ctypes.create_unicode_buffer(260)
            ctypes.windll.shell32.SHGetFolderPathW(0, 0, 0, 0, buf)
            DESKTOP = buf.value
        except Exception:
            DESKTOP = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")

        if browser == "chrome":
            exe_candidates = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.join(LOCAL, r"Google\Chrome\Application\chrome.exe"),
            ]
            src_profile = os.path.join(LOCAL, r"Google\Chrome\User Data")
            cdp_profile = os.path.join(LOCAL, r"Google\Chrome\User Data_CDP")
            port    = 9222
            label   = "Chrome"
            sc_name = "Chrome_CDP.lnk"   # ASCII 파일명 (한글 실패 방지)
            bat_name = "Chrome_CDP.bat"
        else:
            exe_candidates = [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                os.path.join(LOCAL, r"Microsoft\Edge\Application\msedge.exe"),
            ]
            src_profile = os.path.join(LOCAL, r"Microsoft\Edge\User Data")
            cdp_profile = os.path.join(LOCAL, r"Microsoft\Edge\User Data_CDP")
            port    = 9223
            label   = "Edge"
            sc_name = "Edge_CDP.lnk"
            bat_name = "Edge_CDP.bat"

        exe = next((p for p in exe_candidates if os.path.exists(p)), None)
        if not exe:
            messagebox.showerror("경로 오류", f"{label} 실행 파일을 찾을 수 없습니다.")
            return

        # CDP 전용 프로필 폴더 생성 (Default 폴더만 복사, 캐시 제외)
        try:
            if not os.path.exists(cdp_profile):
                os.makedirs(cdp_profile, exist_ok=True)
            dst_default = os.path.join(cdp_profile, "Default")
            src_default = os.path.join(src_profile, "Default")
            if os.path.exists(src_default) and not os.path.exists(dst_default):
                shutil.copytree(
                    src_default, dst_default,
                    ignore=shutil.ignore_patterns(
                        "*.log", "*.tmp", "Cache", "Code Cache", "GPUCache",
                        "Media Cache", "ShaderCache", "Service Worker", "CacheStorage",
                        "blob_storage", "databases", "IndexedDB",
                    )
                )
        except Exception:
            pass  # 복사 실패 시 빈 프로필로 계속 (로그인만 다시 하면 됨)

        lnk_path = os.path.join(DESKTOP, sc_name)
        args_str = (
            f"--remote-debugging-port={port} "
            f"--user-data-dir=\"{cdp_profile}\" "
            f"--no-first-run --no-default-browser-check"
        )

        created_file = sc_name
        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            sc = shell.CreateShortCut(lnk_path)
            sc.Targetpath       = exe
            sc.Arguments        = args_str
            sc.WorkingDirectory = os.path.dirname(exe)
            sc.IconLocation     = exe + ",0"
            # Description은 ASCII만 — 한글 포함 시 일부 환경 저장 실패
            sc.Description = f"{label} CDP Mode Port {port}"
            sc.save()

        except ImportError:
            # pywin32 없으면 .bat Fallback
            bat_path = os.path.join(DESKTOP, bat_name)
            with open(bat_path, "w", encoding="utf-8") as fh:
                fh.write("@echo off\n")
                fh.write(f'start "" "{exe}" {args_str}\n')
            created_file = bat_name

        except Exception as ex:
            # .lnk 실패 시 .bat 자동 Fallback
            try:
                bat_path = os.path.join(DESKTOP, bat_name)
                with open(bat_path, "w", encoding="utf-8") as fh:
                    fh.write("@echo off\n")
                    fh.write(f'start "" "{exe}" {args_str}\n')
                created_file = bat_name
            except Exception as ex2:
                messagebox.showerror("생성 실패", f"바로가기 생성 오류:\n{ex}\n\n.bat 생성도 실패:\n{ex2}")
                return

        msg = (
            f"바탕화면에 [{created_file}]가 생성됐습니다.\n\n"
            f"[사용 방법]\n"
            f"1. 현재 열린 {label} 창을 모두 닫으십시오\n"
            f"2. 바탕화면의 [{created_file}]로 {label} 시작\n"
            f"3. 사이트 로그인 후 RPA 도구에서 [연결 확인] 클릭\n"
            f"4. 초록 표시 확인 후 DOM 수집 — select 드롭다운 포함 완벽 수집"
        )
        messagebox.showinfo("바로가기 생성 완료", msg)

    def _clear_dom_filter(self):
        """객체 검색 필터 초기화"""
        self.ent_dom_filter.delete(0, "end")
        self._filter_dom_catalog()

    def _filter_dom_catalog(self):
        """검색어 기반 DOM 객체 목록 실시간 필터링 및 렌더링"""
        query = self.ent_dom_filter.get().strip().lower()
        self._render_dom_catalog_view(query)

    def _render_dom_catalog_view(self, query: str = ""):
        """현재 수집된 DOM 카탈로그를 검색어(query)에 맞게 렌더링"""
        catalog = self.current_catalog or {}

        for sf in self.scroll_frames.values():
            for w in sf.winfo_children():
                w.destroy()

        def _matches(item: dict) -> bool:
            if not query:
                return True
            fields = [
                item.get("label", ""),
                item.get("text", ""),
                item.get("path", ""),
                item.get("selector", ""),
                item.get("type", ""),
                item.get("element_type", ""),
                item.get("playwrightCode", ""),
                " ".join(item.get("options", [])) if isinstance(item.get("options"), list) else ""
            ]
            combined = " ".join(fields).lower()
            return query in combined

        cat_defs = [
            ("inputs", self.tab_inputs, "입력창", "[입력]"),
            ("buttons", self.tab_buttons, "버튼", "[버튼]"),
            ("selects", self.tab_selects, "드롭다운", "[선택]"),
            ("checks_radios", self.tab_checks, "체크/라디오", "[체크]"),
            ("grids", self.tab_grids, "그리드", "[그리드]"),
            ("links", self.tab_links, "링크", "[링크]"),
        ]

        for key, tab_obj, title_prefix, icon in cat_defs:
            all_items = catalog.get(key, [])
            filtered_items = [itm for itm in all_items if _matches(itm)]
            sf = self.scroll_frames[key]

            # 탭 타이틀 카운트 표시 (필터 시 "버튼 (3/113)" 또는 "버튼 (113)")
            if query and len(filtered_items) != len(all_items):
                tab_title = f"{title_prefix} ({len(filtered_items)}/{len(all_items)})"
            else:
                tab_title = f"{title_prefix} ({len(all_items)})"
            self._set_tab_title(tab_obj, tab_title)

            if not filtered_items and all_items and query:
                ctk.CTkLabel(
                    sf, text=f"'{query}' 일치 항목 없음",
                    font=ctk.CTkFont(size=11), text_color="#666666"
                ).pack(pady=14)
            else:
                for itm in filtered_items:
                    self._render_element_card(sf, itm, icon=icon)

    def _on_harvest_success(self, res: Dict[str, Any]):
        self.btn_harvest_dom.configure(text="DOM 수집", state="normal")
        catalog = res.get("catalog", {})
        self.current_catalog = catalog
        total_count = res.get("count", 0)
        sec = res.get("elapsed_sec", 0)

        self.lbl_dom_status.configure(
            text=f"조작 객체 목록 ({total_count}개 수집됨, {sec}초)",
            text_color="#81c784"
        )
        self._filter_dom_catalog()

    def _set_tab_title(self, tab, new_title):
        try:
            for btn in self.tabview_dom._segmented_button._buttons_dict.values():
                if btn.cget("text").split(" ")[0] == new_title.split(" ")[0]:
                    btn.configure(text=new_title)
                    break
        except Exception:
            pass

    def _render_element_card(self, parent_frame, itm: Dict[str, Any], icon: str = ""):
        name = itm.get("label") or itm.get("text") or itm.get("type") or "알수없음"
        path = itm.get("path") or ""
        raw_html = itm.get("html") or ""
        sel = itm.get("selector") or ""
        code = itm.get("playwrightCode") or ""

        card = ctk.CTkFrame(parent_frame, corner_radius=6, fg_color="#2b2b2b", height=34)
        card.pack(fill="x", pady=2, padx=2)
        card.pack_propagate(False)

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="both", expand=True, padx=4, pady=0)

        # 1. 우측 액션 버튼들을 먼저 pack(side='right')하여 공간 무조건 확보
        is_kept = any(k.get("selector") == sel for k in getattr(self, "keep_list", []))
        btn_keep = ctk.CTkButton(
            row, text="Keep ★", width=62, height=22, font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#c48800" if is_kept else "#7b5800",
            hover_color="#dba000" if is_kept else "#a07000",
            command=lambda i=itm: self._on_keep_item(i)
        )
        btn_keep.pack(side="right", padx=(2, 0))

        if raw_html:
            btn_html = ctk.CTkButton(
                row, text="HTML", width=46, height=22, font=ctk.CTkFont(size=11),
                fg_color="#444444", hover_color="#333333",
                command=lambda: self._show_element_html(name, raw_html, sel)
            )
            btn_html.pack(side="right", padx=2)

        # 2. 좌측 요소명 고정 폭
        disp_name = name if len(name) <= 12 else name[:10] + ".."
        lbl_name = ctk.CTkLabel(row, text=f"{icon} {disp_name}", width=110, font=ctk.CTkFont(size=11, weight="bold"), text_color="#ffffff", anchor="w")
        lbl_name.pack(side="left", padx=(0, 4))

        # 3. 경로 고정 폭
        disp_path = path if len(path) <= 14 else path[:12] + ".."
        if disp_path:
            lbl_path = ctk.CTkLabel(row, text=f"경로: {disp_path}", width=100, font=ctk.CTkFont(size=11), text_color="#b0bec5", anchor="w")
            lbl_path.pack(side="left", padx=2)

        # 4. 남은 공간에 셀렉터 표출 (자동 확장/축소)
        lbl_sel = ctk.CTkLabel(row, text=sel, font=ctk.CTkFont(family="Consolas", size=11), text_color="#64b5f6", anchor="w")
        lbl_sel.pack(side="left", fill="x", expand=True, padx=4)

    def _show_element_html(self, name: str, raw_html: str, sel: str):
        """요소의 실제 HTML 코드 및 세부 속성을 팝업으로 표출"""
        pop = ctk.CTkToplevel(self)
        pop.title(f"HTML 상세 - {name}")
        pop.geometry("680x420")
        pop.attributes("-topmost", True)

        head = ctk.CTkFrame(pop, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(head, text=f"요소: {name}", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")

        sel_bar = ctk.CTkFrame(pop, fg_color="transparent")
        sel_bar.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(sel_bar, text=f"셀렉터: {sel}", font=ctk.CTkFont(family="Consolas", size=12), text_color="#64b5f6").pack(side="left")

        txt_box = ctk.CTkTextbox(pop, font=ctk.CTkFont(family="Consolas", size=12), fg_color="#181818")
        txt_box.pack(fill="both", expand=True, padx=12, pady=8)
        txt_box.insert("1.0", raw_html)

        btn_bar = ctk.CTkFrame(pop, fg_color="transparent")
        btn_bar.pack(fill="x", padx=12, pady=(0, 10))

        def _copy():
            self.clipboard_clear()
            self.clipboard_append(raw_html)
            messagebox.showinfo("복사 완료", "HTML 코드가 클립보드에 복사되었습니다.")

        ctk.CTkButton(btn_bar, text="HTML 복사", width=100, height=32, font=ctk.CTkFont(size=12), fg_color="#1f6aa5", command=_copy).pack(side="left")
        ctk.CTkButton(btn_bar, text="닫기", width=80, height=32, font=ctk.CTkFont(size=12), fg_color="#444444", command=pop.destroy).pack(side="right")

    # ── Keep 기능 ─────────────────────────────────────────────────────────────

    def _make_var_name(self, itm: Dict[str, Any]) -> str:
        """아이템으로부터 타입_레이블 형식의 변수명 자동 생성"""
        import re
        raw_type = itm.get("type") or "요소"
        elem_type = (raw_type
                     .replace("input", "입력")
                     .replace("button", "버튼")
                     .replace("select", "드롭다운")
                     .replace("link", "링크"))
        label = itm.get("label") or itm.get("text") or "항목"
        label_clean = re.sub(r"[^가-힣a-zA-Z0-9]", "", label)[:10]
        type_clean = re.sub(r"[^가-힣a-zA-Z0-9]", "", elem_type)[:4]
        base = f"{type_clean}_{label_clean}" if label_clean else type_clean
        name = base
        existing = [k.get("var_name") for k in self.keep_list]
        count = 1
        while name in existing:
            name = f"{base}_{count}"
            count += 1
        return name

    def _on_keep_item(self, itm: Dict[str, Any]):
        """요소 Keep 목록에 추가 (이미 있으면 제거)"""
        sel = itm.get("selector") or ""
        if not sel:
            return
        existing_idx = next(
            (i for i, k in enumerate(self.keep_list) if k.get("selector") == sel), -1
        )
        if existing_idx >= 0:
            removed = self.keep_list.pop(existing_idx)
            if getattr(self, "db", None) and removed.get("id"):
                try:
                    self.db.delete_keep_element(removed["id"])
                except Exception as e:
                    print(f"DB Keep 삭제 에러: {e}")
        else:
            vname = self._make_var_name(itm)
            new_item = {
                "var_name": vname,
                "label": itm.get("label") or itm.get("text") or "알수없음",
                "selector": sel,
                "element_type": itm.get("type") or "element",
                "path": itm.get("path") or "",
                "html": itm.get("html") or "",
                "options": itm.get("options") or [],
                "keep_type": "element"
            }
            if getattr(self, "db", None) and getattr(self, "current_project", None):
                try:
                    eid = self.db.save_keep_element(
                        project_id=self.current_project["id"],
                        target_id=self.current_target["id"] if getattr(self, "current_target", None) else None,
                        var_name=vname,
                        keep_type="element",
                        selector=sel,
                        label=new_item["label"],
                        element_type=itm.get("type") or "element",
                        path=new_item["path"]
                    )
                    new_item["id"] = eid
                except Exception as e:
                    print(f"DB Keep 에러: {e}")
            self.keep_list.append(new_item)
        self._render_keep_list()
        self._render_var_chips()

    def _render_keep_list(self):
        """Keep 목록 패널 갱신"""
        for w in self.frm_keep_panel.winfo_children():
            w.destroy()

        if not self.keep_list:
            ctk.CTkLabel(
                self.frm_keep_panel,
                text="Keep된 항목이 없습니다. 객체 카드의 [Keep ★] 버튼을 누르세요.",
                font=ctk.CTkFont(size=11), text_color="#555555"
            ).pack(pady=10)
            return

        for idx, item in enumerate(self.keep_list):
            ktype = item.get("keep_type", "element")
            row = ctk.CTkFrame(self.frm_keep_panel, fg_color="#252525", corner_radius=4, cursor="hand2")
            row.pack(fill="x", pady=2, padx=2)

            vname = item["var_name"]
            # 배지 및 색상: URL(시안블루), Data(연초록), File Array(라벤더퍼플), Element(골드노랑)
            if ktype == "target_url":
                badge_prefix = "[URL] "
                color_var = "#29b6f6"
            elif ktype == "data_column":
                badge_prefix = "[DATA] "
                color_var = "#81c784"
            elif ktype == "file_array":
                badge_prefix = "[FILES] "
                color_var = "#ce93d8"
            else:
                badge_prefix = ""
                color_var = "#ffd54f"

            # 1. 우측 액션 버튼들을 side="right"로 먼저 패킹 (버튼 잘림 방지)
            def _del(i=idx):
                removed = self.keep_list.pop(i)
                if getattr(self, "db", None) and removed.get("id"):
                    try:
                        if removed.get("keep_type") == "target_url":
                            self.db.delete_target(removed["id"])
                            self._refresh_target_urls()
                        else:
                            self.db.delete_keep_element(removed["id"])
                    except Exception as e:
                        print(f"DB 삭제 에러: {e}")
                self._render_keep_list()
            ctk.CTkButton(
                row, text="✕", width=26, height=22, font=ctk.CTkFont(size=11),
                fg_color="#5a2d2d", hover_color="#7a1a1a", command=_del
            ).pack(side="right", padx=(2, 4))

            def _rename(i=idx):
                self._rename_keep_item(i)
            ctk.CTkButton(
                row, text="✏", width=26, height=22, font=ctk.CTkFont(size=11),
                fg_color="#333333", hover_color="#444444", command=_rename
            ).pack(side="right", padx=2)

            def _action_menu(it=item):
                self._show_element_action_popup(it)
            ctk.CTkButton(
                row, text="조작 ▾", width=52, height=22, font=ctk.CTkFont(size=11),
                fg_color="#1a3a5c", hover_color="#1f6aa5", command=_action_menu
            ).pack(side="right", padx=2)

            # 2. 좌측 변수명 및 설명 레이블 패킹
            lbl_var = ctk.CTkLabel(
                row, text=f"  {badge_prefix}{{{vname}}}",
                font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
                text_color=color_var, anchor="w", cursor="hand2"
            )
            lbl_var.pack(side="left", fill="x", expand=True)

            # 더블클릭 시 프롬프트 에디터에 {변수명} 삽입 및 노란색 하이라이트
            row.bind("<Double-Button-1>", lambda e, v=vname: self._on_keep_item_dblclick(v))
            lbl_var.bind("<Double-Button-1>", lambda e, v=vname: self._on_keep_item_dblclick(v))

            if item.get("path"):
                lbl_path = ctk.CTkLabel(
                    row, text=item["path"][:26],
                    font=ctk.CTkFont(size=11), text_color="#888888", cursor="hand2"
                )
                lbl_path.pack(side="left", padx=(0, 4))
                lbl_path.bind("<Double-Button-1>", lambda e, v=vname: self._on_keep_item_dblclick(v))

    def _on_keep_item_dblclick(self, var_name: str):
        """Keep 아이템 더블클릭 시 프롬프트 에디터에 {var_name} 삽입 후 노란색 하이라이트"""
        token = f"{{{var_name}}}"
        try:
            self.txt_prompt.insert("insert", f" {token} ")
            self.txt_prompt.focus_set()
            self._highlight_keep_tokens()
        except Exception as e:
            print(f"Keep 토큰 삽입 오류: {e}")

    def _init_prompt_highlight(self):
        """프롬프트 에디터 텍스트 태그 설정 (URL/DOM/DATA/FILE/ACTION 5단 컬러 하이라이트)"""
        try:
            tb = self.txt_prompt._textbox
            # 🌐 URL (시안 블루)
            tb.tag_config("token_url", foreground="#29b6f6", font=("Consolas", 12, "bold"))
            # 🎯 DOM Element (골드 옐로우)
            tb.tag_config("token_elem", foreground="#ffd54f", font=("Consolas", 12, "bold"))
            # 📊 Data Column (에메랄드 그린)
            tb.tag_config("token_data", foreground="#81c784", font=("Consolas", 12, "bold"))
            # 📁 File Array (라벤더 퍼플)
            tb.tag_config("token_file", foreground="#ce93d8", font=("Consolas", 12, "bold"))
            # ⚡ Action Methods (연보라)
            tb.tag_config("token_action", foreground="#e1bee7", font=("Consolas", 12, "bold"))

            tb.bind("<KeyRelease>", self._highlight_keep_tokens)
            tb.bind("<<Paste>>", lambda e: self.after(50, self._highlight_keep_tokens))
            self._highlight_keep_tokens()
        except Exception as e:
            print(f"하이라이트 설정 실패: {e}")

    def _highlight_keep_tokens(self, event=None):
        """프롬프트 에디터 내 {변수명} 및 표준 액션 동사를 5W1H 멀티 컬러로 실시간 하이라이트"""
        try:
            tb = self.txt_prompt._textbox
            for tag in ["token_url", "token_elem", "token_data", "token_file", "token_action", "keep_token"]:
                tb.tag_remove(tag, "1.0", "end")

            content = tb.get("1.0", "end")

            # 1. Keep 목록 매핑 생성
            keep_type_map = {itm.get("var_name"): itm.get("keep_type", "element") for itm in self.keep_list}

            # 2. {변수명} 토큰 매칭
            for match in re.finditer(r"\{[^{}]+\}", content):
                vname = match.group(0)[1:-1].strip()
                ktype = keep_type_map.get(vname, "")
                if not ktype:
                    if vname.startswith("url_"):
                        ktype = "target_url"
                    elif vname.startswith("row.") or vname.startswith("col_"):
                        ktype = "data_column"
                    elif "file" in vname or "files" in vname:
                        ktype = "file_array"
                    else:
                        ktype = "element"

                tag_name = (
                    "token_url" if ktype == "target_url"
                    else "token_data" if ktype == "data_column"
                    else "token_file" if ktype == "file_array"
                    else "token_elem"
                )

                start_idx = f"1.0 + {match.start()} chars"
                end_idx = f"1.0 + {match.end()} chars"
                tb.tag_add(tag_name, start_idx, end_idx)

            # 3. 표준 액션 동사 하이라이트
            action_words = ["접속", "이동", "클릭", "더블클릭", "입력", "지우기", "선택", "체크", "수집", "대기", "첨부", "업로드", "다운로드"]
            for act in action_words:
                for match in re.finditer(rf"\b{re.escape(act)}\b", content):
                    start_idx = f"1.0 + {match.start()} chars"
                    end_idx = f"1.0 + {match.end()} chars"
                    tb.tag_add("token_action", start_idx, end_idx)
        except Exception:
            pass

    def _rename_keep_item(self, idx: int):
        """Keep 아이템 변수명 수정 팝업 (DB 즉시 영구 저장)"""
        item = self.keep_list[idx]
        pop = ctk.CTkToplevel(self)
        pop.title("변수명 수정")
        pop.geometry("360x130")
        pop.attributes("-topmost", True)
        ctk.CTkLabel(pop, text="변수명:", font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(14, 4))
        ent = ctk.CTkEntry(pop, font=ctk.CTkFont(family="Consolas", size=13), width=280)
        ent.insert(0, item["var_name"])
        ent.pack()
        ent.focus_set()

        def _apply():
            new_name = ent.get().strip()
            if new_name:
                item["var_name"] = new_name
                # DB 업데이트 (PK ID 기반 순수 UPDATE 수행, 절대 INSERT 하지 않음)
                if getattr(self, "db", None) and item.get("id"):
                    try:
                        rec_id = item["id"]
                        ktype = item.get("keep_type", "element")
                        # 1. rpa_keep_elements 테이블 업데이트
                        self.db.update_keep_element_var_name(rec_id, new_name)
                        # 2. target_url인 경우 rpa_targets 라벨도 함께 업데이트
                        if ktype == "target_url":
                            self.db.update_target(rec_id, label=new_name)
                            item["label"] = new_name
                            self._refresh_target_urls()
                    except Exception as e:
                        print(f"DB Keep 수정 에러: {e}")
                self._render_keep_list()
                self._highlight_keep_tokens()
            pop.destroy()

        ent.bind("<Return>", lambda e: _apply())
        ctk.CTkButton(pop, text="적용", width=100, height=30, command=_apply).pack(pady=10)

    def _clear_keep_list(self):
        """Keep 목록 전체 삭제"""
        for itm in self.keep_list:
            if getattr(self, "db", None) and itm.get("id"):
                try:
                    self.db.delete_keep_element(itm["id"])
                except Exception:
                    pass
        self.keep_list.clear()
        self._render_keep_list()
        self._render_var_chips()

    # ── 요소 타입 → 가능한 액션 매핑 ─────────────────────────────────────────
    _ELEM_ACTIONS = {
        # element_type 키워드 → [(표시 라벨, 삽입 문장 템플릿)]
        "url": [
            ("페이지 이동", "{var} 주소로 브라우저 이동"),
            ("새 탭에서 열기", "새 탭을 열고 {var}로 접속"),
            ("URL 일치 확인", "현재 페이지가 {var}인지 확인"),
        ],
        "input":    [
            ("값 입력",         "{var}에 '{값}'을 입력"),
            ("내용 지우고 입력", "{var}의 내용을 지우고 '{값}'을 입력"),
            ("내용 지우기",     "{var}의 내용을 지우기"),
            ("Enter 키 입력",   "{var}에서 Enter 키를 누르기"),
            ("현재 값 확인",    "{var}의 현재 입력값을 확인"),
        ],
        "textarea": [
            ("내용 입력",   "{var}에 '{내용}'을 입력"),
            ("내용 지우기", "{var}의 내용을 모두 지우기"),
        ],
        "button": [
            ("클릭",       "{var}을 클릭"),
            ("더블클릭",   "{var}을 더블클릭"),
            ("마우스 오버","{var}에 마우스를 올려두기"),
            ("활성화 확인","{var}이 클릭 가능한 상태인지 확인"),
        ],
        "select": [
            ("옵션 선택",   "{var}에서 '{옵션}'을 선택"),
            ("현재 값 확인","{var}의 현재 선택값을 확인"),
            ("전체 옵션 수집", "{var}의 모든 옵션 목록을 수집"),
        ],
        "checkbox": [
            ("체크",       "{var}을 체크"),
            ("체크 해제",  "{var}의 체크를 해제"),
            ("상태 확인",  "{var}의 체크 상태를 확인"),
        ],
        "link": [
            ("클릭",       "{var}을 클릭"),
            ("href 확인",  "{var}의 링크 주소를 확인"),
        ],
        "table": [
            ("데이터 추출", "{var}의 전체 데이터를 추출"),
            ("행 수 확인",  "{var}의 행 수를 확인"),
            ("특정 행 클릭","{var}에서 '{키워드}'가 포함된 행을 클릭"),
        ],
        "span":  [("텍스트 확인", "{var}의 텍스트를 확인"), ("표시 대기", "{var}가 화면에 나타날 때까지 대기")],
        "div":   [("텍스트 확인", "{var}의 텍스트를 확인"), ("표시 대기", "{var}가 화면에 나타날 때까지 대기")],
        "label": [("텍스트 확인", "{var}의 라벨 텍스트를 확인")],
        "_default": [
            ("클릭",         "{var}을 클릭"),
            ("텍스트 확인",  "{var}의 텍스트를 확인"),
            ("표시 대기",    "{var}가 화면에 나타날 때까지 대기"),
            ("사라질 때 대기", "{var}가 화면에서 사라질 때까지 대기"),
        ],
    }

    def _get_actions_for(self, element_type: str):
        """element_type에 맞는 액션 목록 반환 (text, password, email 등 입력 타입 완벽 매핑)"""
        t = (element_type or "").lower().strip()

        # 1. 텍스트/패스워드/숫자 등 입력창 계열
        if t in ("input", "text", "password", "number", "email", "tel", "search", "date") or "input" in t or "text" in t or "pass" in t:
            return self._ELEM_ACTIONS["input"]

        # 2. 텍스트 영역
        if "textarea" in t:
            return self._ELEM_ACTIONS["textarea"]

        # 3. 버튼 계열
        if "button" in t or "btn" in t or t in ("submit", "reset"):
            return self._ELEM_ACTIONS["button"]

        # 4. 드롭다운/셀렉트 계열
        if "select" in t or "combo" in t or "dropdown" in t:
            return self._ELEM_ACTIONS["select"]

        # 5. 체크박스 / 라디오
        if "check" in t or "radio" in t:
            return self._ELEM_ACTIONS["checkbox"]

        # 6. 링크
        if "link" in t or t == "a":
            return self._ELEM_ACTIONS["link"]

        # 7. 테이블 / 그리드
        if "table" in t or "grid" in t or "tr" in t or "td" in t:
            return self._ELEM_ACTIONS["table"]

        for key in self._ELEM_ACTIONS:
            if key != "_default" and key in t:
                return self._ELEM_ACTIONS[key]
        return self._ELEM_ACTIONS["_default"]

    def _render_var_chips(self):
        """하위 호환 유지 (칩 바 제거됨)"""
        pass

    def _render_data_chips(self):
        """하위 호환 유지 (칩 바 제거됨)"""
        pass

    def _show_element_action_popup(self, item: dict):
        """Keep 아이템의 타입에 따른 스마트 액션 팝업 표시 및 프롬프트 문장 자동 조립"""
        var_name = item.get("var_name", "")
        ktype = item.get("keep_type", "element")

        if ktype == "target_url":
            actions = [
                ("페이지 이동", "{var} 주소로 브라우저 이동"),
                ("새 탭에서 열기", "새 탭을 열고 {var}로 접속"),
                ("URL 일치 확인", "현재 페이지가 {var}인지 확인"),
                ("단순 변수 삽입", "{var}")
            ]
            type_label = "URL"
            header_color = "#29b6f6"
        elif ktype == "data_column":
            actions = [
                ("요소에 입력", "{var} 값을 입력 대상에 입력"),
                ("값 비교/검증", "{var} 값과 화면의 값을 비교"),
                ("조건 분기", "{var} 값이 특정 조건이면"),
                ("단순 변수 삽입", "{var}")
            ]
            type_label = f"Data ({item.get('data_type', 'str')})"
            header_color = "#81c784"
        elif ktype == "file_array":
            actions = [
                ("파일 순회 처리", "{var} 의 각 파일을 순서대로 처리"),
                ("파일명 입력", "{var} 의 파일명을 입력창에 입력"),
                ("파일 첨부/업로드", "{var} 의 파일을 첨부창에 업로드"),
                ("단순 변수 삽입", "{var}")
            ]
            type_label = "Files Array"
            header_color = "#ce93d8"
        else:
            raw_etype = item.get("element_type", "")
            etype = (raw_etype or "DOM 요소").lower()
            type_label = raw_etype or "DOM 요소"
            header_color = "#ffd54f"

            # 1. 셀렉트/드롭다운인 경우 하위 <option> 목록을 동적으로 추출하여 실제 옵션 선택 메뉴 추가
            if "select" in etype or "dropdown" in etype or "combo" in etype:
                opts = list(item.get("options") or [])
                if not opts and item.get("html"):
                    try:
                        raw_opts = re.findall(r"<option[^>]*>\s*([^<]+?)\s*</option>", item["html"], re.IGNORECASE)
                        opts = [o.strip() for o in raw_opts if o.strip() and o.strip() not in ("선택", "선택하세요", "전체", "== 선택 ==")]
                    except Exception:
                        pass

                if opts:
                    actions = []
                    for opt in opts[:10]:
                        actions.append((f"선택: {opt}", f"{{{var_name}}}에서 '{opt}'을 선택"))
                    actions.append(("직접 옵션 입력", f"{{{var_name}}}에서 '{{옵션}}'을 선택"))
                    actions.append(("현재 값 확인", f"{{{var_name}}}의 현재 선택값을 확인"))
                    actions.append(("전체 옵션 수집", f"{{{var_name}}}의 모든 옵션 목록을 수집"))
                else:
                    actions = self._get_actions_for(raw_etype)

            # 2. 입력창(input/textarea/text/password 등)인 경우 Keep 데이터 변수({row.컬럼}, {file_list}) 주입 메뉴 1순위 노출
            elif (
                etype in ("input", "text", "password", "number", "email", "tel", "search", "date")
                or "input" in etype or "text" in etype or "pass" in etype or "textarea" in etype
            ):
                actions = []
                data_vars = [k for k in self.keep_list if k.get("keep_type") in ("data_column", "file_array")]
                for dvar in data_vars:
                    dvname = dvar.get("var_name", "")
                    if dvar.get("keep_type") == "data_column":
                        actions.append((f"변수 주입: {{{dvname}}}", f"{{{var_name}}}에 {{{dvname}}} 값을 입력"))
                    elif dvar.get("keep_type") == "file_array":
                        actions.append((f"파일명 주입: {{{dvname}}}", f"{{{var_name}}}에 {{{dvname}}} 의 파일명을 입력"))

                # 기본 입력 액션들 추가
                actions.append(("직접 값 입력", f"{{{var_name}}}에 '{{값}}'을 입력"))
                actions.append(("내용 지우고 입력", f"{{{var_name}}}의 내용을 지우고 '{{값}}'을 입력"))
                actions.append(("내용 지우기", f"{{{var_name}}}의 내용을 지우기"))
                actions.append(("Enter 키 입력", f"{{{var_name}}}에서 Enter 키를 누르기"))
                actions.append(("현재 값 확인", f"{{{var_name}}}의 현재 입력값을 확인"))
            else:
                actions = self._get_actions_for(raw_etype)

        pop = ctk.CTkToplevel(self)
        pop.overrideredirect(True)          # 제목 표시줄 없음 → 컨텍스트 메뉴 느낌
        pop.attributes("-topmost", True)
        pop.configure(fg_color="#1e1e1e")

        # 팝업 위치: 마우스 커서 근방
        try:
            x = self.winfo_pointerx() - 10
            y = self.winfo_pointery() + 5
        except Exception:
            x, y = 400, 400
        pop.geometry(f"+{x}+{y}")

        # 헤더: 요소 타입 표시
        hdr = ctk.CTkFrame(pop, fg_color="#111111", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(
            hdr,
            text=f"  {{{var_name}}}  ·  {type_label}",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color=header_color, anchor="w"
        ).pack(side="left", padx=8, pady=6)
        ctk.CTkButton(
            hdr, text="✕", width=24, height=24, font=ctk.CTkFont(size=11),
            fg_color="transparent", hover_color="#333333",
            command=pop.destroy
        ).pack(side="right", padx=4)

        # 액션 목록 스크롤 가능 컨테이너 (항목 많을 때 자동 스크롤)
        use_scroll = len(actions) > 7
        if use_scroll:
            content_f = ctk.CTkScrollableFrame(pop, fg_color="transparent", width=340, height=360)
        else:
            content_f = ctk.CTkFrame(pop, fg_color="transparent")
        content_f.pack(fill="both", expand=True, padx=2, pady=2)

        # 액션 버튼 목록
        for label, template in actions:
            phrase = template.replace("{var}", f"{{{var_name}}}")

            def _pick(ph=phrase, p=pop):
                self._insert_phrase(ph)
                p.destroy()

            # 항목별 강조 텍스트 색상
            if "변수 주입" in label:
                btn_txt_color = "#81c784"
                btn_font_w = "bold"
            elif "파일명 주입" in label:
                btn_txt_color = "#ce93d8"
                btn_font_w = "bold"
            elif "선택:" in label:
                btn_txt_color = "#64b5f6"
                btn_font_w = "bold"
            else:
                btn_txt_color = "#dddddd"
                btn_font_w = "normal"

            btn = ctk.CTkButton(
                content_f, text=f"  {label}",
                anchor="w", height=28, font=ctk.CTkFont(size=12, weight=btn_font_w),
                fg_color="transparent", hover_color="#2a2a2a",
                text_color=btn_txt_color, corner_radius=0,
                command=_pick
            )
            btn.pack(fill="x", padx=0, pady=0)

            # 미리보기 라벨
            ctk.CTkLabel(
                content_f, text=f"    → {phrase}",
                anchor="w", font=ctk.CTkFont(size=11), text_color="#555555"
            ).pack(fill="x", padx=0)

        # 팝업 바깥 클릭 시 닫기
        pop.bind("<FocusOut>", lambda e: pop.destroy())
        pop.focus_set()

    def _insert_phrase(self, phrase: str):
        """활성화된 텍스트박스나 입력창의 커서 위치에 문장 조각 삽입"""
        focused = self.focus_get()
        target = focused if isinstance(focused, (ctk.CTkEntry, ctk.CTkTextbox)) else getattr(self, "txt_prompt", None)
        
        if not target:
            return

        try:
            idx = target.index("insert")
        except Exception:
            idx = "end"
            
        if isinstance(target, ctk.CTkTextbox):
            try:
                before = target.get("1.0", idx)
                if before and before[-1] not in (" ", "\n", ""):
                    phrase = " " + phrase
            except Exception:
                pass
            target.insert(idx, phrase)
        else: # CTkEntry
            try:
                before = target.get()[:target.index("insert")]
                if before and before[-1] not in (" ", ""):
                    phrase = " " + phrase
            except Exception:
                pass
            target.insert(idx, phrase)

        target.focus()
        self._highlight_keep_tokens()

    def _insert_var_token(self, var_name: str):
        """활성화된 텍스트박스나 입력창의 커서 위치에 {변수명} 삽입"""
        self._insert_phrase(f"{{{var_name}}}")

    # ── 데이터 소스 기능 ──────────────────────────────────────────────────────

    def _load_data_source(self):
        """Excel / CSV / JSON 파일 선택 → DataLoader로 헤더 파싱 → 헤더 선택 UI 표시"""
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="데이터 소스 파일 선택",
            filetypes=[
                ("지원 파일", "*.xlsx *.xls *.csv *.json"),
                ("Excel", "*.xlsx *.xls"),
                ("CSV", "*.csv"),
                ("JSON", "*.json"),
            ]
        )
        if not path:
            return
        try:
            # DataLoader로 헤더 + 샘플 파싱
            from rpa_data_loader import DataLoader
            loader = DataLoader(path)
            loader.load()
            self.data_source_path      = path
            self.data_source_row_count = len(loader.rows)
            self.data_source_columns   = loader.headers
            self.data_source_sample    = loader.rows[:5]
            self._ds_loader            = loader  # 헤더 info 캐시 보존

            fname = path.replace("\\", "/").split("/")[-1]
            self.lbl_ds_status.configure(
                text=f"{fname}  |  {self.data_source_row_count}행  |  {len(loader.headers)}컬럼 감지됨  →  [헤더 선택] 버튼으로 Keep 추가",
                text_color="#4caf50"
            )
            self.frm_ds_info.configure(height=36)

            # 헤더 선택 팝업 자동 열기
            self._show_header_keep_picker(loader)

        except Exception as e:
            messagebox.showerror("데이터 소스 오류", f"파일 읽기 실패:\n{e}")

    def _load_folder_source(self):
        """폴더 경로 선택 → 확장자 입력(예: pdf) → 폴더 내 파일명 목록을 배열 변수(file_array)로 Keep에 등록"""
        from tkinter import filedialog
        folder = filedialog.askdirectory(title="배치 처리 대상 폴더 선택")
        if not folder:
            return

        folder = os.path.abspath(folder)
        folder_name = os.path.basename(folder) or folder

        pop = ctk.CTkToplevel(self)
        pop.title("폴더 파일 배열 등록")
        pop.attributes("-topmost", True)
        pop.geometry("460x280")
        pop.configure(fg_color="#1a1a1a")

        # 헤더
        hdr = ctk.CTkFrame(pop, fg_color="#2c1338", corner_radius=4)
        hdr.pack(fill="x", padx=8, pady=8)
        ctk.CTkLabel(
            hdr, text=f"  폴더: {folder_name}",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#ce93d8", anchor="w"
        ).pack(side="left", padx=8, pady=8)

        body_f = ctk.CTkFrame(pop, fg_color="transparent")
        body_f.pack(fill="both", expand=True, padx=12, pady=4)

        # 경로 표시
        ctk.CTkLabel(body_f, text="선택 경로:", font=ctk.CTkFont(size=11), text_color="#888").grid(row=0, column=0, sticky="w", pady=4)
        lbl_path = ctk.CTkLabel(body_f, text=folder[:45] + ("..." if len(folder) > 45 else ""), font=ctk.CTkFont(family="Consolas", size=11), text_color="#bbbbbb")
        lbl_path.grid(row=0, column=1, sticky="w", padx=6, pady=4)

        # 확장자 입력
        ctk.CTkLabel(body_f, text="파일 확장자:", font=ctk.CTkFont(size=11), text_color="#888").grid(row=1, column=0, sticky="w", pady=4)
        ent_ext = ctk.CTkEntry(body_f, width=160, height=26, font=ctk.CTkFont(family="Consolas", size=12))
        ent_ext.insert(0, "pdf")
        ent_ext.grid(row=1, column=1, sticky="w", padx=6, pady=4)

        # 변수명 입력
        ctk.CTkLabel(body_f, text="Keep 변수명:", font=ctk.CTkFont(size=11), text_color="#888").grid(row=2, column=0, sticky="w", pady=4)
        ent_var = ctk.CTkEntry(body_f, width=160, height=26, font=ctk.CTkFont(family="Consolas", size=12))
        ent_var.insert(0, "file_list")
        ent_var.grid(row=2, column=1, sticky="w", padx=6, pady=4)

        # 실시간 파일 감지 라벨
        lbl_preview = ctk.CTkLabel(body_f, text="감지 중...", font=ctk.CTkFont(size=11), text_color="#ce93d8")
        lbl_preview.grid(row=3, column=0, columnspan=2, sticky="w", pady=8)

        def _update_count(*args):
            ext_clean = ent_ext.get().strip().lstrip(".")
            try:
                files = [
                    f for f in os.listdir(folder)
                    if os.path.isfile(os.path.join(folder, f)) and
                    (ext_clean == "*" or not ext_clean or f.lower().endswith(f".{ext_clean.lower()}"))
                ]
                lbl_preview.configure(
                    text=f"총 {len(files)}개 파일 일치  (예: {', '.join(files[:2]) if files else '없음'})",
                    text_color="#81c784" if files else "#ffb74d"
                )
            except Exception as e:
                lbl_preview.configure(text=f"조회 실패: {e}", text_color="#e57373")

        ent_ext.bind("<KeyRelease>", _update_count)
        _update_count()

        def _apply():
            ext_clean = ent_ext.get().strip().lstrip(".")
            vname = ent_var.get().strip() or "file_list"
            try:
                matched_files = [
                    f for f in os.listdir(folder)
                    if os.path.isfile(os.path.join(folder, f)) and
                    (ext_clean == "*" or not ext_clean or f.lower().endswith(f".{ext_clean.lower()}"))
                ]
            except Exception as e:
                messagebox.showerror("오류", f"폴더 조회 실패: {e}")
                return

            if not matched_files:
                if not messagebox.askyesno("확인", "해당 확장자의 파일이 없습니다. 그래도 변수를 등록하시겠습니까?"):
                    return

            # Keep 아이템 객체 생성
            item_dict = {
                "keep_type":    "file_array",
                "var_name":     vname,
                "column_name":  ext_clean,
                "data_type":    "list[str]",
                "source_file":  folder,
                "label":        f"{folder_name}/*.{ext_clean} ({len(matched_files)}개)",
                "selector":     folder,
                "element_type": "array",
                "path":         f"{folder_name}/*.{ext_clean} ({len(matched_files)}개)",
                "file_names":   matched_files
            }

            # 중복 체크 후 업데이트 또는 추가
            for i, existing in enumerate(self.keep_list):
                if existing.get("var_name") == vname:
                    self.keep_list[i] = item_dict
                    break
            else:
                self.keep_list.append(item_dict)

            # DB 영구 저장
            if getattr(self, "db", None) and getattr(self, "current_project", None):
                try:
                    eid = self.db.save_keep_element(
                        project_id=self.current_project["id"],
                        var_name=vname,
                        keep_type="file_array",
                        column_name=ext_clean,
                        data_type="list[str]",
                        source_file=folder,
                        label=item_dict["label"],
                        path=item_dict["path"]
                    )
                    item_dict["id"] = eid
                except Exception as e:
                    print(f"DB Keep 저장 에러: {e}")

            # UI 갱신
            self.lbl_ds_status.configure(
                text=f"{folder_name}/*.{ext_clean}  |  {len(matched_files)}개 파일  |  {{{vname}}} 등록됨",
                text_color="#ce93d8"
            )
            self.frm_ds_info.configure(height=36)
            self._render_keep_list()
            self._render_var_chips()
            self._render_data_chips()
            pop.destroy()
            messagebox.showinfo("등록 완료", f"{{{vname}}} 배열 변수가 Keep 목록에 등록되었습니다.\n(총 {len(matched_files)}개 파일)")

        btn_box = ctk.CTkFrame(pop, fg_color="transparent")
        btn_box.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkButton(btn_box, text="✓ Keep 배열 변수 등록", height=32, fg_color="#4a148c", hover_color="#6a1b9a", font=ctk.CTkFont(size=12, weight="bold"), command=_apply).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(btn_box, text="취소", height=32, width=80, fg_color="#333", hover_color="#444", command=pop.destroy).pack(side="right")

    def _show_header_keep_picker(self, loader=None):
        """컬럼 헤더 목록 표시 + [Keep+] 버튼으로 data_column Keep 추가 팝업"""
        if loader is None:
            loader = getattr(self, "_ds_loader", None)
        if loader is None:
            messagebox.showwarning("데이터 소스", "먼저 파일을 선택하세요.")
            return

        headers_info = loader.headers_info()

        pop = ctk.CTkToplevel(self)
        pop.title("헤더 선택 — Keep 추가")
        pop.attributes("-topmost", True)
        pop.geometry("740x520")
        pop.configure(fg_color="#1a1a1a")

        # 상단 헤더 바
        fname = loader.file_path.replace(chr(92), '/').split('/')[-1]
        hdr = ctk.CTkFrame(pop, fg_color="#0d2137", corner_radius=4)
        hdr.pack(fill="x", padx=6, pady=6)
        ctk.CTkLabel(
            hdr, text=f"  {fname}  ·  {len(headers_info)}컬럼  ·  {len(loader.rows)}행",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#64b5f6", anchor="w"
        ).pack(side="left", padx=8, pady=8)

        # 전체 Keep 추가 함수
        row_widgets = []

        def _keep_all():
            added_count = 0
            for info_, ent_, btn_ in row_widgets:
                vname = ent_.get().strip()
                if not vname:
                    continue
                if any(x.get("var_name") == vname for x in self.keep_list):
                    continue
                item_dict = {
                    "keep_type":    "data_column",
                    "var_name":     vname,
                    "column_name":  info_["name"],
                    "data_type":    info_["inferred_type"],
                    "source_file":  self.data_source_path,
                    "label":        info_["name"],
                    "selector":     "",
                    "element_type": "data_column",
                    "path":         "",
                }
                if getattr(self, "db", None) and getattr(self, "current_project", None):
                    try:
                        eid = self.db.save_keep_element(
                            project_id=self.current_project["id"],
                            var_name=vname,
                            keep_type="data_column",
                            column_name=info_["name"],
                            data_type=info_["inferred_type"],
                            source_file=self.data_source_path,
                            label=info_["name"]
                        )
                        item_dict["id"] = eid
                    except Exception as e:
                        print(f"DB Keep 에러: {e}")
                self.keep_list.append(item_dict)
                btn_.configure(text="✓ 추가됨", fg_color="#2e7d32")
                added_count += 1
            self._render_keep_list()
            self._render_var_chips()
            self._render_data_chips()
            if added_count > 0:
                messagebox.showinfo("Keep 추가 완료", f"{added_count}개 컬럼이 Keep 목록에 추가되었습니다.")

        btn_all_top = ctk.CTkButton(
            hdr, text="✓ 전체 컬럼 Keep 추가", height=28,
            font=ctk.CTkFont(size=11, weight="bold"), fg_color="#2e7d32", hover_color="#1b5e20",
            command=_keep_all
        )
        btn_all_top.pack(side="right", padx=8, pady=6)

        # 컬럼 헤더 행 제목
        col_hdr = ctk.CTkFrame(pop, fg_color="#111111", corner_radius=0)
        col_hdr.pack(fill="x", padx=6)
        ctk.CTkLabel(col_hdr, text="컬럼명", width=160, font=ctk.CTkFont(size=11, weight="bold"), text_color="#888", anchor="w").pack(side="left", padx=6, pady=4)
        ctk.CTkLabel(col_hdr, text="샘플 값", width=130, font=ctk.CTkFont(size=11, weight="bold"), text_color="#888", anchor="w").pack(side="left", padx=4)
        ctk.CTkLabel(col_hdr, text="타입", width=50, font=ctk.CTkFont(size=11, weight="bold"), text_color="#888", anchor="w").pack(side="left", padx=4)
        ctk.CTkLabel(col_hdr, text="변수명 ({row.})", width=160, font=ctk.CTkFont(size=11, weight="bold"), text_color="#888", anchor="w").pack(side="left", padx=4)
        ctk.CTkLabel(col_hdr, text="선택 작업", width=80, font=ctk.CTkFont(size=11, weight="bold"), text_color="#888", anchor="e").pack(side="right", padx=10)

        # 스크롤 목록
        sf = ctk.CTkScrollableFrame(pop, fg_color="transparent")
        sf.pack(fill="both", expand=True, padx=6, pady=4)

        # 이미 Keep된 data_column var_name 집합
        already_kept = {
            itm.get("var_name") for itm in self.keep_list
            if itm.get("keep_type") == "data_column"
        }

        for info in headers_info:
            row_f = ctk.CTkFrame(sf, fg_color="#1e1e1e", corner_radius=4, height=36)
            row_f.pack(fill="x", pady=2)
            row_f.pack_propagate(False)

            var_name_default = f"row.{info['var_name']}"
            is_kept = var_name_default in already_kept

            # 1. 우측 Keep 버튼을 먼저 pack(side="right")하여 공간 100% 확보
            btn_text = "✓ 추가됨" if is_kept else "Keep ★"
            btn_color = "#2e7d32" if is_kept else "#1a3a5c"
            btn = ctk.CTkButton(
                row_f, text=btn_text, width=80, height=26,
                fg_color=btn_color, hover_color="#1f6aa5",
                font=ctk.CTkFont(size=11, weight="bold")
            )
            btn.pack(side="right", padx=8)

            # 2. 좌측 컬럼 라벨 및 변수명 입력창
            ctk.CTkLabel(row_f, text=info["name"], width=160, anchor="w",
                         font=ctk.CTkFont(size=11, weight="bold"), text_color="#dddddd").pack(side="left", padx=6)
            ctk.CTkLabel(row_f, text=str(info["sample"])[:18], width=130, anchor="w",
                         font=ctk.CTkFont(family="Consolas", size=11), text_color="#888").pack(side="left", padx=4)
            ctk.CTkLabel(row_f, text=info["inferred_type"], width=50, anchor="w",
                         font=ctk.CTkFont(size=11), text_color="#29b6f6").pack(side="left", padx=4)
            ent = ctk.CTkEntry(row_f, width=160, height=24, font=ctk.CTkFont(family="Consolas", size=11))
            ent.insert(0, var_name_default)
            ent.pack(side="left", padx=4)

            def _make_single_keep(info_=info, ent_=ent, btn_=btn):
                def _do():
                    vname = ent_.get().strip()
                    if not vname:
                        return
                    if any(x.get("var_name") == vname for x in self.keep_list):
                        messagebox.showinfo("중복", f"{vname} 은 이미 Keep 목록에 있습니다.")
                        return
                    item_dict = {
                        "keep_type":    "data_column",
                        "var_name":     vname,
                        "column_name":  info_["name"],
                        "data_type":    info_["inferred_type"],
                        "source_file":  self.data_source_path,
                        "label":        info_["name"],
                        "selector":     "",
                        "element_type": "data_column",
                        "path":         "",
                    }
                    if getattr(self, "db", None) and getattr(self, "current_project", None):
                        try:
                            eid = self.db.save_keep_element(
                                project_id=self.current_project["id"],
                                var_name=vname,
                                keep_type="data_column",
                                column_name=info_["name"],
                                data_type=info_["inferred_type"],
                                source_file=self.data_source_path,
                                label=info_["name"]
                            )
                            item_dict["id"] = eid
                        except Exception as e:
                            print(f"DB Keep 에러: {e}")
                    self.keep_list.append(item_dict)
                    self._render_keep_list()
                    self._render_var_chips()
                    self._render_data_chips()
                    btn_.configure(text="✓ 추가됨", fg_color="#2e7d32")
                return _do
            btn.configure(command=_make_single_keep())
            row_widgets.append((info, ent, btn))

        # 하단 액션 바
        b_bar = ctk.CTkFrame(pop, fg_color="transparent")
        b_bar.pack(fill="x", padx=8, pady=8)

        ctk.CTkButton(
            b_bar, text="✓ 전체 컬럼 Keep 추가", height=32, width=180,
            fg_color="#2e7d32", hover_color="#1b5e20", font=ctk.CTkFont(size=12, weight="bold"),
            command=_keep_all
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            b_bar, text="닫기", height=32, width=100, fg_color="#333", hover_color="#444",
            command=pop.destroy
        ).pack(side="right", padx=4)



    def _build_ai_prompt_with_keep(self, user_prompt: str) -> str:
        """Keep 목록 + 데이터 소스를 포함한 확장 프롬프트 생성"""
        lines = []

        # ⓪ 대상 URL / 시스템 (target_url 타입)
        url_items = [it for it in self.keep_list if it.get("keep_type") == "target_url"]
        if url_items:
            lines.append("[대상 URL / 시스템]")
            for item in url_items:
                lines.append(f"  {{{item['var_name']}}} = url: \"{item['selector']}\" (label: \"{item['label']}\")")
            lines.append("")

        # ① DOM/UI 요소 Keep (element 타입)
        elem_items = [it for it in self.keep_list if it.get("keep_type", "element") == "element"]
        if elem_items:
            lines.append("[고정 참조 객체 - DOM/UI 요소]")
            for item in elem_items:
                etype = item.get("element_type", "")
                opts = item.get("options")
                opt_str = f" | 선택옵션: {opts[:8]}" if opts else ""
                lines.append(f"  {{{item['var_name']}}} = selector: \"{item['selector']}\" | type: {etype}{opt_str}")
            lines.append("")

        # ② 데이터 컬럼 Keep (data_column 타입)
        data_items = [it for it in self.keep_list if it.get("keep_type") == "data_column"]
        if data_items:
            lines.append("[데이터 소스 - 테이블]")
            lines.append(f"  파일: {self.data_source_path}")
            lines.append(f"  총 행 수: {self.data_source_row_count}행")
            lines.append("  Keep된 컬럼:")
            for item in data_items:
                col   = item["column_name"]
                dtype = item.get("data_type", "str")
                vname = item["var_name"]
                # 샘플값 찾기
                sample = ""
                if self.data_source_sample:
                    sample = str(self.data_source_sample[0].get(col, ""))[:20]
                lines.append(f"    {{{vname}}} = column: \"{col}\" | type: {dtype} | 샘플: \"{sample}\"")
            lines.append(f"  → 코드에서 row[\"{data_items[0]['column_name']}\"] 형태로 값 참조")
            lines.append("")

        # ②-2 폴더 파일명 배열 Keep (file_array 타입)
        file_items = [it for it in self.keep_list if it.get("keep_type") == "file_array"]
        if file_items:
            lines.append("[데이터 소스 - 폴더 파일명 배열]")
            for item in file_items:
                folder = item.get("source_file") or item.get("path", "")
                ext = item.get("column_name") or "*"
                fnames = item.get("file_names", [])
                lines.append(f"  {{{item['var_name']}}} = folder: \"{folder}\" | extension: \"*.{ext}\" | 총 {len(fnames)}개 파일")
                if fnames:
                    lines.append(f"    감지된 파일명 샘플: {fnames[:5]}")
                lines.append(f"  → 코드에서 {item['var_name']} = [f for f in os.listdir(r\"{folder}\") if f.endswith(\".{ext}\")]")
                lines.append(f"    또는 for file_name in {item['var_name']}: 형태로 파일 목록 순회 루프 작성")
            lines.append("")

        # ③ 요구사항
        lines.append("[요구사항]")
        if "아래의 요구를 순차적으로 수행하는" not in user_prompt:
            lines.append("아래의 요구를 순차적으로 수행하는 파이썬-playwrite 자동화 스크립트를 작성하시오:")
        lines.append(user_prompt)
        lines.append("")

        # ④ 코드 생성 지침
        if url_items or elem_items or data_items or file_items:
            lines.append("[코드 생성 지침]")
            if url_items:
                lines.append("  - [대상 URL / 시스템]의 변수명을 page.goto() 또는 시작 접속 URL로 활용할 것")
            if elem_items:
                lines.append("  - [고정 참조 객체]의 변수명을 실제 Playwright 셀렉터로 대응할 것")
            if file_items:
                lines.append("  - [폴더 파일명 배열]의 변수명을 os.listdir() 또는 파일 리스트 순회 루프로 대응할 것")
                lines.append("  - import os 모듈 또는 from pathlib import Path 를 활용할 것")
            if data_items:
                lines.append("  - from rpa_data_loader import DataLoader 를 임포트할 것")
                lines.append(f"  - loader = DataLoader(\"{self.data_source_path}\") 로 파일을 로드할 것")
                lines.append("  - loader.iterate() 로 행을 순회하고 row[\"컬럼명\"] 으로 값을 참조할 것")
                lines.append("  - 각 행 처리 성공 시 loader.mark_done(idx, result=...) 호출할 것")
                lines.append("  - 각 행 처리 실패 시 loader.mark_error(idx, str(e)) 호출하고 continue할 것")
                lines.append("  - 루프 종료 후 반드시 loader.save_result() 로 결과 파일을 저장할 것")
                lines.append("  - 각 행 시작 시 loader.progress(idx) 로 진행률을 출력할 것")

        return "\n".join(lines) if lines else user_prompt


    def _on_harvest_error(self, err_msg: str):
        self.btn_harvest_dom.configure(text="DOM 수집", state="normal")
        self.lbl_dom_status.configure(text="DOM 수집 실패", text_color="#e57373")
        messagebox.showerror("DOM 수집 오류", f"수집 실패:\n{err_msg}")


    def _start_ai_generation(self):
        img_path_arg = None

        prompt = self.txt_prompt.get("1.0", "end").strip()
        if not prompt:
            messagebox.showwarning("입력 확인", "자동화 요구사항을 입력하십시오.")
            return

        target_url = self.cbo_target_url.get().strip() or self.cbo_windows.get()
        chosen_browser = "Chrome"
        catalog_summary = DOMHarvester.format_catalog_to_text(self.current_catalog)
        # Keep 목록이 있으면 확장 프롬프트로 교체
        prompt = self._build_ai_prompt_with_keep(prompt)
        engine_choice = self.seg_engine.get()

        self._save_all_configs()
        self._refresh_target_urls()

        if "Gemini" in engine_choice:
            api_key = self.ent_api_key.get().strip()
            if not api_key:
                messagebox.showwarning("입력 확인", "Gemini API Key를 입력하십시오.")
                return
            model = self.cbo_gemini_model.get()
            self.btn_generate.configure(text="코드 생성 중...", state="disabled")
            self.txt_result_code.delete("1.0", "end")
            self.txt_result_code.insert("1.0", f"# Google Gemini ({model}) 분석 중... (브라우저: {chosen_browser})\n")

            def _worker_gemini():
                try:
                    code, full_text = GeminiVisionAgent.call_gemini_vision(
                        api_key=api_key,
                        image_path=img_path_arg,
                        user_prompt=prompt,
                        target_url=target_url,
                        model=model,
                        page_html=catalog_summary,
                        browser_choice=chosen_browser
                    )
                    self._safe_after(0, lambda c=code, f=full_text: self._on_generation_success(c, f, "Gemini"))
                except Exception as e:
                    self._safe_after(0, lambda err=str(e): self._on_generation_error(err))

            threading.Thread(target=_worker_gemini, daemon=True).start()

        else:
            ollama_url = self.ent_ollama_url.get().strip() or "http://localhost:11434"
            model = self.cbo_ollama_model.get()
            self.btn_generate.configure(text="추론 중...", state="disabled")
            self.txt_result_code.delete("1.0", "end")
            self.txt_result_code.insert("1.0", f"# Local Ollama ({model}) 추론 중... (브라우저: {chosen_browser})\n")

            def _worker_ollama():
                try:
                    code, full_text = OllamaVisionAgent.call_ollama_vision(
                        ollama_url=ollama_url,
                        model=model,
                        image_path=img_path_arg,
                        user_prompt=prompt,
                        target_url=target_url,
                        page_html=catalog_summary,
                        browser_choice=chosen_browser
                    )
                    self._safe_after(0, lambda c=code, f=full_text: self._on_generation_success(c, f, f"Ollama ({model})"))
                except Exception as e:
                    self._safe_after(0, lambda err=str(e): self._on_generation_error(err))

            threading.Thread(target=_worker_ollama, daemon=True).start()

    def _on_generation_success(self, code: str, full_text: str, engine_name: str):
        self.btn_generate.configure(text="코드 생성", state="normal")

        # 지문 수집
        fp = self._collect_fingerprint(engine_name)
        # 지문 헤더 주입
        code_with_fp = self._build_fingerprint_header(fp) + "\n" + code

        self.txt_result_code.delete("1.0", "end")
        self.txt_result_code.insert("1.0", code_with_fp)

        # DB 저장 (프로젝트가 설정된 경우)
        self._save_task_to_db(fp, code_with_fp)

        messagebox.showinfo("완료", "코드가 생성되었습니다.")

    def _collect_fingerprint(self, engine_name: str) -> dict:
        """시스템 지문 정보 수집"""
        import platform, socket, sys, datetime
        playwright_ver = ""
        try:
            import playwright
            playwright_ver = getattr(playwright, "__version__", "")
        except Exception:
            pass
        model_str = ""
        try:
            if "Gemini" in engine_name:
                model_str = self.cbo_gemini_model.get()
            else:
                model_str = self.cbo_ollama_model.get()
        except Exception:
            pass
        return {
            "ai_engine":    engine_name,
            "ai_model":     model_str,
            "generated_at": datetime.datetime.now(),
            "build_type":   self.var_build_type.get(),
            "task_title":   (self.ent_task_title.get().strip() or "(무제)"),
            "sys_os":       platform.platform(),
            "sys_hostname": socket.gethostname(),
            "sys_python":   sys.version.split()[0],
            "sys_user":     os.environ.get("USERNAME") or os.environ.get("USER") or "",
            "sys_playwright": playwright_ver,
            "project_name": self.current_project["name"] if self.current_project else "(오프라인)",
        }

    def _build_fingerprint_header(self, fp: dict) -> str:
        """지문 주석 헤더 문자열 생성"""
        gen_time = fp["generated_at"].strftime("%Y-%m-%d %H:%M:%S")
        build_tag = fp["build_type"].upper()
        line = "# " + "=" * 59
        sep  = "# " + "-" * 39
        lines = [
            line,
            "# [RPA Script Fingerprint]",
            f"# Project   : {fp['project_name']}",
            f"# Task      : {fp['task_title']}",
            f"# Build     : {build_tag}",
            sep,
            f"# AI Engine : {fp['ai_engine']}",
            f"# AI Model  : {fp['ai_model']}",
            f"# Generated : {gen_time}",
            sep,
            f"# OS        : {fp['sys_os']}",
            f"# Hostname  : {fp['sys_hostname']}",
            f"# User      : {fp['sys_user']}",
            f"# Python    : {fp['sys_python']}",
            f"# Playwright: {fp['sys_playwright']}",
            line,
        ]
        return "\n".join(lines)

    def _save_prompt_draft(self):
        """작성 중인 자연어 프롬프트와 태스크 정보를 DB에 임시저장 (draft)"""
        prompt = self.txt_prompt.get("1.0", "end").strip()
        if not prompt:
            messagebox.showinfo("저장 안내", "저장할 프롬프트 내용이 없습니다.")
            return

        title = self.ent_task_title.get().strip()
        if not title:
            # 첫 번째 줄에서 제목 자동 추출
            first_line = prompt.splitlines()[0][:30].strip()
            title = first_line or f"태스크_{int(time.time())}"
            self.ent_task_title.delete(0, "end")
            self.ent_task_title.insert(0, title)

        if not self.db or not self.current_project:
            messagebox.showinfo("저장 완료", "프로젝트가 연결되지 않아 로컬 세션에 임시 보관되었습니다.")
            return

        try:
            pid = self.current_project["id"]
            tid = getattr(self, "current_task_id", None)
            btype = self.var_build_type.get()
            new_tid = self.db.save_draft_task(
                project_id=pid,
                title=title,
                prompt_text=prompt,
                task_id=tid,
                build_type=btype
            )
            self.current_task_id = new_tid
            self.db.touch_project(pid)

            # 저장 완료 시각적 피드백
            orig_text = self.btn_save_task.cget("text")
            orig_color = self.btn_save_task.cget("fg_color")
            self.btn_save_task.configure(text="저장됨 ✓", fg_color="#2e7d32")
            self.after(1500, lambda: self.btn_save_task.configure(text=orig_text, fg_color=orig_color))
        except Exception as e:
            messagebox.showerror("저장 오류", f"태스크 저장 중 오류 발생:\n{e}")

    def _show_load_task_popup(self):
        """저장된 태스크/프롬프트 목록 조회 및 불러오기 팝업"""
        if not self.db or not self.current_project:
            messagebox.showwarning("불러오기", "먼저 프로젝트를 선택하거나 연결하십시오.")
            return

        pid = self.current_project["id"]
        tasks = self.db.list_tasks(pid)
        if not tasks:
            messagebox.showinfo("불러오기", f"'{self.current_project['name']}' 프로젝트에 저장된 태스크가 없습니다.")
            return

        pop = ctk.CTkToplevel(self)
        pop.title("태스크 및 프롬프트 불러오기")
        pop.geometry("580x440")
        pop.attributes("-topmost", True)

        # 상단 헤더
        top_f = ctk.CTkFrame(pop, fg_color="transparent")
        top_f.pack(fill="x", padx=16, pady=(14, 6))
        ctk.CTkLabel(
            top_f, text=f"저장된 태스크 목록 ({len(tasks)}개)",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(side="left")
        ctk.CTkLabel(
            top_f, text=f"프로젝트: {self.current_project['name']}",
            font=ctk.CTkFont(size=11), text_color="#aaaaaa"
        ).pack(side="right")

        # 스크롤 목록
        scr = ctk.CTkScrollableFrame(pop, fg_color="#181818", corner_radius=6)
        scr.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        def _load_selected(t):
            self.txt_prompt.delete("1.0", "end")
            self.txt_prompt.insert("1.0", t.get("prompt_text", ""))
            self.ent_task_title.delete(0, "end")
            self.ent_task_title.insert(0, t.get("title", ""))
            if t.get("script_code"):
                self.txt_result_code.delete("1.0", "end")
                self.txt_result_code.insert("1.0", t["script_code"])
            self.var_build_type.set(t.get("build_type", "debug"))
            self.current_task_id = t["id"]
            self._highlight_keep_tokens()
            pop.destroy()

        def _delete_selected(tid, row_frame):
            if messagebox.askyesno("삭제 확인", "이 태스크를 정말 삭제하시겠습니까?"):
                self.db.delete_task(tid)
                row_frame.destroy()
                if getattr(self, "current_task_id", None) == tid:
                    self.current_task_id = None

        for t in tasks:
            row = ctk.CTkFrame(scr, fg_color="#222222", corner_radius=6)
            row.pack(fill="x", pady=4, padx=2)

            r_top = ctk.CTkFrame(row, fg_color="transparent")
            r_top.pack(fill="x", padx=8, pady=(6, 2))

            status = t.get("status", "draft")
            badge_color = "#1565c0" if status == "generated" else "#f57f17"
            badge_text = "코드완료" if status == "generated" else "임시저장"
            ctk.CTkLabel(
                r_top, text=f"[{badge_text}]", font=ctk.CTkFont(size=11, weight="bold"),
                text_color=badge_color
            ).pack(side="left", padx=(0, 6))

            ctk.CTkLabel(
                r_top, text=t.get("title", "무제 태스크"), font=ctk.CTkFont(size=12, weight="bold")
            ).pack(side="left")

            btn_del = ctk.CTkButton(
                r_top, text="삭제", width=46, height=24,
                fg_color="#b71c1c", hover_color="#c62828", font=ctk.CTkFont(size=11),
                command=lambda tid=t["id"], rf=row: _delete_selected(tid, rf)
            )
            btn_del.pack(side="right", padx=(4, 0))

            btn_apply = ctk.CTkButton(
                r_top, text="불러오기", width=68, height=24,
                fg_color="#00695c", hover_color="#00796b", font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda task=t: _load_selected(task)
            )
            btn_apply.pack(side="right")

            p_text = t.get("prompt_text", "").replace("\n", " ")[:90]
            if p_text:
                ctk.CTkLabel(
                    row, text=f"💬 {p_text}...", font=ctk.CTkFont(size=11),
                    text_color="#888888", anchor="w"
                ).pack(fill="x", padx=10, pady=(0, 6))

    def _save_task_to_db(self, fp: dict, code: str):
        """생성된 태스크를 DB에 저장 (프로젝트 연결 시)"""
        if not self.db or not self.current_project:
            return
        try:
            prompt = self.txt_prompt.get("1.0", "end").strip()
            pid = self.current_project["id"]
            task_id = self.db.save_task(
                project_id=pid,
                title=fp["task_title"],
                prompt_text=prompt,
                script_code=code,
                build_type=fp["build_type"],
                ai_engine=fp["ai_engine"],
                ai_model=fp["ai_model"],
                generated_at=fp["generated_at"],
                sys_os=fp["sys_os"],
                sys_hostname=fp["sys_hostname"],
                sys_python=fp["sys_python"],
                sys_user=fp["sys_user"],
                sys_playwright=fp["sys_playwright"],
                status="generated"
            )
            self.current_task_id = task_id
            self.db.touch_project(pid)
            print(f"[DB] 태스크 저장 완료 task_id={task_id}")
        except Exception as e:
            print(f"[DB] 태스크 저장 실패: {e}")

    def _load_project_keep_elements(self):
        """DB에서 현재 프로젝트의 Target URL 및 Keep 요소 목록 불러오기"""
        if not self.db or not self.current_project:
            return
        try:
            pid = self.current_project["id"]
            self.keep_list = []

            # 1. Target URL (rpa_targets) 먼저 로드
            from urllib.parse import urlparse
            targets = self.db.list_targets(pid)
            for idx, t in enumerate(targets):
                val = t.get("value") or t.get("label") or ""
                lbl = t.get("label") or ""
                if lbl and not lbl.startswith("http://") and not lbl.startswith("https://"):
                    vname = lbl
                else:
                    try:
                        p = urlparse(val).path.strip("/").replace("/", "_").replace("-", "_")
                        vname = f"url_{p}" if p else f"url_{idx+1}"
                    except Exception:
                        vname = f"url_{idx+1}"

                self.keep_list.append({
                    "id": t.get("id"),
                    "var_name": vname,
                    "label": lbl,
                    "selector": val,
                    "element_type": "url",
                    "path": val,
                    "keep_type": "target_url",
                    "target_id": t.get("id"),
                    "column_name": "",
                    "data_type": "",
                    "source_file": ""
                })

            # 2. Keep Elements (rpa_keep_elements) 로드
            items = self.db.list_keep_elements(pid)
            for itm in items:
                ktype = itm.get("keep_type") or "element"
                fnames = []
                if ktype == "file_array":
                    folder = itm.get("source_file") or itm.get("selector") or ""
                    ext = itm.get("column_name") or "*"
                    if os.path.isdir(folder):
                        try:
                            fnames = [
                                f for f in os.listdir(folder)
                                if os.path.isfile(os.path.join(folder, f)) and
                                (ext == "*" or not ext or f.lower().endswith(f".{ext.lower()}"))
                            ]
                        except Exception:
                            pass

                self.keep_list.append({
                    "id": itm.get("id"),
                    "var_name": itm.get("var_name"),
                    "label": itm.get("label") or "",
                    "selector": itm.get("selector") or "",
                    "element_type": itm.get("element_type") or ("array" if ktype == "file_array" else "element"),
                    "path": itm.get("path") or "",
                    "keep_type": ktype,
                    "target_id": itm.get("target_id"),
                    "column_name": itm.get("column_name") or "",
                    "data_type": itm.get("data_type") or "",
                    "source_file": itm.get("source_file") or "",
                    "file_names": fnames
                })
            self._render_keep_list()
            self._render_var_chips()
            self._render_data_chips()
        except Exception as e:
            print(f"[DB] Keep 요소 불러오기 실패: {e}")

    def _update_project_bar(self):
        """프로젝트 컨텍스트 바 라벨 및 DB 리소스(URL, Keep) 갱신"""
        try:
            if self.current_project:
                self.lbl_proj_name.configure(
                    text=f"프로젝트: {self.current_project['name']}",
                    text_color="#4caf50"
                )
                self._refresh_target_urls()
                self._load_project_keep_elements()
            else:
                self.lbl_proj_name.configure(text="[오프라인]", text_color="#888888")
        except Exception as e:
            print(f"프로젝트 바 갱신 오류: {e}")

    def _switch_project(self):
        """프로젝트 전환 - 시작 모달 재호출"""
        try:
            from project_startup import show_startup_dialog
            result = show_startup_dialog(self.winfo_toplevel(), self.db)
            if result is not None:
                self.current_project = result
                self._update_project_bar()
        except Exception as e:
            messagebox.showwarning("프로젝트 전환", f"전환 실패: {e}")

    def _on_generation_error(self, err_msg: str):
        self.btn_generate.configure(text="코드 생성", state="normal")
        self.txt_result_code.delete("1.0", "end")
        self.txt_result_code.insert("1.0", f"[오류]\n{err_msg}")
        messagebox.showerror("오류", f"코드 생성 실패:\n{err_msg}")

    # =========================================================================
    # 액션 핸들러
    # =========================================================================
    def _do_insert_editor(self):
        code = self.txt_result_code.get("1.0", "end").strip()
        if not code or code.startswith("#") or code.startswith("[오류"):
            messagebox.showwarning("안내", "유효한 코드가 없습니다.")
            return

        if self.on_insert_code:
            self.on_insert_code(code)
            if self.on_switch_tab:
                self.on_switch_tab("script")
            messagebox.showinfo("전송 완료", "스크립트 에디터로 전송되었습니다.")

    def _do_add_bot(self):
        code = self.txt_result_code.get("1.0", "end").strip()
        if not code or code.startswith("#") or code.startswith("[오류"):
            messagebox.showwarning("안내", "유효한 코드가 없습니다.")
            return

        engine_str = "Gemini" if "Gemini" in self.seg_engine.get() else self.cbo_ollama_model.get()
        prompt_first_line = self.txt_prompt.get("1.0", "end").strip().splitlines()[0][:20]
        mod_data = {
            "name": f"ai_mod_{int(time.time())}",
            "title": f"{prompt_first_line}",
            "category": "웹조작",
            "description": f"AI 생성 모듈 ({engine_str})",
            "code": code
        }

        if self.on_add_to_bot:
            self.on_add_to_bot(mod_data)
            if self.on_switch_tab:
                self.on_switch_tab("bot")
            messagebox.showinfo("등록 완료", "봇 에디터에 등록되었습니다.")

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
    # 설정 자동 저장
    # =========================================================================
    def _refresh_target_urls(self):
        if not self.db or not self.current_project:
            return
        try:
            targets = self.db.list_targets(self.current_project["id"])
            urls = [t["value"] for t in targets if t.get("type") == "url"]
            self.cbo_target_url.configure(values=urls)
        except Exception as e:
            print(f"Failed to load targets: {e}")

    def _save_target_url(self):
        if not self.db or not self.current_project:
            from tkinter import messagebox
            messagebox.showerror("오류", "프로젝트 DB가 연결되지 않았습니다.")
            return
            
        url = self.cbo_target_url.get().strip()
        if not url:
            return
            
        try:
            targets = self.db.list_targets(self.current_project["id"])
            urls = [t["value"] for t in targets if t.get("type") == "url"]
            if url not in urls:
                self.db.add_target(
                    project_id=self.current_project["id"],
                    label=url,
                    value=url,
                    type_="url"
                )
                self._refresh_target_urls()
                self._load_project_keep_elements()
                from tkinter import messagebox
                messagebox.showinfo("URL 저장", "현재 URL이 프로젝트 대상 목록에 저장되었습니다.")
            else:
                from tkinter import messagebox
                messagebox.showinfo("URL 저장", "이미 저장된 URL입니다.")
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("오류", f"URL 저장 실패: {e}")

    def _load_saved_configs(self):
        k = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
        ollama_u = "http://localhost:11434"
        target_u = "http://175.119.156.105:3000/contract/list"
        last_engine = "Google Gemini"
        last_gemini_model = "gemini-2.5-flash"
        last_ollama_model = "qwen2.5-coder:7b"

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
            self.cbo_target_url.set(target_u)

        if "Ollama" in last_engine:
            self.seg_engine.set("Local Ollama")
            self._on_engine_changed("Local Ollama")
        else:
            self.seg_engine.set("Google Gemini")
            self._on_engine_changed("Google Gemini")

        if last_gemini_model in ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash"]:
            self.cbo_gemini_model.set(last_gemini_model)

        if last_ollama_model:
            self.cbo_ollama_model.set(last_ollama_model)


        self._refresh_target_urls()

    def _save_all_configs(self):
        data_to_save = {
            "gemini_api_key": self.ent_api_key.get().strip(),
            "ollama_url": self.ent_ollama_url.get().strip(),
            "target_url": self.cbo_target_url.get().strip(),
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
    def __init__(self, parent, on_insert_code: Optional[Callable[[str], None]] = None,
                 on_add_to_bot: Optional[Callable[[Dict[str, Any]], None]] = None):
        super().__init__(parent)
        self.title("AI 비전 코드 생성")
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

