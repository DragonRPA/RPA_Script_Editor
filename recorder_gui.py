"""
Universal RPA Recorder - Studio GUI & Script IDE
CustomTkinter 기반 범용 RPA 시나리오 녹화기 + 스니펫 지원형 파이썬 코드 에디터
"""

import os
import sys
import json
import threading
import time
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Dict, Any, List, Optional

import customtkinter as ctk

from scenario_model import ScenarioModel
from browser_recorder import BrowserRecorder
from snippets_library import SNIPPET_CATEGORIES
from playwright_parser import parse_advanced_python_to_scenario
from neon_db import NeonDBManager

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

DEFAULT_PYTHON_SCRIPT = """# =============================================================================
# Universal RPA Python Script
# =============================================================================
import re
import os
import time
from playwright.sync_api import sync_playwright

def run(playwright):
    # 1. 브라우저 기동
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    # -------------------------------------------------------------------------
    # [1단계: 1회 실행] 로그인 및 초기 화면 이동
    # -------------------------------------------------------------------------
    print(">>> 1단계: 로그인 진행 중...")
    page.goto("http://175.119.156.105:3000/")
    page.get_by_role("textbox", name="ID").fill("dragonrpa")
    page.get_by_role("textbox", name="비밀번호").fill("1111")
    page.get_by_role("button", name="로그인").click()

    page.locator("a").filter(has_text=re.compile(r"^계약$")).click()
    page.locator("a").filter(has_text="계약조회").click()
    page.wait_for_load_state("domcontentloaded")
    print(">>> 계약조회 화면 도착 완료!\\n")

    # -------------------------------------------------------------------------
    # [2단계: PDF 건별 반복 루프] (좌측 스니펫 패널에서 버튼으로 추가 가능)
    # -------------------------------------------------------------------------
    # [단일 테스트용 모의 데이터]
    test_items = [
        {"계약번호": "2D2607007", "file_path": "C:/UBUS_PDF/2_OCR완료/2D2607007.pdf"}
    ]

    for idx, item in enumerate(test_items, start=1):
        contract_no = item["계약번호"]
        file_path = item["file_path"]
        print(f"[{idx}/{len(test_items)}] {contract_no} 작업 시작...")

        # 계약번호 검색
        contract_input = page.locator("label:has-text('계약번호') + input, input[name*='contract']").first
        contract_input.fill(contract_no)
        page.get_by_role("button", name="조회").click()

        # 결과 1행 더블클릭 및 파일 첨부
        page.locator("table tbody tr").first.dblclick()
        page.locator("input[type='file']").first.set_input_files(file_path)
        page.get_by_role("button", name="저장").click()
        page.wait_for_timeout(1000)

        print(f"[{idx}/{len(test_items)}] {contract_no} 등록 완료!")

    # -------------------------------------------------------------------------
    # [3단계: 종료]
    # -------------------------------------------------------------------------
    print(">>> 모든 자동화 작업 완료!")
    context.close()
    browser.close()

if __name__ == "__main__":
    with sync_playwright() as p:
        run(p)
"""


