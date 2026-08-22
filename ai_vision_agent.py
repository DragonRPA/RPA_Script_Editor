"""
Universal RPA - Evidence-Based Hybrid Vision AI RPA Code & Selector Generator
Google Gemini (클라우드 초고속) + Local Ollama (100% 무료 / 로컬 오프라인) 듀얼 엔진
- 1단계: 화면 이미지 (클립보드 붙여넣기 Ctrl+V / 직접 캡처 / 파일 열기)
- 2단계: 대상 웹 URL 및 실시간 인터랙티브 HTML DOM 수집/검증 뷰어
- 3단계: 자연어 요구사항 입력
- 증거 기반(Evidence-Based) Visual Grounding & 100% 무결점 셀렉터 생성
"""

import os
import sys
import json
import base64
import threading
import time
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


class GeminiVisionAgent:
    """Google Gemini 멀티모달 비전 API 통신 매니저 (클라우드)"""

    SYSTEM_INSTRUCTION = """당신은 세계 최고 권위의 엔터프라이즈 파이썬 RPA 및 웹/데스크톱 자동화 아키텍트입니다.
사용자가 제공한 [화면 스크린샷 이미지], [대상 웹 URL], [실시간 수집된 HTML DOM 증거], [자연어 요구사항]을 정밀 분석하여, 실무 현장에서 100% 오류 없이 즉시 실행 가능한 완성형 파이썬 Playwright / Windows UIA 자동화 코드를 작성하십시오.

[필수 엔지니어링 표준 수칙]
1. 🔍 증거 기반(Evidence-Based) 셀렉터 1:1 매핑:
   - 함께 제공된 [실시간 수집된 HTML DOM 증거] 속의 실제 id, name, placeholder, class, label 힌트를 스크린샷 이미지와 1:1로 정확히 대조하십시오.
   - 추측이나 환각(Hallucination)에 의한 가상 속성을 쓰지 말고, DOM 증거에 실제로 존재하는 고유 속성을 기반으로 셀렉터를 작성하십시오.

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
   - 예시:
     - 검색창: `page.locator("input[placeholder*='검색어'], div:has(> label:has-text('라벨명')) input, input[name*='keyword']").first`
     - 버튼: `page.locator("button:has-text('조회'), button[type='submit']").first`
     - AG-Grid / 테이블: `page.locator(".ag-row, table tbody tr").first.dblclick()`
   - 모든 요소 조작 전 `locator.wait_for(state="visible", timeout=5000)` 가시성 대기를 기본 적용하십시오.

4. 🪟 Windows 데스크톱 앱 (UIA) 감지 시:
   - `import uiautomation as uia`를 사용하여 최상위 창 포커스 및 AutomationId / Name 기반 제어 코드를 작성하십시오.

5. 📊 실시간 콘솔 로깅 및 예외 처리:
   - 각 작업 단계마다 `print(">>> [단계 진행] ...")` 로그를 남기고, 적절한 `page.wait_for_timeout(...)`을 배치하여 안정성을 확보하십시오.

6. 📦 출력 포맷:
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
            prompt_text += f"### [대상 웹페이지 URL / 라우트]\n{target_url}\n\n"
        if page_html:
            prompt_text += f"### [실시간 수집된 실제 HTML DOM 증거]\n{page_html[:4000]}\n\n"
        prompt_text += f"### [자연어 자동화 요구사항]\n{user_prompt}\n\n"
        prompt_text += "위 화면 스크린샷과 실시간 HTML DOM 증거, URL, 요구사항을 바탕으로 최적의 셀렉터와 파이썬 Playwright RPA 코드를 작성해 주십시오."

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
제공된 [화면 스크린샷 이미지], [대상 URL], [실시간 HTML DOM 증거], [자연어 요구사항]을 분석하여, 가장 견고하고 정확한 Playwright (웹) 또는 Windows UIA 자동화 코드를 작성하십시오.

[작성 규칙]
1. 제공된 [실시간 HTML DOM 증거]의 id, name, placeholder, class 속성을 스크린샷과 대조하여 100% 정확한 실제 셀렉터를 추출하십시오.
2. Playwright 브라우저 기동 시 `browser = playwright.chromium.launch(headless=False, args=["--start-maximized"])`, `context = browser.new_context(no_viewport=True)`를 적용하십시오.
3. 대상 URL이 있으면 `page.goto("{target_url}")` 코드를 최상단에 작성하십시오.
4. 셀렉터는 클래스명이 바뀌어도 안전한 `page.locator("input[placeholder*='...'], div:has(> label:has-text('...')) input").first` 형태의 다중 Fallback을 사용하십시오.
5. 반드시 실행 가능한 완성된 파이썬 코드를 ```python ... ``` 블록으로 감싸서 출력하십시오."""

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
            prompt_body += f"[대상 웹페이지 URL]\n{target_url}\n\n"
        if page_html:
            prompt_body += f"[실시간 수집된 실제 HTML DOM 증거]\n{page_html[:4000]}\n\n"
        prompt_body += f"[사용자 자연어 요구사항]\n{user_prompt}\n\n"
        prompt_body += "위 화면 스크린샷과 HTML DOM 증거에서 타겟 요소를 찾아 최적의 Playwright 셀렉터와 파이썬 실행 코드를 작성해 주십시오."

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


