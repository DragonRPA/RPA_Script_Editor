"""
Google Gemini Multimodal Vision AI RPA Code & Selector Generator
화면 스크린샷 + 자연어 프롬프트를 분석하여 최적의 Playwright / Windows UIA 셀렉터 및 파이썬 코드를 자동 생성하는 AI 에이전트
"""

import os
import sys
import json
import base64
import threading
import time
from typing import Dict, Any, Optional, Tuple, Callable

import requests
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


class GeminiVisionAgent:
    """Google Gemini 멀티모달 비전 API 통신 매니저"""

    SYSTEM_INSTRUCTION = """당신은 세계 최고 수준의 파이썬 RPA 및 웹/데스크톱 자동화 엔지니어링 전문가입니다.
사용자가 제공한 화면 스크린샷 이미지와 자연어 요구사항을 분석하여, 가장 견고하고 정확한 Playwright (웹) 또는 Windows UIA (데스크톱) 자동화 코드를 작성해야 합니다.

[작성 규칙]
1. 시각적 위치 분석: 사용자가 지정한 입력창, 버튼, 테이블 그리드, 콤보박스, 체크박스의 시각적 위치와 주변 텍스트(라벨)를 정밀하게 파악하십시오.
2. 셀렉터 최적화:
   - Playwright: placeholder, role, text, label 연계 locator (예: page.locator("div:has(> label:has-text('계약번호')) input"), page.locator("button:has-text('조회')"), page.locator(".ag-row").first.dblclick())
   - 윈도우 앱: AutomationId, Name, ClassName 기반 uiautomation 코드
3. 코드 스타일: 즉시 실행 가능한 완성형 파이썬 코드로 작성하고, 핵심 셀렉터 추출 이유를 주석으로 친절히 설명하십시오.
4. 응답 포맷: 순수 파이썬 코드 블록(```python ... ```)과 함께 하단에 [추출된 셀렉터 분석 요약]을 첨부하십시오.
"""

    @classmethod
    def call_gemini_vision(cls, api_key: str, image_path: str, user_prompt: str,
                           model: str = "gemini-2.5-flash", page_html: str = "") -> Tuple[str, str]:
        """
        Gemini REST API v1beta를 통해 이미지 + 프롬프트로 코드 생성
        반환값: (generated_code, full_explanation)
        """
        if not api_key:
            raise ValueError("Google Gemini API Key가 설정되지 않았습니다.")

        if not os.path.exists(image_path):
            raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

        # 1. 이미지 Base64 인코딩
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        # MIME 타입 결정
        mime_type = "image/png"
        if image_path.lower().endswith(".jpg") or image_path.lower().endswith(".jpeg"):
            mime_type = "image/jpeg"
        elif image_path.lower().endswith(".webp"):
            mime_type = "image/webp"

        # 2. 페이로드 구성
        parts = [
            {
                "inline_data": {
                    "mime_type": mime_type,
                    "data": img_b64
                }
            },
            {
                "text": f"### [자연어 자동화 요구사항]\n{user_prompt}\n\n"
                        f"{f'### [참조 HTML/DOM 구조 스니펫]\n{page_html[:3000]}' if page_html else ''}\n"
                        f"위 화면 스크린샷과 요구사항을 바탕으로 최적의 셀렉터와 파이썬 Playwright RPA 코드를 작성해 주십시오."
            }
        ]

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "system_instruction": {
                "parts": [{"text": cls.SYSTEM_INSTRUCTION}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": parts
                }
            ],
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

        # 코드 블록 추출
        code = ""
        if "```python" in full_text:
            code = full_text.split("```python")[1].split("```")[0].strip()
        elif "```" in full_text:
            code = full_text.split("```")[1].split("```")[0].strip()
        else:
            code = full_text.strip()

        return code, full_text