class RecorderGUI(ctk.CTk):
    """범용 RPA 시나리오 녹화 스튜디오 & 파이썬 스크립트 IDE"""

    def __init__(self):
        super().__init__()

        self.title("범용 RPA 시나리오 스튜디오 (Universal RPA Studio & Script IDE)")
        self.geometry("1280x880")
        self.minsize(1080, 740)

        self.scenario = ScenarioModel()
        self.recorder: Optional[BrowserRecorder] = None
        self.is_loop_mode = False

        self._build_ui()
        self._refresh_step_lists()

    def _build_ui(self):
        """메인 탭 레이아웃 구성"""
        self.tabview = ctk.CTkTabview(self, corner_radius=6)
        self.tabview.pack(fill="both", expand=True, padx=12, pady=12)

        self.tab_script = self.tabview.add("🐍 파이썬 스크립트 에디터 (스니펫 지원)")
        self.tab_cards = self.tabview.add("🧩 비주얼 스텝 카드 에디터")

        self._build_script_tab()
        self._build_cards_tab()

    # -------------------------------------------------------------------------
    # 탭 1: 스크립트 코드 에디터 (IDE)
    # -------------------------------------------------------------------------
    def _build_script_tab(self):
        # 0. 대상 URL 설정 행 (저장/복원 가능)
        url_bar = ctk.CTkFrame(self.tab_script, corner_radius=6)
        url_bar.pack(fill="x", padx=6, pady=(4, 0))

        ctk.CTkLabel(url_bar, text="대상 URL", font=ctk.CTkFont(size=12, weight="bold"),
                     width=60).pack(side="left", padx=(10, 6), pady=8)
        self.entry_script_url = ctk.CTkEntry(
            url_bar, height=32, placeholder_text="예: http://175.119.156.105:3000  또는  https://www.example.com"
        )
        self.entry_script_url.pack(side="left", fill="x", expand=True, padx=(0, 6), pady=6)
        self.entry_script_url.insert(0, self._load_script_url())

        btn_save_url = ctk.CTkButton(
            url_bar, text="URL 저장", width=80, height=32,
            fg_color="#2e7d32", hover_color="#1b5e20", command=self._save_script_url
        )
        btn_save_url.pack(side="left", padx=(0, 8), pady=6)

        # 1. 상단 액션 툴바
        top_bar = ctk.CTkFrame(self.tab_script, corner_radius=6)
        top_bar.pack(fill="x", padx=6, pady=(4, 6))

        self.btn_run_script = ctk.CTkButton(
            top_bar, text="▶ 코드 테스트 실행", width=140, height=34,
            fg_color="#2e7d32", hover_color="#1b5e20", font=ctk.CTkFont(weight="bold"),
            command=self.run_current_script
        )
        self.btn_run_script.pack(side="left", padx=8, pady=6)

        btn_codegen = ctk.CTkButton(
            top_bar, text="Playwright 비주얼 인스펙터 열기", width=210, height=34,
            fg_color="#1f6aa5", hover_color="#144d75", command=self.launch_codegen
        )
        btn_codegen.pack(side="left", padx=6, pady=6)

        btn_convert_to_cards = ctk.CTkButton(
            top_bar, text="🧩 스크립트 ➔ 스텝 카드로 변환", width=210, height=34,
            fg_color="#00838f", hover_color="#006064", font=ctk.CTkFont(weight="bold"),
            command=self._convert_current_script_to_cards
        )
        btn_convert_to_cards.pack(side="left", padx=6, pady=6)

        btn_db_modules = ctk.CTkButton(
            top_bar, text="☁️ DB 모듈 라이브러리", width=160, height=34,
            fg_color="#6a1b9a", hover_color="#4a148c", command=self._open_db_modules_modal
        )
        btn_db_modules.pack(side="left", padx=6, pady=6)

        btn_save_py = ctk.CTkButton(
            top_bar, text="💾 파이썬 저장 (.py)", width=130, height=34,
            fg_color="#3a3a3a", hover_color="#222222", command=self.save_python_file
        )
        btn_save_py.pack(side="right", padx=(4, 8), pady=6)

        btn_load_py = ctk.CTkButton(
            top_bar, text="📂 파일 불러오기", width=120, height=34,
            fg_color="#444444", hover_color="#333333", command=self.load_python_file
        )
        btn_load_py.pack(side="right", padx=4, pady=6)

        btn_reset_py = ctk.CTkButton(
            top_bar, text="기본 예제 복원", width=100, height=34,
            fg_color="#555555", hover_color="#333333", command=self.reset_python_code
        )
        btn_reset_py.pack(side="right", padx=4, pady=6)

        # 2. 본문 2분할 (좌: 스니펫 라이브러리 / 우: 코드 에디터 + 콘솔)
        body_frame = ctk.CTkFrame(self.tab_script, corner_radius=6)
        body_frame.pack(fill="both", expand=True, padx=6, pady=4)
        body_frame.grid_columnconfigure(0, weight=0, minsize=290)
        body_frame.grid_columnconfigure(1, weight=1)
        body_frame.grid_rowconfigure(0, weight=1)

        # 2-1. 좌측: 스니펫 라이브러리 스크롤 패널
        snippet_box = ctk.CTkFrame(body_frame, width=290, corner_radius=6)
        snippet_box.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")

        ctk.CTkLabel(
            snippet_box, text="🛠️ 원클릭 스니펫 라이브러리", font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=10, pady=(8, 4))
        ctk.CTkLabel(
            snippet_box, text="버튼을 누르면 에디터 커서 위치에 자동 삽입됩니다.",
            font=ctk.CTkFont(size=11), text_color="#aaaaaa"
        ).pack(anchor="w", padx=10, pady=(0, 6))

        scroll_snippets = ctk.CTkScrollableFrame(snippet_box)
        scroll_snippets.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        # 카테고리별 스니펫 버튼 생성
        for category, items in SNIPPET_CATEGORIES.items():
            cat_label = ctk.CTkLabel(
                scroll_snippets, text=category, font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#64b5f6"
            )
            cat_label.pack(anchor="w", pady=(8, 2))

            for item in items:
                btn_snip = ctk.CTkButton(
                    scroll_snippets,
                    text=f"+ {item['name']}",
                    anchor="w",
                    height=26,
                    fg_color="#333333",
                    hover_color="#1f6aa5",
                    font=ctk.CTkFont(size=11),
                    command=lambda code=item["code"]: self.insert_snippet_code(code)
                )
                btn_snip.pack(fill="x", pady=1)

        # 2-2. 우측: 코드 텍스트 에디터 + 콘솔 출력 창
        editor_box = ctk.CTkFrame(body_frame, corner_radius=6)
        editor_box.grid(row=0, column=1, padx=6, pady=6, sticky="nsew")
        editor_box.grid_rowconfigure(0, weight=3) # 코드 에디터
        editor_box.grid_rowconfigure(1, weight=1) # 콘솔 로그
        editor_box.grid_columnconfigure(0, weight=1)

        # 상부: 파이썬 코드 입력기
        self.txt_code = ctk.CTkTextbox(
            editor_box, font=ctk.CTkFont(family="Consolas", size=13), wrap="none"
        )
        self.txt_code.grid(row=0, column=0, padx=6, pady=(6, 3), sticky="nsew")
        self.txt_code.insert("1.0", DEFAULT_PYTHON_SCRIPT)

        # 하부: 콘솔 로그 출력기
        console_frame = ctk.CTkFrame(editor_box, corner_radius=6)
        console_frame.grid(row=1, column=0, padx=6, pady=(3, 6), sticky="nsew")

        con_head = ctk.CTkFrame(console_frame, fg_color="transparent")
        con_head.pack(fill="x", padx=8, pady=(4, 2))
        ctk.CTkLabel(con_head, text="💻 실시간 실행 콘솔 출력", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        ctk.CTkButton(
            con_head, text="로그 지우기", width=70, height=20, font=ctk.CTkFont(size=10),
            command=lambda: self.txt_console.delete("1.0", "end")
        ).pack(side="right")

        self.txt_console = ctk.CTkTextbox(
            console_frame, font=ctk.CTkFont(family="Consolas", size=11), fg_color="#181818"
        )
        self.txt_console.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    def insert_snippet_code(self, code_text: str):
        """커서 위치에 스니펫 코드 삽입"""
        self.txt_code.insert("insert", code_text + "\n")
        self.txt_code.focus_set()

    def run_current_script(self):
        """현재 에디터의 파이썬 코드를 독립 서브프로세스로 안전하게 실행"""
        code = self.txt_code.get("1.0", "end").strip()
        if not code:
            messagebox.showwarning("실행 확인", "실행할 코드가 없습니다.")
            return

        self.txt_console.delete("1.0", "end")
        self.txt_console.insert("end", "=== [스크립트 실행 시작] ===\n")

        # 임시 실행 파일 저장
        temp_script_path = os.path.abspath("_temp_runner.py")
        try:
            with open(temp_script_path, "w", encoding="utf-8") as f:
                f.write(code)
        except Exception as e:
            self.txt_console.insert("end", f"임시 파일 생성 실패: {e}\n")
            return

        def _worker():
            try:
                proc = subprocess.Popen(
                    [sys.executable, temp_script_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1
                )
                for line in proc.stdout:
                    self.after(0, lambda l=line: self._append_console(l))
                proc.wait()
                self.after(0, lambda: self._append_console(f"\n=== [실행 완료 (종료 코드: {proc.returncode})] ===\n"))
            except Exception as ex:
                self.after(0, lambda: self._append_console(f"실행 예외: {ex}\n"))
            finally:
                if os.path.exists(temp_script_path):
                    try:
                        os.remove(temp_script_path)
                    except Exception:
                        pass

        threading.Thread(target=_worker, daemon=True).start()

    def _append_console(self, text: str):
        self.txt_console.insert("end", text)
        self.txt_console.see("end")

    def save_python_file(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".py",
            filetypes=[("파이썬 스크립트", "*.py")],
            initialfile="rpa_custom_scenario.py"
        )
        if filepath:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(self.txt_code.get("1.0", "end"))
                messagebox.showinfo("저장 완료", f"스크립트가 성공적으로 저장되었습니다:\n{filepath}")
            except Exception as e:
                messagebox.showerror("저장 오류", f"파일 저장 실패: {e}")

    def load_python_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("파이썬 스크립트", "*.py")])
        if filepath:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                self.txt_code.delete("1.0", "end")
                self.txt_code.insert("1.0", content)
                messagebox.showinfo("불러오기 완료", f"스크립트를 성공적으로 불러왔습니다:\n{filepath}")
            except Exception as e:
                messagebox.showerror("로드 오류", f"파일 로드 실패: {e}")

    def reset_python_code(self):
        self.txt_code.delete("1.0", "end")
        self.txt_code.insert("1.0", DEFAULT_PYTHON_SCRIPT)

    # -------------------------------------------------------------------------
    # 탭 2: 비주얼 스텝 카드 에디터
    # -------------------------------------------------------------------------
    def _build_cards_tab(self):
        top_frame = ctk.CTkFrame(self.tab_cards, corner_radius=6)
        top_frame.pack(fill="x", padx=8, pady=(4, 6))

        url_box = ctk.CTkFrame(top_frame, fg_color="transparent")
        url_box.pack(fill="x", padx=12, pady=(6, 4))
        
        ctk.CTkLabel(url_box, text="대상 웹사이트 URL", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
        self.entry_url = ctk.CTkEntry(url_box, height=32)
        self.entry_url.pack(fill="x", pady=(2, 0))
        self.entry_url.insert(0, "http://175.119.156.105:3000")

        bar = ctk.CTkFrame(top_frame, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=(4, 8))

        self.btn_record = ctk.CTkButton(
            bar, text="실시간 녹화 시작", width=130, height=34, fg_color="#992222", hover_color="#771111",
            font=ctk.CTkFont(weight="bold"), command=self.toggle_recording
        )
        self.btn_record.pack(side="left", padx=(0, 6))

        self.btn_mode = ctk.CTkButton(
            bar, text="현재 녹화 모드: [1회 실행 영역]", width=220, height=34,
            fg_color="#3a3a3a", hover_color="#2a2a2a", command=self.toggle_record_mode
        )
        self.btn_mode.pack(side="left", padx=6)

        btn_import_code = ctk.CTkButton(
            bar, text="📋 인스펙터 코드 가져오기", width=170, height=34,
            fg_color="#d97706", hover_color="#b45309", command=self.open_code_importer
        )
        btn_import_code.pack(side="left", padx=6)

        self.btn_save = ctk.CTkButton(
            bar, text="시나리오 저장 (JSON)", width=130, height=34,
            fg_color="#1f6aa5", hover_color="#144d75", command=self.save_scenario
        )
        self.btn_save.pack(side="right", padx=(6, 0))

        self.btn_load = ctk.CTkButton(
            bar, text="시나리오 불러오기", width=120, height=34,
            fg_color="#444444", hover_color="#333333", command=self.load_scenario
        )
        self.btn_load.pack(side="right", padx=6)

        # 2분할 카드 뷰
        body = ctk.CTkFrame(self.tab_cards, corner_radius=6)
        body.pack(fill="both", expand=True, padx=8, pady=4)
        body.grid_columnconfigure((0, 1), weight=1, uniform="c_cols")
        body.grid_rowconfigure(0, weight=1)

        # 좌: 1회
        self.frame_setup = ctk.CTkFrame(body)
        self.frame_setup.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")

        f_setup_head = ctk.CTkFrame(self.frame_setup, fg_color="transparent")
        f_setup_head.pack(fill="x", padx=10, pady=6)
        ctk.CTkLabel(f_setup_head, text="[1회 실행 영역] 로그인 및 초기 세션", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkButton(f_setup_head, text="+ 스텝 추가", width=80, height=24, command=lambda: self._add_manual_step(False)).pack(side="right")

        self.scroll_setup = ctk.CTkScrollableFrame(self.frame_setup)
        self.scroll_setup.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # 우: 반복
        self.frame_loop = ctk.CTkFrame(body)
        self.frame_loop.grid(row=0, column=1, padx=6, pady=6, sticky="nsew")

        f_loop_head = ctk.CTkFrame(self.frame_loop, fg_color="transparent")
        f_loop_head.pack(fill="x", padx=10, pady=6)
        ctk.CTkLabel(f_loop_head, text="[반복 실행 영역] 데이터 건별 루프", font=ctk.CTkFont(size=13, weight="bold"), text_color="#64b5f6").pack(side="left")
        ctk.CTkButton(f_loop_head, text="+ 스텝 추가", width=80, height=24, command=lambda: self._add_manual_step(True)).pack(side="right")

        self.scroll_loop = ctk.CTkScrollableFrame(self.frame_loop)
        self.scroll_loop.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.lbl_status = ctk.CTkLabel(
            self.tab_cards, text="준비 완료. [실시간 녹화 시작]을 누르면 브라우저 화면에 빨간색 타겟 박스와 배지가 표시됩니다.",
            font=ctk.CTkFont(size=12), text_color="#aaaaaa"
        )
        self.lbl_status.pack(anchor="w", padx=16, pady=(2, 6))

    # -------------------------------------------------------------------------
    # 녹화 제어
    # -------------------------------------------------------------------------
    def toggle_recording(self):
        if self.recorder and self.recorder.is_recording:
            self.recorder.stop()
            self.recorder = None
            self.btn_record.configure(text="실시간 녹화 시작", fg_color="#992222")
            self.lbl_status.configure(text="녹화가 중지되었습니다. 스텝 카드를 검토하고 저장하십시오.", text_color="#aaaaaa")
        else:
            url = self.entry_url.get().strip()
            self.btn_record.configure(text="녹화 중지 (Stop)", fg_color="#555555")
            self.lbl_status.configure(
                text="🔴 실시간 녹화 중: 브라우저에 마우스를 올리면 [빨간 박스]가 뜨며, 클릭/입력 시 카드가 즉시 생성됩니다.",
                text_color="#ff5555"
            )
            self.recorder = BrowserRecorder(self._on_action_captured_async)
            self.recorder.start(url)

    # -------------------------------------------------------------------------
    # URL 설정 저장/복원 (config.json 기반)
    # -------------------------------------------------------------------------
    _CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recorder_config.json")

    def _load_script_url(self) -> str:
        """저장된 대상 URL 복원 (없으면 기본값 반환)"""
        try:
            if os.path.exists(self._CONFIG_FILE):
                with open(self._CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f).get("target_url", "http://175.119.156.105:3000")
        except Exception:
            pass
        return "http://175.119.156.105:3000"

    def _save_script_url(self):
        """현재 대상 URL을 config 파일에 저장"""
        url = self.entry_script_url.get().strip()
        try:
            existing = {}
            if os.path.exists(self._CONFIG_FILE):
                with open(self._CONFIG_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            existing["target_url"] = url
            with open(self._CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            # 비주얼 피드백: 버튼 텍스트 1.5초간 변경
            from tkinter import messagebox
            messagebox.showinfo("저장 완료", f"대상 URL이 저장되었습니다:\n{url}")
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("저장 오류", f"URL 저장 실패: {e}")

    def launch_codegen(self):
        """저장된 대상 URL로 Playwright 비주얼 인스펙터(codegen) 실행"""
        url = self.entry_script_url.get().strip() or "http://175.119.156.105:3000"
        BrowserRecorder.launch_official_codegen(url)

    def toggle_record_mode(self):
        self.is_loop_mode = not self.is_loop_mode
        if self.is_loop_mode:
            self.btn_mode.configure(text="현재 녹화 모드: [🔁 반복 실행 영역]", fg_color="#1f6aa5")
        else:
            self.btn_mode.configure(text="현재 녹화 모드: [1회 실행 영역]", fg_color="#3a3a3a")

    def _on_action_captured_async(self, event_data: Dict[str, Any]):
        self.after(0, lambda: self._process_captured_event(event_data))

    def _process_captured_event(self, event_data: Dict[str, Any]):
        action = event_data.get("action", "")
        target = event_data.get("target", "")
        value = event_data.get("value", "")
        text = event_data.get("elementText", "")

        step = self.scenario.create_step(action, target, value, title=f"{action}: {text or target}")
        self.scenario.add_step(step, is_loop=self.is_loop_mode)
        self._refresh_step_lists()
        self.lbl_status.configure(text=f"⚡ 동작 기록됨: [{action}] {text or target}", text_color="#64b5f6")

    def _refresh_step_lists(self):
        for w in self.scroll_setup.winfo_children():
            w.destroy()
        for w in self.scroll_loop.winfo_children():
            w.destroy()

        for idx, step in enumerate(self.scenario.setup_steps):
            self._render_step_card(self.scroll_setup, step, idx, is_loop=False)

        for idx, step in enumerate(self.scenario.loop_steps):
            self._render_step_card(self.scroll_loop, step, idx, is_loop=True)

    def _render_step_card(self, parent, step: Dict[str, Any], index: int, is_loop: bool):
        card = ctk.CTkFrame(parent, corner_radius=6, fg_color="#2b2b2b")
        card.pack(fill="x", pady=4, padx=4)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=8, pady=(6, 2))

        ctk.CTkLabel(
            head, text=f"Step {index + 1}. [{step.get('action')}]",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#64b5f6" if is_loop else "#ffffff"
        ).pack(side="left")

        ctk.CTkButton(
            head, text="✕", width=22, height=22, fg_color="#772222", hover_color="#551111",
            command=lambda sid=step['id']: self._delete_step(sid)
        ).pack(side="right", padx=(4, 0))

        ctk.CTkButton(
            head, text="반복으로 ➔" if not is_loop else "1회로 ➔", width=70, height=22,
            fg_color="#3a3a3a", hover_color="#222222",
            command=lambda sid=step['id'], loop=is_loop: self._switch_step_zone(sid, loop)
        ).pack(side="right", padx=4)

        f_target = ctk.CTkFrame(card, fg_color="transparent")
        f_target.pack(fill="x", padx=8, pady=2)
        ctk.CTkLabel(f_target, text="대상 선택자 (Selector):", font=ctk.CTkFont(size=11)).pack(anchor="w")
        e_target = ctk.CTkEntry(f_target, height=26, font=ctk.CTkFont(family="Consolas", size=11))
        e_target.pack(fill="x", pady=(1, 0))
        e_target.insert(0, step.get("target", ""))
        e_target.bind("<FocusOut>", lambda e, s=step, ent=e_target: self._update_step_val(s, "target", ent.get()))

        if step.get("action") in ["FILL", "SET_FILES", "GOTO"]:
            f_val = ctk.CTkFrame(card, fg_color="transparent")
            f_val.pack(fill="x", padx=8, pady=(2, 6))
            
            v_head = ctk.CTkFrame(f_val, fg_color="transparent")
            v_head.pack(fill="x")
            ctk.CTkLabel(v_head, text="입력값 / 파일경로:", font=ctk.CTkFont(size=11)).pack(side="left")
            
            ctk.CTkButton(
                v_head, text="{{계약번호}}", width=65, height=18, font=ctk.CTkFont(size=10),
                command=lambda ent=None, s=step: self._inject_variable(s, "{{계약번호}}")
            ).pack(side="right", padx=2)

            ctk.CTkButton(
                v_head, text="{{첨부파일_경로}}", width=85, height=18, font=ctk.CTkFont(size=10),
                command=lambda ent=None, s=step: self._inject_variable(s, "{{첨부파일_경로}}")
            ).pack(side="right", padx=2)

            e_val = ctk.CTkEntry(f_val, height=26, font=ctk.CTkFont(family="Consolas", size=11))
            e_val.pack(fill="x", pady=(1, 0))
            e_val.insert(0, step.get("value", ""))
            e_val.bind("<FocusOut>", lambda e, s=step, ent=e_val: self._update_step_val(s, "value", ent.get()))

    def _update_step_val(self, step: Dict[str, Any], key: str, value: str):
        step[key] = value

    def _inject_variable(self, step: Dict[str, Any], var_tag: str):
        step["value"] = var_tag
        self._refresh_step_lists()

    def _delete_step(self, step_id: str):
        self.scenario.remove_step(step_id)
        self._refresh_step_lists()

    def _switch_step_zone(self, step_id: str, is_currently_loop: bool):
        if is_currently_loop:
            self.scenario.move_to_setup(step_id)
        else:
            self.scenario.move_to_loop(step_id)
        self._refresh_step_lists()

    def _add_manual_step(self, is_loop: bool):
        step = self.scenario.create_step("CLICK", "button:has-text('새버튼')", "", "신규 스텝")
        self.scenario.add_step(step, is_loop=is_loop)
        self._refresh_step_lists()

    def save_scenario(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("RPA 시나리오 파일", "*.json")],
            initialfile="scenario.json"
        )
        if filepath:
            ok = self.scenario.save_to_file(filepath)
            if ok:
                messagebox.showinfo("저장 완료", f"시나리오가 성공적으로 저장되었습니다:\n{filepath}")

    def load_scenario(self):
        filepath = filedialog.askopenfilename(filetypes=[("RPA 시나리오 파일", "*.json")])
        if filepath:
            ok = self.scenario.load_from_file(filepath)
            if ok:
                self._refresh_step_lists()
                messagebox.showinfo("불러오기 완료", f"시나리오를 성공적으로 불러왔습니다:\n{filepath}")

    def open_code_importer(self):
        modal = ctk.CTkToplevel(self)
        modal.title("Playwright 인스펙터 코드 가져오기")
        modal.geometry("700x520")
        modal.grab_set()

        ctk.CTkLabel(
            modal, text="Playwright Inspector 화면의 코드를 복사하여 아래에 붙여넣으십시오:",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=16, pady=(16, 6))

        txt_code = ctk.CTkTextbox(modal, font=ctk.CTkFont(family="Consolas", size=12))
        txt_code.pack(fill="both", expand=True, padx=16, pady=6)

        zone_frame = ctk.CTkFrame(modal, fg_color="transparent")
        zone_frame.pack(fill="x", padx=16, pady=6)

        var_target_zone = ctk.StringVar(value="setup")
        ctk.CTkRadioButton(zone_frame, text="1회 실행 영역(Setup)으로 가져오기", variable=var_target_zone, value="setup").pack(side="left", padx=(0, 12))
        ctk.CTkRadioButton(zone_frame, text="반복 실행 영역(Loop)으로 가져오기", variable=var_target_zone, value="loop").pack(side="left")

        def _do_import():
            raw_code = txt_code.get("1.0", "end").strip()
            if not raw_code:
                messagebox.showwarning("입력 확인", "코드를 붙여넣어 주십시오.")
                return

            setup_s, loop_s = parse_advanced_python_to_scenario(raw_code)
            all_steps = setup_s + loop_s
            if not all_steps:
                messagebox.showerror("변환 실패", "유효한 동작 코드를 찾지 못했습니다.")
                return

            is_loop = (var_target_zone.get() == "loop")
            for ps in all_steps:
                step = self.scenario.create_step(ps["action"], ps["target"], ps["value"], ps["title"])
                self.scenario.add_step(step, is_loop=is_loop)

            self._refresh_step_lists()
            modal.destroy()
            messagebox.showinfo("가져오기 완료", f"총 {len(all_steps)}개의 스텝 카드가 성공적으로 생성되었습니다!")

        ctk.CTkButton(
            modal, text="시나리오 스텝으로 변환하기", height=36, fg_color="#1f6aa5", hover_color="#144d75",
            font=ctk.CTkFont(weight="bold"), command=_do_import
        ).pack(fill="x", padx=16, pady=(6, 16))

    def _convert_current_script_to_cards(self):
        """현재 에디터의 파이썬 코드를 분석하여 비주얼 스텝 카드로 변환하고 카드 탭으로 이동"""
        code = self.txt_script_editor.get("1.0", "end").strip()
        if not code:
            messagebox.showwarning("입력 확인", "에디터에 변환할 파이썬 코드가 없습니다.")
            return

        setup_steps, loop_steps = parse_advanced_python_to_scenario(code)
        if not setup_steps and not loop_steps:
            messagebox.showerror("변환 실패", "유효한 동작 스텝을 추출하지 못했습니다.")
            return

        self.scenario.setup_steps = setup_steps
        self.scenario.loop_steps = loop_steps
        self._refresh_step_lists()

        # 카드 에디터 탭으로 자동 전환
        self.tabview.set("🧩 비주얼 스텝 카드 에디터")
        messagebox.showinfo(
            "변환 완료",
            f"✅ 파이썬 스크립트가 스텝 카드로 변환되었습니다!\n\n"
            f"• 1회 실행(Setup) 영역: {len(setup_steps)}개 카드\n"
            f"• 반복 실행(Loop) 영역: {len(loop_steps)}개 카드"
        )


    def _load_neon_url(self) -> str:
        """Neon DB 연결 URL 불러오기"""
        try:
            # 1. recorder_config.json 확인
            if os.path.exists(self._CONFIG_FILE):
                with open(self._CONFIG_FILE, "r", encoding="utf-8") as f:
                    u = json.load(f).get("neon_database_url", "")
                    if u:
                        return u
            # 2. UBUS_contract/config.json 확인
            ubus_cfg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "UBUS_contract", "config.json")
            if os.path.exists(ubus_cfg):
                with open(ubus_cfg, "r", encoding="utf-8") as f:
                    return json.load(f).get("neon_database_url", "")
        except Exception:
            pass
        return "postgresql://neondb_owner:npg_W0LzlYBckKp1@ep-small-firefly-az3rp5ve.c-3.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"

    def _open_db_modules_modal(self):
        """Neon DB에 저장된 모듈형 RPA 스크립트 관리 및 불러오기/저장 모달"""
        modal = ctk.CTkToplevel(self)
        modal.title("☁️ Neon DB 모듈형 RPA 스크립트 관리자 (rpa_scripts)")
        modal.geometry("900x620")
        modal.grab_set()

        db_url = self._load_neon_url()
        db = NeonDBManager(db_url)

        # 전체 레이아웃 (좌: 모듈 목록 / 우: 모듈 편집 및 액션)
        modal.grid_columnconfigure(0, weight=0, minsize=300)
        modal.grid_columnconfigure(1, weight=1)
        modal.grid_rowconfigure(0, weight=1)

        # ---------------------------------------------------------------------
        # 좌측: 모듈 목록 패널
        # ---------------------------------------------------------------------
        left_frame = ctk.CTkFrame(modal, corner_radius=6)
        left_frame.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")

        l_head = ctk.CTkFrame(left_frame, fg_color="transparent")
        l_head.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(l_head, text="🗄️ 저장된 모듈 목록", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")

        # 카테고리 필터
        cbo_cat_filter = ctk.CTkComboBox(
            left_frame, values=["전체", "로그인", "웹조작", "윈도우앱", "OCR", "스니펫", "유틸", "사용자정의"],
            height=28
        )
        cbo_cat_filter.pack(fill="x", padx=8, pady=(0, 4))
        cbo_cat_filter.set("전체")

        scroll_list = ctk.CTkScrollableFrame(left_frame, corner_radius=6)
        scroll_list.pack(fill="both", expand=True, padx=8, pady=4)

        # ---------------------------------------------------------------------
        # 우측: 모듈 세부 정보 및 코드 편집
        # ---------------------------------------------------------------------
        right_frame = ctk.CTkFrame(modal, corner_radius=6)
        right_frame.grid(row=0, column=1, padx=(0, 8), pady=8, sticky="nsew")

        r_top = ctk.CTkFrame(right_frame, fg_color="transparent")
        r_top.pack(fill="x", padx=10, pady=(10, 4))
        r_top.grid_columnconfigure((0, 1), weight=1)

        # 모듈 식별자 (name)
        f_name = ctk.CTkFrame(r_top, fg_color="transparent")
        f_name.grid(row=0, column=0, padx=(0, 4), sticky="ew")
        ctk.CTkLabel(f_name, text="모듈 식별자 (영문 ID)", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w")
        ent_mod_name = ctk.CTkEntry(f_name, height=28, placeholder_text="예: ubus_login")
        ent_mod_name.pack(fill="x", pady=(2, 0))

        # 모듈 한글명 (title)
        f_title = ctk.CTkFrame(r_top, fg_color="transparent")
        f_title.grid(row=0, column=1, padx=(4, 0), sticky="ew")
        ctk.CTkLabel(f_title, text="모듈 한글명 (Title)", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w")
        ent_mod_title = ctk.CTkEntry(f_title, height=28, placeholder_text="예: UBUS ERP 로그인")
        ent_mod_title.pack(fill="x", pady=(2, 0))

        # 2행: 카테고리 & 설명
        r_mid = ctk.CTkFrame(right_frame, fg_color="transparent")
        r_mid.pack(fill="x", padx=10, pady=2)
        r_mid.grid_columnconfigure(0, weight=0, minsize=140)
        r_mid.grid_columnconfigure(1, weight=1)

        f_cat = ctk.CTkFrame(r_mid, fg_color="transparent")
        f_cat.grid(row=0, column=0, padx=(0, 4), sticky="ew")
        ctk.CTkLabel(f_cat, text="카테고리", font=ctk.CTkFont(size=11)).pack(anchor="w")
        cbo_mod_cat = ctk.CTkComboBox(f_cat, values=["로그인", "웹조작", "윈도우앱", "OCR", "스니펫", "유틸", "사용자정의"], height=28)
        cbo_mod_cat.pack(fill="x", pady=(2, 0))
        cbo_mod_cat.set("웹조작")

        f_desc = ctk.CTkFrame(r_mid, fg_color="transparent")
        f_desc.grid(row=0, column=1, padx=(4, 0), sticky="ew")
        ctk.CTkLabel(f_desc, text="모듈 설명 / 필요 변수", font=ctk.CTkFont(size=11)).pack(anchor="w")
        ent_mod_desc = ctk.CTkEntry(f_desc, height=28, placeholder_text="예: 계약번호 조회 후 상세 화면 진입")
        ent_mod_desc.pack(fill="x", pady=(2, 0))

        # 코드 에디터 박스
        ctk.CTkLabel(right_frame, text="파이썬 모듈 코드 (Python Code)", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10, pady=(6, 2))
        txt_mod_code = ctk.CTkTextbox(right_frame, font=ctk.CTkFont(family="Consolas", size=12), fg_color="#181818")
        txt_mod_code.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        # 하단 액션 버튼 바
        b_bar = ctk.CTkFrame(right_frame, fg_color="transparent")
        b_bar.pack(fill="x", padx=10, pady=(0, 10))

        def _refresh_module_list():
            for widget in scroll_list.winfo_children():
                widget.destroy()

            cat_filter = cbo_cat_filter.get()
            cat_val = None if cat_filter == "전체" else cat_filter

            try:
                mods = db.list_scripts(category=cat_val)
                if not mods:
                    ctk.CTkLabel(scroll_list, text="저장된 모듈이 없습니다.", font=ctk.CTkFont(size=11)).pack(pady=20)
                    return

                for m in mods:
                    card = ctk.CTkFrame(scroll_list, corner_radius=6, fg_color="#2b2b2b")
                    card.pack(fill="x", pady=3)

                    top_c = ctk.CTkFrame(card, fg_color="transparent")
                    top_c.pack(fill="x", padx=6, pady=(4, 2))
                    ctk.CTkLabel(top_c, text=f"[{m['category']}]", font=ctk.CTkFont(size=10, weight="bold"), text_color="#64b5f6").pack(side="left")
                    ctk.CTkLabel(top_c, text=m['name'], font=ctk.CTkFont(size=10), text_color="#aaaaaa").pack(side="right")

                    title_btn = ctk.CTkButton(
                        card, text=m['title'], anchor="w", fg_color="transparent",
                        hover_color="#3a3a3a", font=ctk.CTkFont(size=12, weight="bold"),
                        command=lambda key=m['name']: _select_module(key)
                    )
                    title_btn.pack(fill="x", padx=4, pady=(0, 4))
            except Exception as e:
                ctk.CTkLabel(scroll_list, text=f"DB 조회 오류:\n{e}", text_color="#ff5555", font=ctk.CTkFont(size=11)).pack(pady=10)

        def _select_module(mod_name: str):
            try:
                mod = db.get_script(mod_name)
                if mod:
                    ent_mod_name.delete(0, "end"); ent_mod_name.insert(0, mod.get("name", ""))
                    ent_mod_title.delete(0, "end"); ent_mod_title.insert(0, mod.get("title", ""))
                    cbo_mod_cat.set(mod.get("category", "웹조작"))
                    ent_mod_desc.delete(0, "end"); ent_mod_desc.insert(0, mod.get("description", "") or "")
                    txt_mod_code.delete("1.0", "end"); txt_mod_code.insert("1.0", mod.get("code", ""))
            except Exception as e:
                messagebox.showerror("오류", f"모듈 로드 실패: {e}")

        def _insert_to_main_editor():
            code = txt_mod_code.get("1.0", "end").strip()
            if not code:
                messagebox.showwarning("경고", "삽입할 코드가 없습니다.")
                return
            self.txt_script_editor.insert("insert", f"\n{code}\n")
            self.txt_script_editor.focus_set()
            modal.destroy()
            messagebox.showinfo("삽입 완료", f"모듈 '{ent_mod_title.get()}' 코드가 에디터에 삽입되었습니다.")

        def _save_to_neon_db():
            name = ent_mod_name.get().strip()
            title = ent_mod_title.get().strip()
            cat = cbo_mod_cat.get().strip()
            desc = ent_mod_desc.get().strip()
            code = txt_mod_code.get("1.0", "end").strip()

            if not name or not title or not code:
                messagebox.showwarning("필수 입력", "식별자(영문), 한글명, 코드는 필수 입력 항목입니다.")
                return

            try:
                db.save_script(name=name, title=title, category=cat, code=code, description=desc)
                _refresh_module_list()
                messagebox.showinfo("저장 완료", f"Neon DB에 모듈 '{title}'이(가) 성공적으로 저장되었습니다!")
            except Exception as e:
                messagebox.showerror("저장 오류", f"DB 저장 실패: {e}")

        def _pull_from_main_editor():
            cur_code = self.txt_script_editor.get("1.0", "end").strip()
            if not cur_code:
                messagebox.showwarning("안내", "현재 에디터에 코드가 없습니다.")
                return
            txt_mod_code.delete("1.0", "end")
            txt_mod_code.insert("1.0", cur_code)

        def _delete_from_db():
            name = ent_mod_name.get().strip()
            if not name:
                return
            if messagebox.askyesno("삭제 확인", f"정말로 모듈 '{name}'을(를) DB에서 삭제하시겠습니까?"):
                try:
                    db.delete_script(name)
                    _refresh_module_list()
                    txt_mod_code.delete("1.0", "end")
                    ent_mod_name.delete(0, "end")
                    ent_mod_title.delete(0, "end")
                    ent_mod_desc.delete(0, "end")
                    messagebox.showinfo("삭제 완료", f"모듈 '{name}'이(가) 삭제되었습니다.")
                except Exception as e:
                    messagebox.showerror("삭제 오류", f"삭제 실패: {e}")

        # 버튼 배치
        ctk.CTkButton(b_bar, text="📋 에디터에 삽입", height=32, fg_color="#2e7d32", hover_color="#1b5e20",
                      font=ctk.CTkFont(weight="bold"), command=_insert_to_main_editor).pack(side="left", padx=(0, 6))

        ctk.CTkButton(b_bar, text="💾 Neon DB에 저장/수정", height=32, fg_color="#6a1b9a", hover_color="#4a148c",
                      font=ctk.CTkFont(weight="bold"), command=_save_to_neon_db).pack(side="left", padx=6)

        ctk.CTkButton(b_bar, text="✨ 현재 에디터 내용 가져오기", height=32, fg_color="#444444", hover_color="#333333",
                      command=_pull_from_main_editor).pack(side="left", padx=6)

        ctk.CTkButton(b_bar, text="🗑️ DB에서 삭제", height=32, fg_color="#c62828", hover_color="#8e0000",
                      command=_delete_from_db).pack(side="right")

        cbo_cat_filter.configure(command=lambda _: _refresh_module_list())
        ctk.CTkButton(l_head, text="새로고침", width=60, height=22, font=ctk.CTkFont(size=10),
                      command=_refresh_module_list).pack(side="right")

        _refresh_module_list()



def main():
    app = RecorderGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