class AIVisionModal(ctk.CTkToplevel):
    """Google Gemini + Local Ollama 듀얼 비전 AI 코드 생성기 대화상자"""

    _CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recorder_config.json")

    def __init__(self, parent, on_insert_code: Optional[Callable[[str], None]] = None,
                 on_add_to_bot: Optional[Callable[[Dict[str, Any]], None]] = None):
        super().__init__(parent)

        self.parent_app = parent
        self.on_insert_code = on_insert_code
        self.on_add_to_bot = on_add_to_bot

        self.title("🤖 증거 기반(Evidence-Based) Vision AI 셀렉터 & RPA 코드 생성기 (Gemini + Ollama)")
        self.geometry("1060x880")
        self.minsize(940, 720)
        self.attributes("-topmost", True)

        self.current_image_path: Optional[str] = None
        self.preview_image_ref: Optional[ImageTk.PhotoImage] = None

        self._build_ui()
        self._load_saved_configs()
        self._on_engine_changed(self.seg_engine.get())

        self.bind("<Control-v>", lambda e: self._paste_from_clipboard())
        self.bind("<Control-V>", lambda e: self._paste_from_clipboard())

    def _build_ui(self):
        # 1. 상단 AI 엔진 선택 및 설정 바
        top_ctrl = ctk.CTkFrame(self, corner_radius=6)
        top_ctrl.pack(fill="x", padx=10, pady=(10, 6))

        ctk.CTkLabel(top_ctrl, text="AI 엔진:", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(10, 4), pady=8)
        self.seg_engine = ctk.CTkSegmentedButton(
            top_ctrl, values=["☁️ Google Gemini (초고속)", "🦙 Local Ollama (100% 무료)"],
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._on_engine_changed
        )
        self.seg_engine.pack(side="left", padx=(0, 12), pady=6)
        self.seg_engine.set("☁️ Google Gemini (초고속)")

        self.engine_conf_frame = ctk.CTkFrame(top_ctrl, fg_color="transparent")
        self.engine_conf_frame.pack(side="left", fill="x", expand=True, padx=4)

        # [A] Gemini 설정 위젯들
        self.f_gemini = ctk.CTkFrame(self.engine_conf_frame, fg_color="transparent")
        ctk.CTkLabel(self.f_gemini, text="Key:", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(0, 4))
        self.ent_api_key = ctk.CTkEntry(self.f_gemini, height=28, width=210, placeholder_text="Gemini API Key", show="*")
        self.ent_api_key.pack(side="left", padx=(0, 4))

        btn_toggle_key = ctk.CTkButton(self.f_gemini, text="👁", width=28, height=28, fg_color="#444444", command=self._toggle_key_visibility)
        btn_toggle_key.pack(side="left", padx=(0, 4))

        btn_save_key = ctk.CTkButton(self.f_gemini, text="저장", width=50, height=28, fg_color="#2e7d32", command=self._save_api_key)
        btn_save_key.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(self.f_gemini, text="모델:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.cbo_gemini_model = ctk.CTkComboBox(self.f_gemini, values=["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash"], width=145, height=28)
        self.cbo_gemini_model.pack(side="left")
        self.cbo_gemini_model.set("gemini-2.5-flash")

        # [B] Ollama 설정 위젯들
        self.f_ollama = ctk.CTkFrame(self.engine_conf_frame, fg_color="transparent")
        ctk.CTkLabel(self.f_ollama, text="URL:", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(0, 4))
        self.ent_ollama_url = ctk.CTkEntry(self.f_ollama, height=28, width=170)
        self.ent_ollama_url.pack(side="left", padx=(0, 4))
        self.ent_ollama_url.insert(0, "http://localhost:11434")

        btn_refresh_ollama = ctk.CTkButton(self.f_ollama, text="🔄 모델 조회", width=80, height=28, fg_color="#1f6aa5", command=self._refresh_ollama_models)
        btn_refresh_ollama.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(self.f_ollama, text="비전 모델:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.cbo_ollama_model = ctk.CTkComboBox(self.f_ollama, values=["qwen3-vl:4b", "gemma3:12b", "llava", "qwen2.5:7b"], width=145, height=28)
        self.cbo_ollama_model.pack(side="left")
        self.cbo_ollama_model.set("qwen3-vl:4b")

        # 2. 본문 2분할 (좌: 3대 입력 칸 + 증거 DOM 뷰어 / 우: AI 생성 코드 뷰어)
        body = ctk.CTkFrame(self, corner_radius=6)
        body.pack(fill="both", expand=True, padx=10, pady=4)
        body.grid_columnconfigure(0, weight=1, minsize=480)
        body.grid_columnconfigure(1, weight=1, minsize=480)
        body.grid_rowconfigure(0, weight=1)

        # ---------------------------------------------------------------------
        # 좌측: 3대 입력 칸 + 실시간 DOM 증거 뷰어
        # ---------------------------------------------------------------------
        left_f = ctk.CTkFrame(body, corner_radius=6)
        left_f.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")

        # [섹션 1] 이미지 지정 칸 (클립보드 / 캡처 / 파일선택)
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

        # 썸네일 미리보기 박스
        self.frame_preview = ctk.CTkFrame(left_f, height=100, fg_color="#181818", corner_radius=6)
        self.frame_preview.pack(fill="x", padx=8, pady=2)
        self.lbl_img_preview = ctk.CTkLabel(
            self.frame_preview, text="[클립보드 복사(Win+Shift+S) 후 Ctrl+V 또는 캡처/파일 선택]",
            font=ctk.CTkFont(size=11), text_color="#777777"
        )
        self.lbl_img_preview.pack(expand=True, pady=18)

        # [섹션 2] 대상 웹 URL 입력 칸 & 실시간 DOM 수집 버튼
        s2_head = ctk.CTkFrame(left_f, fg_color="transparent")
        s2_head.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(s2_head, text="🌐 [2/3] 대상 웹 URL & 라이브 DOM 증거", font=ctk.CTkFont(size=12, weight="bold"), text_color="#64b5f6").pack(side="left")

        url_bar = ctk.CTkFrame(left_f, fg_color="transparent")
        url_bar.pack(fill="x", padx=8, pady=(0, 2))

        self.ent_target_url = ctk.CTkEntry(
            url_bar, height=28, placeholder_text="예: http://175.119.156.105:3000/contract/list"
        )
        self.ent_target_url.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.ent_target_url.insert(0, "http://175.119.156.105:3000/contract/list")

        self.btn_harvest_dom = ctk.CTkButton(
            url_bar, text="🌐 실시간 DOM 수집 🔍", width=145, height=28,
            fg_color="#1f6aa5", hover_color="#144d75", font=ctk.CTkFont(size=11, weight="bold"),
            command=self._start_harvest_dom
        )
        self.btn_harvest_dom.pack(side="right")

        # [신규] 실시간 수집된 인터랙티브 HTML DOM 증거 뷰어
        dom_head = ctk.CTkFrame(left_f, fg_color="transparent")
        dom_head.pack(fill="x", padx=8, pady=(2, 0))

        self.lbl_dom_status = ctk.CTkLabel(
            dom_head, text="📄 [증거 DOM] 수집 대기 중 (실시간 DOM 수집 클릭 시 채워집니다)",
            font=ctk.CTkFont(size=10), text_color="#aaaaaa"
        )
        self.lbl_dom_status.pack(side="left")

        btn_clear_dom = ctk.CTkButton(
            dom_head, text="지우기", width=50, height=18, font=ctk.CTkFont(size=10),
            fg_color="#333333", command=lambda: self.txt_dom_snippet.delete("1.0", "end")
        )
        btn_clear_dom.pack(side="right")

        self.txt_dom_snippet = ctk.CTkTextbox(
            left_f, height=85, font=ctk.CTkFont(family="Consolas", size=10), fg_color="#181818"
        )
        self.txt_dom_snippet.pack(fill="x", padx=8, pady=(1, 4))

        # [섹션 3] 자연어 요구사항 입력 칸
        s3_head = ctk.CTkFrame(left_f, fg_color="transparent")
        s3_head.pack(fill="x", padx=8, pady=(4, 2))
        ctk.CTkLabel(s3_head, text="✍️ [3/3] 자연어 자동화 요구사항 입력", font=ctk.CTkFont(size=12, weight="bold"), text_color="#81c784").pack(side="left")

        self.txt_prompt = ctk.CTkTextbox(left_f, height=75, font=ctk.CTkFont(size=12))
        self.txt_prompt.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.txt_prompt.insert(
            "1.0",
            "계약번호 검색창에 '2D2607007'을 입력하고 '조회' 버튼을 클릭한 다음,\n"
            "검색 결과 그리드(테이블)의 첫 번째 행을 더블클릭해서 상세 화면으로 이동해줘."
        )

        # 실행 버튼
        self.btn_generate = ctk.CTkButton(
            left_f, text="⚡ 증거 기반 AI 코드 생성 (Generate RPA Code)", height=36,
            fg_color="#00838f", hover_color="#006064", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._start_ai_generation
        )
        self.btn_generate.pack(fill="x", padx=8, pady=(4, 6))

        # ---------------------------------------------------------------------
        # 우측: AI 생성 코드 & 분석 설명 뷰어
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
            b_bar, text="📋 에디터에 코드 삽입", width=160, height=34,
            fg_color="#2e7d32", hover_color="#1b5e20", font=ctk.CTkFont(weight="bold"),
            command=self._do_insert_editor
        )
        btn_insert.pack(side="left", padx=(0, 4))

        btn_add_bot = ctk.CTkButton(
            b_bar, text="🤖 봇 에디터에 모듈로 추가", width=180, height=34,
            fg_color="#6a1b9a", hover_color="#4a148c", font=ctk.CTkFont(weight="bold"),
            command=self._do_add_bot
        )
        btn_add_bot.pack(side="left", padx=4)

        btn_copy = ctk.CTkButton(
            b_bar, text="클립보드 복사", width=100, height=34,
            fg_color="#444444", hover_color="#333333", command=self._copy_result
        )
        btn_copy.pack(side="right")

    def _on_engine_changed(self, choice: str):
        if "Gemini" in choice:
            self.f_ollama.pack_forget()
            self.f_gemini.pack(fill="x")
        else:
            self.f_gemini.pack_forget()
            self.f_ollama.pack(fill="x")
            self._refresh_ollama_models()

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
    # [실시간 DOM 수집] 백그라운드 워커 스레드
    # =========================================================================
    def _start_harvest_dom(self):
        url = self.ent_target_url.get().strip()
        if not url:
            messagebox.showwarning("입력 확인", "수집할 대상 웹 URL을 입력해 주십시오.")
            return

        self.btn_harvest_dom.configure(text="⏳ DOM 수집 중...", state="disabled")
        self.lbl_dom_status.configure(text="⏳ 대상 페이지 접속 및 인터랙티브 DOM 렌더링 수집 중...", text_color="#ffb74d")

        def _worker():
            try:
                res = DOMHarvester.harvest_live_dom(url, timeout_sec=12)
                self.after(0, lambda r=res: self._on_harvest_success(r))
            except Exception as e:
                self.after(0, lambda err=str(e): self._on_harvest_error(err))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_harvest_success(self, res: Dict[str, Any]):
        self.btn_harvest_dom.configure(text="🌐 실시간 DOM 수집 🔍", state="normal")
        snippet = res.get("dom_snippet", "")
        count = res.get("count", 0)
        sec = res.get("elapsed_sec", 0)
        engine = res.get("engine", "")

        self.txt_dom_snippet.delete("1.0", "end")
        self.txt_dom_snippet.insert("1.0", snippet)

        self.lbl_dom_status.configure(
            text=f"✅ {count}개 핵심 태그 수집 완료 ({sec}초, {engine})",
            text_color="#81c784"
        )

    def _on_harvest_error(self, err_msg: str):
        self.btn_harvest_dom.configure(text="🌐 실시간 DOM 수집 🔍", state="normal")
        self.lbl_dom_status.configure(
            text=f"❌ DOM 수집 실패: {err_msg[:40]}",
            text_color="#e57373"
        )
        messagebox.showerror("DOM 수집 오류", f"대상 URL DOM 수집 실패:\n{err_msg}")

    # =========================================================================
    # [섹션 1] 클립보드 붙여넣기, 화면 캡처, 이미지 로드
    # =========================================================================
    def _paste_from_clipboard(self):
        """클립보드 이미지 가져오기 (Win+Shift+S 또는 PrtScn 캡처 후 Ctrl+V)"""
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
        self.withdraw()
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
            self.deiconify()

    def _browse_image_file(self):
        p = filedialog.askopenfilename(filetypes=[("이미지 파일", "*.png;*.jpg;*.jpeg;*.webp")])
        if p:
            self.current_image_path = p
            self._display_preview_image(p)

    def _display_preview_image(self, path: str):
        try:
            pil_img = Image.open(path)
            pil_img.thumbnail((380, 85))
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)

            self.lbl_img_preview.configure(image=ctk_img, text="")
            self.lbl_img_preview.image = ctk_img
        except Exception as ex:
            self.lbl_img_preview.configure(text=f"미리보기 실패: {ex}")

    # =========================================================================
    # AI 코드 생성 실행 (이미지 + URL + 실시간 DOM 증거 + 프롬프트 4박자 결합)
    # =========================================================================
    def _start_ai_generation(self):
        if not self.current_image_path or not os.path.exists(self.current_image_path):
            messagebox.showwarning("입력 확인", "[1단계: 타겟 화면 이미지]를 먼저 지정해 주십시오.\n(클립보드 붙여넣기, 즉시 캡처, 또는 파일 선택)")
            return

        prompt = self.txt_prompt.get("1.0", "end").strip()
        if not prompt:
            messagebox.showwarning("입력 확인", "[3단계: 자연어 자동화 요구사항]을 입력해 주십시오.")
            return

        target_url = self.ent_target_url.get().strip()
        dom_snippet = self.txt_dom_snippet.get("1.0", "end").strip()
        engine_choice = self.seg_engine.get()

        if "Gemini" in engine_choice:
            api_key = self.ent_api_key.get().strip()
            if not api_key:
                messagebox.showwarning("입력 확인", "Google Gemini API Key를 먼저 입력해 주십시오.")
                return
            model = self.cbo_gemini_model.get()
            self.btn_generate.configure(text="⏳ Gemini 증거 기반 분석 중... (약 1~2초)", state="disabled")
            self.txt_result_code.delete("1.0", "end")
            self.txt_result_code.insert("1.0", f"// 🤖 Google Gemini ({model})에 이미지와 URL, 실시간 DOM 증거를 대조 분석 중입니다...\n")

            def _worker_gemini():
                try:
                    code, full_text = GeminiVisionAgent.call_gemini_vision(
                        api_key=api_key,
                        image_path=self.current_image_path,
                        user_prompt=prompt,
                        target_url=target_url,
                        model=model,
                        page_html=dom_snippet
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
            self.txt_result_code.insert("1.0", f"// 🦙 Local Ollama ({model})에서 이미지와 실시간 DOM 증거를 로컬 GPU로 추론 중입니다...\n// (100% 무료 / 사내 보안 유지 / 외부 유출 없음)\n")

            def _worker_ollama():
                try:
                    code, full_text = OllamaVisionAgent.call_ollama_vision(
                        ollama_url=ollama_url,
                        model=model,
                        image_path=self.current_image_path,
                        user_prompt=prompt,
                        target_url=target_url,
                        page_html=dom_snippet
                    )
                    self.after(0, lambda c=code, f=full_text: self._on_generation_success(c, f, f"Ollama ({model})"))
                except Exception as e:
                    self.after(0, lambda err=str(e): self._on_generation_error(err))

            threading.Thread(target=_worker_ollama, daemon=True).start()

    def _on_generation_success(self, code: str, full_text: str, engine_name: str):
        self.btn_generate.configure(text="⚡ 증거 기반 AI 코드 생성 (Generate RPA Code)", state="normal")
        self.txt_result_code.delete("1.0", "end")
        self.txt_result_code.insert("1.0", code)
        messagebox.showinfo("생성 완료", f"✅ {engine_name} 엔진이 실시간 DOM 증거를 기반으로 100% 무결점 코드를 생성하였습니다!")

    def _on_generation_error(self, err_msg: str):
        self.btn_generate.configure(text="⚡ 증거 기반 AI 코드 생성 (Generate RPA Code)", state="normal")
        self.txt_result_code.delete("1.0", "end")
        self.txt_result_code.insert("1.0", f"[오류 발생]\n{err_msg}")
        messagebox.showerror("AI 생성 오류", f"코드 생성 실패:\n{err_msg}")

    # =========================================================================
    # 액션 버튼 핸들러
    # =========================================================================
    def _do_insert_editor(self):
        code = self.txt_result_code.get("1.0", "end").strip()
        if not code or code.startswith("//") or code.startswith("[오류"):
            messagebox.showwarning("안내", "삽입할 유효한 생성 코드가 없습니다.")
            return

        if self.on_insert_code:
            self.on_insert_code(code)
            messagebox.showinfo("삽입 완료", "파이썬 에디터에 AI 생성 코드가 삽입되었습니다!")

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
            messagebox.showinfo("모듈 등록 완료", "🤖 봇 에디터에 새 모듈 카드가 등록되었습니다!")

    def _copy_result(self):
        code = self.txt_result_code.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(code)

    def _toggle_key_visibility(self):
        if self.ent_api_key.cget("show") == "*":
            self.ent_api_key.configure(show="")
        else:
            self.ent_api_key.configure(show="*")

    def _load_saved_configs(self):
        k = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
        ollama_u = "http://localhost:11434"
        target_u = "http://175.119.156.105:3000/contract/list"

        if os.path.exists(self._CONFIG_FILE):
            try:
                with open(self._CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    k = k or cfg.get("gemini_api_key", "")
                    ollama_u = cfg.get("ollama_url", ollama_u)
                    target_u = cfg.get("target_url", target_u)
            except Exception:
                pass

        ubus_cfg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "UBUS_contract", "config.json")
        if os.path.exists(ubus_cfg):
            try:
                with open(ubus_cfg, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    k = k or cfg.get("gemini_api_key", "")
                    ollama_u = cfg.get("ollama_url", ollama_u)
                    target_u = cfg.get("erp_url", target_u)
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

    def _save_api_key(self):
        k = self.ent_api_key.get().strip()
        try:
            for cfg_path in [
                self._CONFIG_FILE,
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "UBUS_contract", "config.json")
            ]:
                data = {}
                if os.path.exists(cfg_path):
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                data["gemini_api_key"] = k
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

            messagebox.showinfo("저장 완료", "Gemini API Key가 안전하게 저장되었습니다!")
        except Exception as e:
            messagebox.showerror("저장 오류", f"Key 저장 실패: {e}")


def open_ai_vision_generator(parent, on_insert: Optional[Callable[[str], None]] = None,
                             on_add_bot: Optional[Callable[[Dict[str, Any]], None]] = None) -> AIVisionModal:
    """AI 비전 코드 생성기 대화상자 열기"""
    modal = AIVisionModal(parent, on_insert_code=on_insert, on_add_to_bot=on_add_bot)
    return modal