class AIVisionModal(ctk.CTkToplevel):
    """Google Gemini Vision AI 코드 생성기 대화상자"""

    _CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recorder_config.json")

    def __init__(self, parent, on_insert_code: Optional[Callable[[str], None]] = None,
                 on_add_to_bot: Optional[Callable[[Dict[str, Any]], None]] = None):
        super().__init__(parent)

        self.parent_app = parent
        self.on_insert_code = on_insert_code
        self.on_add_to_bot = on_add_to_bot

        self.title("🤖 Google Gemini Vision AI 셀렉터 & RPA 코드 생성기")
        self.geometry("960x780")
        self.minsize(860, 640)
        self.attributes("-topmost", True)

        self.current_image_path: Optional[str] = None
        self.preview_image_ref: Optional[ImageTk.PhotoImage] = None

        self._build_ui()
        self._load_saved_api_key()

    def _build_ui(self):
        # 1. 상단 API Key 바
        api_bar = ctk.CTkFrame(self, corner_radius=6)
        api_bar.pack(fill="x", padx=10, pady=(10, 6))

        ctk.CTkLabel(api_bar, text="🔑 Gemini API Key:", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(10, 4), pady=8)
        self.ent_api_key = ctk.CTkEntry(api_bar, height=28, placeholder_text="AI Studio에서 발급받은 Gemini API Key 입력", show="*")
        self.ent_api_key.pack(side="left", fill="x", expand=True, padx=(0, 6), pady=6)

        btn_toggle_key = ctk.CTkButton(api_bar, text="👁", width=30, height=28, fg_color="#444444", command=self._toggle_key_visibility)
        btn_toggle_key.pack(side="left", padx=(0, 6), pady=6)

        btn_save_key = ctk.CTkButton(api_bar, text="Key 저장", width=80, height=28, fg_color="#2e7d32", hover_color="#1b5e20", command=self._save_api_key)
        btn_save_key.pack(side="left", padx=(0, 10), pady=6)

        # 모델 선택
        ctk.CTkLabel(api_bar, text="모델:", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(0, 4))
        self.cbo_model = ctk.CTkComboBox(api_bar, values=["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash"], width=150, height=28)
        self.cbo_model.pack(side="left", padx=(0, 10))
        self.cbo_model.set("gemini-2.5-flash")

        # 2. 본문 2분할 (좌: 화면 캡처 및 자연어 프롬프트 / 우: AI 생성 결과)
        body = ctk.CTkFrame(self, corner_radius=6)
        body.pack(fill="both", expand=True, padx=10, pady=4)
        body.grid_columnconfigure(0, weight=1, minsize=440)
        body.grid_columnconfigure(1, weight=1, minsize=440)
        body.grid_rowconfigure(0, weight=1)

        # ---------------------------------------------------------------------
        # 좌측: 화면 캡처 + 이미지 미리보기 + 자연어 입력
        # ---------------------------------------------------------------------
        left_f = ctk.CTkFrame(body, corner_radius=6)
        left_f.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")

        l_head = ctk.CTkFrame(left_f, fg_color="transparent")
        l_head.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(l_head, text="📸 1단계: 타겟 화면 캡처 / 이미지", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")

        # 캡처 버튼 툴바
        cap_bar = ctk.CTkFrame(left_f, fg_color="transparent")
        cap_bar.pack(fill="x", padx=8, pady=(0, 6))

        btn_cap_screen = ctk.CTkButton(
            cap_bar, text="📸 현재 화면 즉시 캡처", width=150, height=30,
            fg_color="#1f6aa5", hover_color="#144d75", font=ctk.CTkFont(weight="bold"),
            command=self._capture_screen_now
        )
        btn_cap_screen.pack(side="left", padx=(0, 4))

        btn_browse_img = ctk.CTkButton(
            cap_bar, text="📁 이미지 파일 열기", width=130, height=30,
            fg_color="#444444", hover_color="#333333", command=self._browse_image_file
        )
        btn_browse_img.pack(side="left", padx=4)

        # 이미지 썸네일 미리보기 영역
        self.frame_preview = ctk.CTkFrame(left_f, height=180, fg_color="#181818", corner_radius=6)
        self.frame_preview.pack(fill="x", padx=8, pady=4)
        self.lbl_img_preview = ctk.CTkLabel(
            self.frame_preview, text="[캡처된 이미지가 여기에 표시됩니다]",
            font=ctk.CTkFont(size=11), text_color="#777777"
        )
        self.lbl_img_preview.pack(expand=True, pady=40)

        # 자연어 요구사항 입력
        ctk.CTkLabel(
            left_f, text="✍️ 2단계: AI에게 시킬 자연어 지시사항 입력",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#64b5f6"
        ).pack(anchor="w", padx=8, pady=(8, 2))

        self.txt_prompt = ctk.CTkTextbox(left_f, height=120, font=ctk.CTkFont(size=12))
        self.txt_prompt.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self.txt_prompt.insert(
            "1.0",
            "계약번호 검색창에 '2D2607007'을 입력하고 '조회' 버튼을 클릭한 다음,\n"
            "검색 결과 그리드(테이블)의 첫 번째 행을 더블클릭해서 상세 화면으로 이동해줘."
        )

        # 생성 실행 버튼
        self.btn_generate = ctk.CTkButton(
            left_f, text="⚡ AI 코드 생성 (Generate RPA Code)", height=38,
            fg_color="#00838f", hover_color="#006064", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._start_ai_generation
        )
        self.btn_generate.pack(fill="x", padx=8, pady=(4, 8))

        # ---------------------------------------------------------------------
        # 우측: AI 생성 코드 & 분석 설명 뷰어
        # ---------------------------------------------------------------------
        right_f = ctk.CTkFrame(body, corner_radius=6)
        right_f.grid(row=0, column=1, padx=(0, 6), pady=6, sticky="nsew")

        r_head = ctk.CTkFrame(right_f, fg_color="transparent")
        r_head.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(r_head, text="💻 3단계: AI가 생성한 완성형 RPA 코드", font=ctk.CTkFont(size=12, weight="bold"), text_color="#81c784").pack(side="left")

        self.txt_result_code = ctk.CTkTextbox(
            right_f, font=ctk.CTkFont(family="Consolas", size=12), fg_color="#181818"
        )
        self.txt_result_code.pack(fill="both", expand=True, padx=8, pady=4)

        # 하단 액션 버튼 바
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

    # =========================================================================
    # 화면 캡처 및 이미지 로딩
    # =========================================================================
    def _capture_screen_now(self):
        """현재 전체 화면 캡처"""
        self.withdraw()  # 스파이 창 잠시 숨김
        time.sleep(0.3)

        temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures")
        os.makedirs(temp_dir, exist_ok=True)
        shot_path = os.path.join(temp_dir, f"screen_{int(time.time())}.png")

        try:
            if HAS_PYAUTOGUI:
                shot = pyautogui.screenshot()
                shot.save(shot_path)
            else:
                # PIL ImageGrab fallback
                from PIL import ImageGrab
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
            # 썸네일 리사이즈 (가로 최대 400, 세로 최대 160)
            pil_img.thumbnail((400, 160))
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)

            self.lbl_img_preview.configure(image=ctk_img, text="")
            self.lbl_img_preview.image = ctk_img
        except Exception as ex:
            self.lbl_img_preview.configure(text=f"미리보기 실패: {ex}")

    # =========================================================================
    # AI 코드 생성 실행 (비동기 스레드)
    # =========================================================================
    def _start_ai_generation(self):
        api_key = self.ent_api_key.get().strip()
        if not api_key:
            messagebox.showwarning("입력 확인", "상단에 Google Gemini API Key를 먼저 입력해 주십시오.")
            return

        if not self.current_image_path or not os.path.exists(self.current_image_path):
            messagebox.showwarning("입력 확인", "[📸 현재 화면 캡처] 또는 [📁 이미지 파일 열기]로 타겟 화면을 먼저 지정해 주십시오.")
            return

        prompt = self.txt_prompt.get("1.0", "end").strip()
        if not prompt:
            messagebox.showwarning("입력 확인", "AI에게 요청할 자연어 지시사항을 입력해 주십시오.")
            return

        model = self.cbo_model.get()
        self.btn_generate.configure(text="⏳ Gemini AI 분석 중... (약 1~2초 소요)", state="disabled")
        self.txt_result_code.delete("1.0", "end")
        self.txt_result_code.insert("1.0", f"// 🤖 Google Gemini ({model})에 화면 이미지와 요구사항을 전송하여 분석 중입니다...\n// 잠시만 기다려 주십시오...\n")

        def _worker():
            try:
                code, full_text = GeminiVisionAgent.call_gemini_vision(
                    api_key=api_key,
                    image_path=self.current_image_path,
                    user_prompt=prompt,
                    model=model
                )
                self.after(0, lambda c=code, f=full_text: self._on_generation_success(c, f))
            except Exception as e:
                self.after(0, lambda err=str(e): self._on_generation_error(err))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_generation_success(self, code: str, full_text: str):
        self.btn_generate.configure(text="⚡ AI 코드 생성 (Generate RPA Code)", state="normal")
        self.txt_result_code.delete("1.0", "end")
        self.txt_result_code.insert("1.0", code)
        messagebox.showinfo("생성 완료", "✅ Gemini Vision AI가 최적의 셀렉터와 파이썬 RPA 코드를 생성하였습니다!")

    def _on_generation_error(self, err_msg: str):
        self.btn_generate.configure(text="⚡ AI 코드 생성 (Generate RPA Code)", state="normal")
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

        prompt_first_line = self.txt_prompt.get("1.0", "end").strip().splitlines()[0][:20]
        mod_data = {
            "name": f"ai_mod_{int(time.time())}",
            "title": f"AI 생성: {prompt_first_line}",
            "category": "웹조작",
            "description": f"Gemini Vision 생성 모듈 ({self.cbo_model.get()})",
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

    def _load_saved_api_key(self):
        # 1. 환경변수 확인
        k = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
        if not k and os.path.exists(self._CONFIG_FILE):
            try:
                with open(self._CONFIG_FILE, "r", encoding="utf-8") as f:
                    k = json.load(f).get("gemini_api_key", "")
            except Exception:
                pass
        if not k:
            ubus_cfg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "UBUS_contract", "config.json")
            if os.path.exists(ubus_cfg):
                try:
                    with open(ubus_cfg, "r", encoding="utf-8") as f:
                        k = json.load(f).get("gemini_api_key", "")
                except Exception:
                    pass

        if k:
            self.ent_api_key.insert(0, k)

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
