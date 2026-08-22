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
                           user_prompt: str, target_url: str = "", page_html: str = "",
                           browser_choice: str = "Chrome") -> Tuple[str, str]:
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

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
        prompt_body += "위 화면 스크린샷과 UI 객체 목록에서 타겟 요소를 찾아 Playwright 코드를 작성하십시오."

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

        self._build_ui()
        self._load_saved_configs()
        self._refresh_window_list()

    def _build_ui(self):
        # ── 프로젝트 컨텍스트 바 (상단 고정) ──────────────────────────────────
        proj_bar = ctk.CTkFrame(self, fg_color="#111111", corner_radius=0, height=32)
        proj_bar.pack(fill="x", padx=0, pady=(0, 2))
        proj_bar.pack_propagate(False)

        self.lbl_proj_name = ctk.CTkLabel(
            proj_bar, text="[오프라인]",
            font=ctk.CTkFont(size=11, weight="bold"), text_color="#888888"
        )
        self.lbl_proj_name.pack(side="left", padx=(12, 0))

        ctk.CTkButton(
            proj_bar, text="프로젝트 전환", width=90, height=22,
            font=ctk.CTkFont(size=10), fg_color="#333333", hover_color="#444444",
            command=self._switch_project
        ).pack(side="right", padx=8)

        self._update_project_bar()

        # 1. 상단 설정 바
        top_ctrl = ctk.CTkFrame(self, corner_radius=6)
        top_ctrl.pack(fill="x", padx=6, pady=(4, 6))

        ctk.CTkLabel(top_ctrl, text="AI 엔진", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=(12, 6), pady=8)
        self.seg_engine = ctk.CTkSegmentedButton(
            top_ctrl, values=["Google Gemini", "Local Ollama"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_engine_changed
        )
        self.seg_engine.pack(side="left", padx=(0, 12), pady=6)

        self.engine_conf_frame = ctk.CTkFrame(top_ctrl, fg_color="transparent")
        self.engine_conf_frame.pack(side="left", fill="x", expand=True, padx=4)

        # [A] Gemini 설정
        self.f_gemini = ctk.CTkFrame(self.engine_conf_frame, fg_color="transparent")
        ctk.CTkLabel(self.f_gemini, text="API 키", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(0, 6))
        self.ent_api_key = ctk.CTkEntry(self.f_gemini, height=30, width=220, font=ctk.CTkFont(size=12), placeholder_text="Gemini API Key", show="*")
        self.ent_api_key.pack(side="left", padx=(0, 6))
        self.ent_api_key.bind("<FocusOut>", lambda e: self._save_all_configs())

        btn_toggle_key = ctk.CTkButton(self.f_gemini, text="보기", width=45, height=30, font=ctk.CTkFont(size=12), fg_color="#444444", command=self._toggle_key_visibility)
        btn_toggle_key.pack(side="left", padx=(0, 6))

        btn_save_key = ctk.CTkButton(self.f_gemini, text="저장", width=55, height=30, font=ctk.CTkFont(size=12), fg_color="#2e7d32", command=self._save_all_configs)
        btn_save_key.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(self.f_gemini, text="모델", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(0, 6))
        self.cbo_gemini_model = ctk.CTkComboBox(
            self.f_gemini, values=["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash"], width=155, height=30, font=ctk.CTkFont(size=12),
            command=lambda _: self._save_all_configs()
        )
        self.cbo_gemini_model.pack(side="left")
        self.cbo_gemini_model.set("gemini-2.5-flash")

        # [B] Ollama 설정
        self.f_ollama = ctk.CTkFrame(self.engine_conf_frame, fg_color="transparent")
        ctk.CTkLabel(self.f_ollama, text="URL", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(0, 6))
        self.ent_ollama_url = ctk.CTkEntry(self.f_ollama, height=30, width=170, font=ctk.CTkFont(size=12))
        self.ent_ollama_url.pack(side="left", padx=(0, 6))
        self.ent_ollama_url.insert(0, "http://localhost:11434")
        self.ent_ollama_url.bind("<FocusOut>", lambda e: self._save_all_configs())

        btn_refresh_ollama = ctk.CTkButton(self.f_ollama, text="모델 조회", width=80, height=30, font=ctk.CTkFont(size=12), fg_color="#1f6aa5", command=self._refresh_ollama_models)
        btn_refresh_ollama.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(self.f_ollama, text="모델", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(0, 6))
        self.cbo_ollama_model = ctk.CTkComboBox(
            self.f_ollama, values=["qwen3-vl:4b", "gemma3:12b", "llava", "qwen2.5:7b"], width=155, height=30, font=ctk.CTkFont(size=12),
            command=lambda _: self._save_all_configs()
        )
        self.cbo_ollama_model.pack(side="left")
        self.cbo_ollama_model.set("qwen3-vl:4b")

        # 2. 본문 2분할 (좌: 입력 및 카탈로그 / 우: 생성 코드)
        body = ctk.CTkFrame(self, corner_radius=6)
        body.pack(fill="both", expand=True, padx=6, pady=2)
        body.grid_columnconfigure(0, weight=1, minsize=520)
        body.grid_columnconfigure(1, weight=1, minsize=500)
        body.grid_rowconfigure(0, weight=1)

        # ---------------------------------------------------------------------
        # 좌측 패널
        # ---------------------------------------------------------------------
        left_f = ctk.CTkFrame(body, corner_radius=6)
        left_f.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")

        # [섹션 1] 타겟 이미지
        s1_head = ctk.CTkFrame(left_f, fg_color="transparent")
        s1_head.pack(fill="x", padx=8, pady=(4, 2))
        ctk.CTkLabel(s1_head, text="타겟 화면 이미지", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")

        cap_bar = ctk.CTkFrame(left_f, fg_color="transparent")
        cap_bar.pack(fill="x", padx=8, pady=(0, 2))

        btn_paste_clip = ctk.CTkButton(
            cap_bar, text="붙여넣기", width=110, height=30,
            fg_color="#00695c", hover_color="#004d40", font=ctk.CTkFont(size=12, weight="bold"),
            command=self._paste_from_clipboard
        )
        btn_paste_clip.pack(side="left", padx=(0, 6))

        btn_cap_screen = ctk.CTkButton(
            cap_bar, text="화면 캡처", width=95, height=30,
            fg_color="#1f6aa5", hover_color="#144d75", font=ctk.CTkFont(size=12),
            command=self._capture_screen_now
        )
        btn_cap_screen.pack(side="left", padx=4)

        btn_browse_img = ctk.CTkButton(
            cap_bar, text="파일 선택", width=95, height=30,
            fg_color="#444444", hover_color="#333333", font=ctk.CTkFont(size=12),
            command=self._browse_image_file
        )
        btn_browse_img.pack(side="left", padx=4)

        self.frame_preview = ctk.CTkFrame(left_f, height=80, fg_color="#181818", corner_radius=6)
        self.frame_preview.pack(fill="x", padx=8, pady=2)
        self.lbl_img_preview = ctk.CTkLabel(
            self.frame_preview, text="이미지 미리보기 영역",
            font=ctk.CTkFont(size=12), text_color="#888888"
        )
        self.lbl_img_preview.pack(expand=True, pady=10)

        # [섹션 2] 대상 창 / URL / 브라우저 / DOM 카탈로그
        s2_head = ctk.CTkFrame(left_f, fg_color="transparent")
        s2_head.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(s2_head, text="대상 창 및 URL", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")

        # CDP 상태 표시 바
        cdp_bar = ctk.CTkFrame(left_f, fg_color="#1a1a2e", corner_radius=6)
        cdp_bar.pack(fill="x", padx=8, pady=(0, 4))

        self.lbl_cdp_status = ctk.CTkLabel(
            cdp_bar, text="● CDP 미연결", font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#888888", anchor="w"
        )
        self.lbl_cdp_status.pack(side="left", padx=(8, 6), pady=4)


        btn_cdp_launch = ctk.CTkButton(
            cdp_bar, text="Chrome CDP 바로가기 생성", width=180, height=26, font=ctk.CTkFont(size=12),
            fg_color="#1a3a5c", hover_color="#122a44", command=lambda: self._create_cdp_shortcut("chrome")
        )
        btn_cdp_launch.pack(side="left", padx=(0, 4), pady=4)

        btn_cdp_launch_edge = ctk.CTkButton(
            cdp_bar, text="Edge CDP 바로가기 생성", width=168, height=26, font=ctk.CTkFont(size=12),
            fg_color="#1a3a3a", hover_color="#122a2a", command=lambda: self._create_cdp_shortcut("edge")
        )
        btn_cdp_launch_edge.pack(side="left", padx=(0, 6), pady=4)

        # 윈도우 창 선택 드롭다운
        win_bar = ctk.CTkFrame(left_f, fg_color="transparent")
        win_bar.pack(fill="x", padx=8, pady=(0, 2))

        ctk.CTkLabel(win_bar, text="대상 창", font=ctk.CTkFont(size=12, weight="bold"), width=55).pack(side="left", padx=(0, 4))
        self.cbo_windows = ctk.CTkComboBox(win_bar, values=["(창 검색 중)"], height=30, font=ctk.CTkFont(size=12))
        self.cbo_windows.pack(side="left", fill="x", expand=True, padx=(0, 6))

        btn_refresh_wins = ctk.CTkButton(
            win_bar, text="창 갱신", width=75, height=30, font=ctk.CTkFont(size=12), fg_color="#333333",
            command=self._refresh_window_list
        )
        btn_refresh_wins.pack(side="right")

        # URL 입력 및 브라우저 선택 & 수집 버튼
        url_bar = ctk.CTkFrame(left_f, fg_color="transparent")
        url_bar.pack(fill="x", padx=8, pady=(2, 2))

        ctk.CTkLabel(url_bar, text="대상 URL", font=ctk.CTkFont(size=12, weight="bold"), width=55).pack(side="left", padx=(0, 4))
        self.ent_target_url = ctk.CTkEntry(
            url_bar, height=30, font=ctk.CTkFont(size=12), placeholder_text="예: http://175.119.156.105:3000/contract/list"
        )
        self.ent_target_url.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.ent_target_url.bind("<FocusOut>", lambda e: self._save_all_configs())

        self.btn_harvest_dom = ctk.CTkButton(
            url_bar, text="DOM 수집", width=105, height=30,
            fg_color="#1f6aa5", hover_color="#144d75", font=ctk.CTkFont(size=12, weight="bold"),
            command=self._start_harvest_dom
        )
        self.btn_harvest_dom.pack(side="right")

        # 브라우저 선택 옵션 바
        browser_bar = ctk.CTkFrame(left_f, fg_color="transparent")
        browser_bar.pack(fill="x", padx=8, pady=(2, 2))

        ctk.CTkLabel(browser_bar, text="브라우저", font=ctk.CTkFont(size=12, weight="bold"), width=55).pack(side="left", padx=(0, 4))
        self.seg_browser = ctk.CTkSegmentedButton(
            browser_bar, values=["Chrome", "Edge", "기본"],
            font=ctk.CTkFont(size=11, weight="bold"),
            command=lambda _: self._save_all_configs()
        )
        self.seg_browser.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.seg_browser.set("Chrome")

        # 유형별 조작 객체 탭뷰
        self.lbl_dom_status = ctk.CTkLabel(
            left_f, text="조작 객체 목록",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#aaaaaa", anchor="w"
        )
        self.lbl_dom_status.pack(fill="x", padx=8, pady=(4, 0))

        self.tabview_dom = ctk.CTkTabview(left_f, height=180)
        self.tabview_dom.pack(fill="both", expand=True, padx=8, pady=(1, 2))

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

        # ── [섹션 K] Keep 목록 패널 ──────────────────────────────────────────────
        keep_head = ctk.CTkFrame(left_f, fg_color="transparent")
        keep_head.pack(fill="x", padx=8, pady=(4, 1))
        ctk.CTkLabel(keep_head, text="Keep 목록", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        ctk.CTkButton(
            keep_head, text="전체 삭제", width=70, height=24,
            font=ctk.CTkFont(size=11), fg_color="#5a2d2d", hover_color="#7a1a1a",
            command=self._clear_keep_list
        ).pack(side="right")

        self.frm_keep_panel = ctk.CTkScrollableFrame(left_f, height=110, fg_color="#1a1a1a", corner_radius=6)
        self.frm_keep_panel.pack(fill="x", padx=8, pady=(0, 4))

        ctk.CTkLabel(
            self.frm_keep_panel,
            text="Keep된 항목이 없습니다. 객체 카드의 [Keep ★] 버튼을 누르세요.",
            font=ctk.CTkFont(size=11), text_color="#555555"
        ).pack(pady=10)

        # [섹션 3] 요구사항 입력
        s3_head = ctk.CTkFrame(left_f, fg_color="transparent")
        s3_head.pack(fill="x", padx=8, pady=(2, 1))
        ctk.CTkLabel(s3_head, text="자동화 요구사항", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")

        self.txt_prompt = ctk.CTkTextbox(left_f, height=60, font=ctk.CTkFont(size=12))
        self.txt_prompt.pack(fill="x", padx=8, pady=(0, 2))
        self.txt_prompt.insert(
            "1.0",
            "아이디 입력창에 'admin', 비밀번호에 '1234'를 입력하고 로그인 버튼을 클릭."
        )

        # 변수 삽입 칩 버튼 영역 (Keep 아이템 추가 시 동적 생성)
        self.frm_var_chips = ctk.CTkFrame(left_f, fg_color="transparent")
        self.frm_var_chips.pack(fill="x", padx=8, pady=(0, 4))

        # 태스크 제목 + 빌드 타입
        task_meta = ctk.CTkFrame(left_f, fg_color="transparent")
        task_meta.pack(fill="x", padx=8, pady=(0, 2))

        ctk.CTkLabel(task_meta, text="태스크 제목", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(0, 6))
        self.ent_task_title = ctk.CTkEntry(task_meta, height=28, font=ctk.CTkFont(size=11), placeholder_text="예: 계약 목록 검색 및 필터링")
        self.ent_task_title.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.var_build_type = ctk.StringVar(value="debug")
        ctk.CTkRadioButton(task_meta, text="DEBUG", variable=self.var_build_type, value="debug",
                           font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 6))
        ctk.CTkRadioButton(task_meta, text="RELEASE", variable=self.var_build_type, value="release",
                           font=ctk.CTkFont(size=11), text_color="#ffd54f").pack(side="left")

        # 실행 버튼
        self.btn_generate = ctk.CTkButton(
            left_f, text="코드 생성", height=38,
            fg_color="#00838f", hover_color="#006064", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._start_ai_generation
        )
        self.btn_generate.pack(fill="x", padx=8, pady=(2, 6))

        # ---------------------------------------------------------------------
        # 우측 패널: 생성 코드 뷰어
        # ---------------------------------------------------------------------
        right_f = ctk.CTkFrame(body, corner_radius=6)
        right_f.grid(row=0, column=1, padx=(0, 6), pady=6, sticky="nsew")

        r_head = ctk.CTkFrame(right_f, fg_color="transparent")
        r_head.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(r_head, text="생성 코드", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")

        self.txt_result_code = ctk.CTkTextbox(
            right_f, font=ctk.CTkFont(family="Consolas", size=13), fg_color="#181818"
        )
        self.txt_result_code.pack(fill="both", expand=True, padx=8, pady=4)

        b_bar = ctk.CTkFrame(right_f, fg_color="transparent")
        b_bar.pack(fill="x", padx=8, pady=(4, 8))

        btn_insert = ctk.CTkButton(
            b_bar, text="스크립트 에디터 전송", width=170, height=36,
            fg_color="#2e7d32", hover_color="#1b5e20", font=ctk.CTkFont(size=12, weight="bold"),
            command=self._do_insert_editor
        )
        btn_insert.pack(side="left", padx=(0, 6))

        btn_add_bot = ctk.CTkButton(
            b_bar, text="봇 모듈 등록", width=150, height=36,
            fg_color="#6a1b9a", hover_color="#4a148c", font=ctk.CTkFont(size=12, weight="bold"),
            command=self._do_add_bot
        )
        btn_add_bot.pack(side="left", padx=4)

        btn_copy = ctk.CTkButton(
            b_bar, text="클립보드 복사", width=120, height=36,
            fg_color="#444444", hover_color="#333333", font=ctk.CTkFont(size=12), command=self._copy_result
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
        url = self.ent_target_url.get().strip()
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
        self.btn_harvest_dom.configure(text="수집 중...", state="disabled")
        self.lbl_dom_status.configure(text="객체 수집 중...", text_color="#ffb74d")

        def _worker():
            try:
                info = DOMHarvester.check_cdp_available()
                self.after(0, lambda i=info: self._on_cdp_check_done(i))
                res = DOMHarvester.harvest_live_dom(
                    url=url,
                    hwnd=target_hwnd,
                    window_title=selected_win_title,
                    browser_type=chosen_browser,
                    timeout_sec=15
                )
                self.after(0, lambda r=res: self._on_harvest_success(r))
            except Exception as e:
                self.after(0, lambda err=str(e): self._on_harvest_error(err))

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
            self.after(0, lambda i=info: self._on_cdp_check_done(i))

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

        for sf in self.scroll_frames.values():
            for w in sf.winfo_children():
                w.destroy()

        inputs = catalog.get("inputs", [])
        self._set_tab_title(self.tab_inputs, f"입력창 ({len(inputs)})")
        for itm in inputs:
            self._render_element_card(self.scroll_frames["inputs"], itm, icon="[입력]")

        buttons = catalog.get("buttons", [])
        self._set_tab_title(self.tab_buttons, f"버튼 ({len(buttons)})")
        for itm in buttons:
            self._render_element_card(self.scroll_frames["buttons"], itm, icon="[버튼]")

        selects = catalog.get("selects", [])
        self._set_tab_title(self.tab_selects, f"드롭다운 ({len(selects)})")
        for itm in selects:
            self._render_element_card(self.scroll_frames["selects"], itm, icon="[선택]")

        checks = catalog.get("checks_radios", [])
        self._set_tab_title(self.tab_checks, f"체크/라디오 ({len(checks)})")
        for itm in checks:
            self._render_element_card(self.scroll_frames["checks_radios"], itm, icon="[체크]")

        grids = catalog.get("grids", [])
        self._set_tab_title(self.tab_grids, f"그리드 ({len(grids)})")
        for itm in grids:
            self._render_element_card(self.scroll_frames["grids"], itm, icon="[그리드]")

        links = catalog.get("links", [])
        self._set_tab_title(self.tab_links, f"링크 ({len(links)})")
        for itm in links:
            self._render_element_card(self.scroll_frames["links"], itm, icon="[링크]")

    def _set_tab_title(self, tab, new_title):
        try:
            for btn in self.tabview_dom._segmented_button._buttons_dict.values():
                if btn.cget("text").split(" ")[0] == new_title.split(" ")[0]:
                    btn.configure(text=new_title)
                    break
        except Exception:
            pass

    def _render_element_card(self, parent_frame, itm: Dict[str, Any], icon: str = ""):
        name = itm.get("label") or itm.get("text") or itm.get("type") or "요소"
        path = itm.get("path") or ""
        raw_html = itm.get("html") or ""
        sel = itm.get("selector") or ""
        code = itm.get("playwrightCode") or ""

        card = ctk.CTkFrame(parent_frame, corner_radius=6, fg_color="#2b2b2b")
        card.pack(fill="x", pady=3, padx=2)

        # 1행: 아이콘 + 라벨명 + [HTML 보기] + [선택]
        top_r = ctk.CTkFrame(card, fg_color="transparent")
        top_r.pack(fill="x", padx=8, pady=(5, 2))

        ctk.CTkLabel(
            top_r, text=f"{icon} {name}", font=ctk.CTkFont(size=12, weight="bold"), text_color="#ffffff", anchor="w"
        ).pack(side="left", fill="x", expand=True)

        if raw_html:
            btn_html = ctk.CTkButton(
                top_r, text="HTML 보기", width=75, height=26, font=ctk.CTkFont(size=11),
                fg_color="#444444", hover_color="#333333",
                command=lambda: self._show_element_html(name, raw_html, sel)
            )
            btn_html.pack(side="right", padx=(4, 2))

        btn_keep = ctk.CTkButton(
            top_r, text="Keep ★", width=70, height=26, font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#7b5800", hover_color="#a07000",
            command=lambda i=itm: self._on_keep_item(i)
        )
        btn_keep.pack(side="right", padx=2)

        # 2행: 3~4단계 상위 조상 계층 텍스트 경로 (존재 시)
        if path and path != name:
            mid_r = ctk.CTkFrame(card, fg_color="transparent")
            mid_r.pack(fill="x", padx=8, pady=(0, 2))
            ctk.CTkLabel(
                mid_r, text=f"경로: {path}", font=ctk.CTkFont(size=11), text_color="#b0bec5", anchor="w"
            ).pack(side="left", fill="x", expand=True)

        # 3행: 추천 셀렉터
        bot_r = ctk.CTkFrame(card, fg_color="transparent")
        bot_r.pack(fill="x", padx=8, pady=(0, 5))

        ctk.CTkLabel(
            bot_r, text=f"셀렉터: {sel}", font=ctk.CTkFont(family="Consolas", size=12), text_color="#64b5f6", anchor="w"
        ).pack(side="left", fill="x", expand=True)

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
        """객체를 Keep 목록에 추가 (이미 있으면 제거 토글)"""
        sel = itm.get("selector") or ""
        if not sel:
            return
        existing_idx = next(
            (i for i, k in enumerate(self.keep_list) if k["selector"] == sel), -1
        )
        if existing_idx >= 0:
            self.keep_list.pop(existing_idx)
        else:
            self.keep_list.append({
                "var_name": self._make_var_name(itm),
                "label": itm.get("label") or itm.get("text") or "요소",
                "selector": sel,
                "element_type": itm.get("type") or "element",
                "path": itm.get("path") or ""
            })
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
            row = ctk.CTkFrame(self.frm_keep_panel, fg_color="#252525", corner_radius=4)
            row.pack(fill="x", pady=2, padx=2)

            ctk.CTkLabel(
                row, text=f"  {{{item['var_name']}}}",
                font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
                text_color="#ffd54f", anchor="w"
            ).pack(side="left", fill="x", expand=True)

            if item.get("path"):
                ctk.CTkLabel(
                    row, text=item["path"][:30],
                    font=ctk.CTkFont(size=10), text_color="#888888"
                ).pack(side="left", padx=(0, 6))

            def _rename(i=idx):
                self._rename_keep_item(i)
            ctk.CTkButton(
                row, text="✏", width=28, height=22, font=ctk.CTkFont(size=11),
                fg_color="#333333", hover_color="#444444", command=_rename
            ).pack(side="right", padx=(2, 0))

            def _del(i=idx):
                self.keep_list.pop(i)
                self._render_keep_list()
                self._render_var_chips()
            ctk.CTkButton(
                row, text="✕", width=28, height=22, font=ctk.CTkFont(size=11),
                fg_color="#5a2d2d", hover_color="#7a1a1a", command=_del
            ).pack(side="right", padx=2)

    def _rename_keep_item(self, idx: int):
        """Keep 아이템 변수명 수정 팝업"""
        item = self.keep_list[idx]
        pop = ctk.CTkToplevel(self)
        pop.title("변수명 수정")
        pop.geometry("360x120")
        pop.attributes("-topmost", True)
        ctk.CTkLabel(pop, text="변수명:", font=ctk.CTkFont(size=12)).pack(pady=(14, 4))
        ent = ctk.CTkEntry(pop, font=ctk.CTkFont(family="Consolas", size=13), width=280)
        ent.insert(0, item["var_name"])
        ent.pack()
        def _apply():
            new_name = ent.get().strip()
            if new_name:
                item["var_name"] = new_name
                self._render_keep_list()
                self._render_var_chips()
            pop.destroy()
        ctk.CTkButton(pop, text="적용", width=100, height=30, command=_apply).pack(pady=8)

    def _clear_keep_list(self):
        """Keep 목록 전체 삭제"""
        self.keep_list.clear()
        self._render_keep_list()
        self._render_var_chips()

    def _render_var_chips(self):
        """요구사항 텍스트박스 아래 변수 삽입 칩 버튼 갱신"""
        for w in self.frm_var_chips.winfo_children():
            w.destroy()
        for item in self.keep_list:
            var = item["var_name"]
            def _insert(v=var):
                self._insert_var_token(v)
            ctk.CTkButton(
                self.frm_var_chips, text=f"{{{var}}}",
                height=24, font=ctk.CTkFont(family="Consolas", size=11),
                fg_color="#37474f", hover_color="#546e7a", command=_insert
            ).pack(side="left", padx=2, pady=2)

    def _insert_var_token(self, var_name: str):
        """요구사항 텍스트박스 커서 위치에 {변수명} 삽입"""
        try:
            idx = self.txt_prompt.index("insert")
        except Exception:
            idx = "end"
        self.txt_prompt.insert(idx, f"{{{var_name}}}")
        self.txt_prompt.focus()

    def _build_ai_prompt_with_keep(self, user_prompt: str) -> str:
        """Keep 목록을 포함한 확장 프롬프트 생성"""
        if not self.keep_list:
            return user_prompt
        lines = ["[고정 참조 객체]"]
        for item in self.keep_list:
            lines.append(f"  {{{item['var_name']}}} = selector: \"{item['selector']}\"")
        lines.append("")
        lines.append("[요구사항]")
        lines.append(user_prompt)
        lines.append("")
        lines.append("위 [고정 참조 객체]의 변수명을 실제 셀렉터로 대응시켜 Playwright 코드를 작성하십시오.")
        return "\n".join(lines)


    def _on_harvest_error(self, err_msg: str):
        self.btn_harvest_dom.configure(text="DOM 수집", state="normal")
        self.lbl_dom_status.configure(text="DOM 수집 실패", text_color="#e57373")
        messagebox.showerror("DOM 수집 오류", f"수집 실패:\n{err_msg}")


    # =========================================================================
    # [섹션 1] 이미지
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
                messagebox.showinfo("붙여넣기", "스크린샷 이미지가 로드되었습니다.")
                return
            elif isinstance(clip_data, list) and len(clip_data) > 0 and os.path.exists(clip_data[0]):
                p = clip_data[0]
                if p.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    self.current_image_path = p
                    self._display_preview_image(p)
                    messagebox.showinfo("파일 로드", f"이미지 파일이 로드되었습니다:\n{p}")
                    return

            messagebox.showwarning("안내", "클립보드에 이미지가 없습니다.")
        except Exception as e:
            messagebox.showerror("오류", f"이미지 처리 실패: {e}")

    def _capture_screen_now(self):
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
            messagebox.showerror("오류", f"캡처 실패: {e}")
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
            pil_img.thumbnail((380, 75))
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)

            self.lbl_img_preview.configure(image=ctk_img, text="")
            self.lbl_img_preview.image = ctk_img
        except Exception as ex:
            self.lbl_img_preview.configure(text=f"미리보기 실패: {ex}")

    # =========================================================================
    # AI 코드 생성
    # =========================================================================
    def _start_ai_generation(self):
        image_valid = self.current_image_path and os.path.exists(self.current_image_path)
        img_path_arg = self.current_image_path if image_valid else None

        prompt = self.txt_prompt.get("1.0", "end").strip()
        if not prompt:
            messagebox.showwarning("입력 확인", "자동화 요구사항을 입력하십시오.")
            return

        target_url = self.ent_target_url.get().strip() or self.cbo_windows.get()
        chosen_browser = "Chrome"
        catalog_summary = DOMHarvester.format_catalog_to_text(self.current_catalog)
        # Keep 목록이 있으면 확장 프롬프트로 교체
        prompt = self._build_ai_prompt_with_keep(prompt)
        engine_choice = self.seg_engine.get()

        self._save_all_configs()

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
                    self.after(0, lambda c=code, f=full_text: self._on_generation_success(c, f, "Gemini"))
                except Exception as e:
                    self.after(0, lambda err=str(e): self._on_generation_error(err))

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
                    self.after(0, lambda c=code, f=full_text: self._on_generation_success(c, f, f"Ollama ({model})"))
                except Exception as e:
                    self.after(0, lambda err=str(e): self._on_generation_error(err))

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
                status="draft"
            )
            self.db.touch_project(pid)
            print(f"[DB] 태스크 저장 완료 task_id={task_id}")
        except Exception as e:
            print(f"[DB] 태스크 저장 실패: {e}")

    def _update_project_bar(self):
        """프로젝트 컨텍스트 바 라벨 갱신"""
        try:
            if self.current_project:
                self.lbl_proj_name.configure(
                    text=f"프로젝트: {self.current_project['name']}",
                    text_color="#4caf50"
                )
            else:
                self.lbl_proj_name.configure(text="[오프라인]", text_color="#888888")
        except Exception:
            pass

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
    def _load_saved_configs(self):
        k = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
        ollama_u = "http://localhost:11434"
        target_u = "http://175.119.156.105:3000/contract/list"
        last_engine = "Google Gemini"
        last_gemini_model = "gemini-2.5-flash"
        last_ollama_model = "qwen3-vl:4b"
        last_browser = "Chrome"

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
                        last_browser = cfg.get("last_browser_choice", last_browser)
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

        if last_browser in ["Chrome", "Edge", "기본"]:
            self.seg_browser.set(last_browser)

    def _save_all_configs(self):
        data_to_save = {
            "gemini_api_key": self.ent_api_key.get().strip(),
            "ollama_url": self.ent_ollama_url.get().strip(),
            "target_url": self.ent_target_url.get().strip(),
            "last_ai_engine": self.seg_engine.get(),
            "last_gemini_model": self.cbo_gemini_model.get(),
            "last_ollama_model": self.cbo_ollama_model.get(),
            "last_browser_choice": "Chrome"
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

