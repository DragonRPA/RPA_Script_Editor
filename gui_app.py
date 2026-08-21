"""
UBUS Contract RPA & Ollama Pipeline - Main Desktop GUI
PDF OCR 키워드 추출 + RPA 재생기(Runner) & 스크립트 에디터 대시보드
"""

import os
import sys
import threading
import time
import json
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Dict, Any, List, Optional

import customtkinter as ctk

from config_manager import ConfigManager
from pdf_extractor import PDFExtractor
from file_pipeline import FilePipeline
from scenario_runner import ScenarioRunner
from scenario_recorder import ScenarioManager
from snippets_library import SNIPPET_CATEGORIES
from neon_db import NeonDBManager

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class UBUSApp(ctk.CTk):
    """UBUS ERP 계약서 자동 등록 관리 시스템 메인 윈도우"""

    def __init__(self):
        super().__init__()

        self.title("UBUS ERP 계약서 자동 등록 시스템 (PDF OCR + RPA 스크립트 재생기)")
        self.geometry("1260x880")
        self.minsize(1040, 740)

        self.config_mgr = ConfigManager()
        self.scenario_mgr = ScenarioManager(self.config_mgr.get("scenario_file", "scenario.json"))
        self.pipeline = FilePipeline(
            self.config_mgr.get("input_dir"),
            self.config_mgr.get("ocr_done_dir"),
            self.config_mgr.get("rpa_done_dir"),
            self.config_mgr.get("error_dir")
        )

        self.is_running = False
        self.runner: Optional[ScenarioRunner] = None
        self.worker_thread: Optional[threading.Thread] = None

        self._build_ui()
        self._load_values_to_ui()

    def _build_ui(self):
        self.tabview = ctk.CTkTabview(self, corner_radius=6)
        self.tabview.pack(fill="both", expand=True, padx=12, pady=12)

        self.tab_run      = self.tabview.add("🚀 작업 실행 대시보드")
        self.tab_script   = self.tabview.add("🐍 RPA 스크립트 에디터 (스니펫 지원)")
        self.tab_desktop  = self.tabview.add("🖥️ 윈도우 앱 자동화 (Desktop)")
        self.tab_scenario = self.tabview.add("🧩 JSON 시나리오 뷰어")
        self.tab_test     = self.tabview.add("📄 PDF 추출 테스트")

        self._build_run_tab()
        self._build_script_tab()
        self._build_desktop_tab()
        self._build_scenario_tab()
        self._build_test_tab()

    # -------------------------------------------------------------------------
    # 탭 1: 작업 실행 대시보드
    # -------------------------------------------------------------------------
    def _build_run_tab(self):
        top_frame = ctk.CTkFrame(self.tab_run, corner_radius=6)
        top_frame.pack(fill="x", padx=8, pady=(4, 8))
        top_frame.grid_columnconfigure((0, 1), weight=1, uniform="g1")

        # 좌: ERP 접속
        erp_card = ctk.CTkFrame(top_frame, fg_color="transparent")
        erp_card.grid(row=0, column=0, padx=12, pady=8, sticky="nsew")

        ctk.CTkLabel(erp_card, text="ERP 접속 정보", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(0, 6))
        self._create_vertical_input(erp_card, "ERP 접속 URL", "entry_erp_url")

        id_pw_frame = ctk.CTkFrame(erp_card, fg_color="transparent")
        id_pw_frame.pack(fill="x", pady=2)
        id_pw_frame.grid_columnconfigure((0, 1), weight=1)

        f_id = ctk.CTkFrame(id_pw_frame, fg_color="transparent")
        f_id.grid(row=0, column=0, padx=(0, 4), sticky="ew")
        ctk.CTkLabel(f_id, text="사용자 ID", font=ctk.CTkFont(size=12)).pack(anchor="w")
        self.entry_user_id = ctk.CTkEntry(f_id, height=30)
        self.entry_user_id.pack(fill="x", pady=(2, 0))

        f_pw = ctk.CTkFrame(id_pw_frame, fg_color="transparent")
        f_pw.grid(row=0, column=1, padx=(4, 0), sticky="ew")
        ctk.CTkLabel(f_pw, text="비밀번호", font=ctk.CTkFont(size=12)).pack(anchor="w")
        self.entry_user_pw = ctk.CTkEntry(f_pw, height=30, show="*")
        self.entry_user_pw.pack(fill="x", pady=(2, 0))

        self.chk_headless = ctk.CTkCheckBox(erp_card, text="브라우저 화면 표시 (Headed)")
        self.chk_headless.pack(anchor="w", pady=(8, 0))

        # 우: AI 설정
        ai_card = ctk.CTkFrame(top_frame, fg_color="transparent")
        ai_card.grid(row=0, column=1, padx=12, pady=8, sticky="nsew")

        ctk.CTkLabel(ai_card, text="Ollama AI 설정", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(0, 6))
        self._create_vertical_input(ai_card, "추출 키워드 (콤마 구분)", "entry_keywords")

        model_tpl = ctk.CTkFrame(ai_card, fg_color="transparent")
        model_tpl.pack(fill="x", pady=2)
        model_tpl.grid_columnconfigure((0, 1), weight=1)

        f_m = ctk.CTkFrame(model_tpl, fg_color="transparent")
        f_m.grid(row=0, column=0, padx=(0, 4), sticky="ew")
        ctk.CTkLabel(f_m, text="Ollama 모델", font=ctk.CTkFont(size=12)).pack(anchor="w")
        self.cbo_model = ctk.CTkComboBox(
            f_m, values=["qwen2.5:7b", "qwen3:8b", "qwen3:4b", "gemma3:4b", "llama3.2:3b"], height=30
        )
        self.cbo_model.pack(fill="x", pady=(2, 0))

        f_t = ctk.CTkFrame(model_tpl, fg_color="transparent")
        f_t.grid(row=0, column=1, padx=(4, 0), sticky="ew")
        ctk.CTkLabel(f_t, text="파일명 변경 서식", font=ctk.CTkFont(size=12)).pack(anchor="w")
        self.entry_template = ctk.CTkEntry(f_t, height=30)
        self.entry_template.pack(fill="x", pady=(2, 0))

        # 중간: 3단계 폴더 경로
        path_frame = ctk.CTkFrame(self.tab_run, corner_radius=6)
        path_frame.pack(fill="x", padx=8, pady=4)

        ctk.CTkLabel(path_frame, text="폴더 파이프라인 경로", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=12, pady=(8, 4))
        self._create_folder_picker(path_frame, "1단계: OCR 대기 폴더 (원본 PDF)", "entry_input_dir")
        self._create_folder_picker(path_frame, "2단계: OCR 완료 폴더 (파일명 변경본)", "entry_ocr_done_dir")
        self._create_folder_picker(path_frame, "3단계: RPA 완료 폴더 (ERP 등록 완료본)", "entry_rpa_done_dir")

        # 하단 제어 바
        ctrl_frame = ctk.CTkFrame(self.tab_run, corner_radius=6)
        ctrl_frame.pack(fill="x", padx=8, pady=6)

        btn_box = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        btn_box.pack(side="left", padx=12, pady=8)

        self.btn_start = ctk.CTkButton(
            btn_box, text="작업 시작", fg_color="#1f6aa5", hover_color="#144d75",
            width=120, height=36, font=ctk.CTkFont(weight="bold"), command=self.start_pipeline
        )
        self.btn_start.pack(side="left", padx=(0, 6))

        self.btn_stop = ctk.CTkButton(
            btn_box, text="작업 중지", fg_color="#992222", hover_color="#661111",
            width=100, height=36, state="disabled", command=self.stop_pipeline
        )
        self.btn_stop.pack(side="left", padx=6)

        self.btn_save = ctk.CTkButton(
            btn_box, text="설정 저장", fg_color="#3a3a3a", hover_color="#222222",
            width=90, height=36, command=self.save_current_settings
        )
        self.btn_save.pack(side="left", padx=6)

        self.lbl_stats = ctk.CTkLabel(
            ctrl_frame, text="대기: 0건 | 진행: 0/0 | 성공: 0 | 실패: 0",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.lbl_stats.pack(side="right", padx=16, pady=8)

        self.prog_bar = ctk.CTkProgressBar(self.tab_run, height=10)
        self.prog_bar.pack(fill="x", padx=8, pady=(0, 4))
        self.prog_bar.set(0)

        # 로그 창
        log_frame = ctk.CTkFrame(self.tab_run, corner_radius=6)
        log_frame.pack(fill="both", expand=True, padx=8, pady=4)

        ctk.CTkLabel(log_frame, text="작업 로그", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(6, 2))
        self.txt_log = ctk.CTkTextbox(log_frame, font=ctk.CTkFont(family="Consolas", size=12))
        self.txt_log.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _create_vertical_input(self, parent, label_text: str, attr_name: str):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=2)
        ctk.CTkLabel(frame, text=label_text, font=ctk.CTkFont(size=12)).pack(anchor="w")
        entry = ctk.CTkEntry(frame, height=30)
        entry.pack(fill="x", pady=(2, 0))
        setattr(self, attr_name, entry)

    def _create_folder_picker(self, parent, label_text: str, attr_name: str):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(frame, text=label_text, font=ctk.CTkFont(size=12)).pack(anchor="w")
        box = ctk.CTkFrame(frame, fg_color="transparent")
        box.pack(fill="x", pady=(2, 0))
        entry = ctk.CTkEntry(box, height=28)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        btn = ctk.CTkButton(
            box, text="폴더 선택", width=80, height=28,
            command=lambda e=entry: self._choose_directory(e)
        )
        btn.pack(side="right")
        setattr(self, attr_name, entry)

    def _choose_directory(self, target_entry: ctk.CTkEntry):
        chosen = filedialog.askdirectory(initialdir=target_entry.get())
        if chosen:
            target_entry.delete(0, "end")
            target_entry.insert(0, chosen)

    # -------------------------------------------------------------------------
    # 탭 2: 스크립트 에디터 (스니펫 지원)
    # -------------------------------------------------------------------------
    def _build_script_tab(self):
        top_bar = ctk.CTkFrame(self.tab_script, corner_radius=6)
        top_bar.pack(fill="x", padx=6, pady=(4, 6))

        btn_run_py = ctk.CTkButton(
            top_bar, text="▶ 단독 테스트 실행", width=130, height=34,
            fg_color="#2e7d32", hover_color="#1b5e20", font=ctk.CTkFont(weight="bold"),
            command=self._run_standalone_script
        )
        btn_run_py.pack(side="left", padx=6, pady=6)

        btn_ai_vision = ctk.CTkButton(
            top_bar, text="🤖 AI 비전 코드 생성", width=160, height=34,
            fg_color="#00695c", hover_color="#004d40", font=ctk.CTkFont(weight="bold"),
            command=self._open_ai_vision_generator
        )
        btn_ai_vision.pack(side="left", padx=4, pady=6)

        btn_win_spy = ctk.CTkButton(
            top_bar, text="🔍 Windows UIA Spy", width=160, height=34,
            fg_color="#4a148c", hover_color="#311b92", font=ctk.CTkFont(weight="bold"),
            command=self._open_windows_spy
        )
        btn_win_spy.pack(side="left", padx=4, pady=6)

        btn_db_modules = ctk.CTkButton(
            top_bar, text="☁️ DB 모듈", width=100, height=34,
            fg_color="#6a1b9a", hover_color="#4a148c", command=self._open_db_modules_modal
        )
        btn_db_modules.pack(side="left", padx=4, pady=6)

        btn_save_py = ctk.CTkButton(
            top_bar, text="💾 스크립트 저장 (.py)", width=140, height=34,
            fg_color="#3a3a3a", hover_color="#222222", command=self._save_script_file
        )
        btn_save_py.pack(side="right", padx=(4, 8), pady=6)

        btn_load_py = ctk.CTkButton(
            top_bar, text="📂 파일 불러오기", width=120, height=34,
            fg_color="#444444", hover_color="#333333", command=self._load_script_file
        )
        btn_load_py.pack(side="right", padx=4, pady=6)

        # 2분할 (좌: 스니펫 / 우: 에디터 + 콘솔)
        body = ctk.CTkFrame(self.tab_script, corner_radius=6)
        body.pack(fill="both", expand=True, padx=6, pady=4)
        body.grid_columnconfigure(0, weight=0, minsize=290)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # 좌: 스니펫 라이브러리
        snip_box = ctk.CTkFrame(body, width=290, corner_radius=6)
        snip_box.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")

        ctk.CTkLabel(snip_box, text="🛠️ 원클릭 스니펫 라이브러리", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(8, 4))
        scroll_snips = ctk.CTkScrollableFrame(snip_box)
        scroll_snips.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        def _make_category_toggle(btn_toggle, c_frame, cat_name):
            state = {"open": False}
            def _toggle():
                state["open"] = not state["open"]
                if state["open"]:
                    btn_toggle.configure(text=f"▼ {cat_name}", fg_color="#1f4b75")
                    c_frame.pack(fill="x", padx=(6, 0), pady=(2, 4))
                else:
                    btn_toggle.configure(text=f"▶ {cat_name}", fg_color="#262626")
                    c_frame.pack_forget()
            return _toggle

        for category, items in SNIPPET_CATEGORIES.items():
            cat_wrapper = ctk.CTkFrame(scroll_snips, fg_color="transparent")
            cat_wrapper.pack(fill="x", pady=2)

            content_frame = ctk.CTkFrame(cat_wrapper, fg_color="transparent")

            btn_cat = ctk.CTkButton(
                cat_wrapper,
                text=f"▶ {category}",
                anchor="w",
                height=30,
                fg_color="#262626",
                hover_color="#383838",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#64b5f6"
            )
            btn_cat.pack(fill="x")
            btn_cat.configure(command=_make_category_toggle(btn_cat, content_frame, category))

            for item in items:
                btn_snip = ctk.CTkButton(
                    content_frame,
                    text=f"+ {item['name']}",
                    anchor="w",
                    height=26,
                    fg_color="#333333",
                    hover_color="#1f6aa5",
                    font=ctk.CTkFont(size=11),
                    command=lambda c=item["code"]: self._insert_snippet(c)
                )
                btn_snip.pack(fill="x", pady=1)

        # 우: 에디터 + 콘솔
        editor_frame = ctk.CTkFrame(body, corner_radius=6)
        editor_frame.grid(row=0, column=1, padx=6, pady=6, sticky="nsew")
        editor_frame.grid_rowconfigure(0, weight=3)
        editor_frame.grid_rowconfigure(1, weight=1)
        editor_frame.grid_columnconfigure(0, weight=1)

        self.txt_script_editor = ctk.CTkTextbox(editor_frame, font=ctk.CTkFont(family="Consolas", size=13), wrap="none")
        self.txt_script_editor.grid(row=0, column=0, padx=6, pady=(6, 3), sticky="nsew")
        self._load_default_sample_script()

        console_box = ctk.CTkFrame(editor_frame, corner_radius=6)
        console_box.grid(row=1, column=0, padx=6, pady=(3, 6), sticky="nsew")

        c_head = ctk.CTkFrame(console_box, fg_color="transparent")
        c_head.pack(fill="x", padx=8, pady=(4, 2))
        ctk.CTkLabel(c_head, text="💻 실시간 실행 콘솔 출력", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        ctk.CTkButton(c_head, text="로그 지우기", width=70, height=20, font=ctk.CTkFont(size=10), command=lambda: self.txt_script_console.delete("1.0", "end")).pack(side="right")

        self.txt_script_console = ctk.CTkTextbox(console_box, font=ctk.CTkFont(family="Consolas", size=11), fg_color="#181818")
        self.txt_script_console.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    def _insert_snippet(self, code_text: str):
        self.txt_script_editor.insert("insert", code_text + "\n")
        self.txt_script_editor.focus_set()

    def _load_default_sample_script(self):
        sample = """# =============================================================================
# UBUS 계약서 RPA 자동화 파이썬 스크립트
# =============================================================================
import re
from playwright.sync_api import sync_playwright

def run(playwright):
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    # 1. 로그인
    page.goto("http://175.119.156.105:3000/")
    page.get_by_role("textbox", name="ID").fill("dragonrpa")
    page.get_by_role("textbox", name="비밀번호").fill("1111")
    page.get_by_role("button", name="로그인").click()

    # 2. 계약조회 이동
    page.locator("a").filter(has_text=re.compile(r"^계약$")).click()
    page.locator("a").filter(has_text="계약조회").click()
    page.wait_for_load_state("domcontentloaded")

    # 3. 단일 테스트 실행
    print(">>> 계약조회 진입 완료!")
    context.close()
    browser.close()

if __name__ == "__main__":
    with sync_playwright() as p:
        run(p)
"""
        self.txt_script_editor.insert("1.0", sample)

    def _run_standalone_script(self):
        code = self.txt_script_editor.get("1.0", "end").strip()
        if not code:
            return
        self.txt_script_console.delete("1.0", "end")
        self.txt_script_console.insert("end", "=== [스크립트 단독 실행 시작] ===\n")

        temp_py = os.path.abspath("_temp_standalone.py")
        with open(temp_py, "w", encoding="utf-8") as f:
            f.write(code)

        def _worker():
            try:
                proc = subprocess.Popen(
                    [sys.executable, temp_py],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace"
                )
                for line in proc.stdout:
                    self.after(0, lambda l=line: (self.txt_script_console.insert("end", l), self.txt_script_console.see("end")))
                proc.wait()
                self.after(0, lambda: self.txt_script_console.insert("end", f"\n=== [실행 완료 (종료 코드: {proc.returncode})] ===\n"))
            except Exception as e:
                self.after(0, lambda: self.txt_script_console.insert("end", f"실행 에러: {e}\n"))
            finally:
                if os.path.exists(temp_py):
                    try:
                        os.remove(temp_py)
                    except Exception:
                        pass

        threading.Thread(target=_worker, daemon=True).start()

    def _save_script_file(self):
        p = filedialog.asksaveasfilename(defaultextension=".py", filetypes=[("파이썬", "*.py")], initialfile="custom_rpa.py")
        if p:
            with open(p, "w", encoding="utf-8") as f:
                f.write(self.txt_script_editor.get("1.0", "end"))
            messagebox.showinfo("저장 완료", f"스크립트가 저장되었습니다:\n{p}")

    def _load_script_file(self):
        p = filedialog.askopenfilename(filetypes=[("파이썬", "*.py")])
        if p:
            with open(p, "r", encoding="utf-8") as f:
                c = f.read()
            self.txt_script_editor.delete("1.0", "end")
            self.txt_script_editor.insert("1.0", c)

    def _open_db_modules_modal(self):
        """Neon DB에 저장된 모듈형 RPA 스크립트 관리 및 불러오기/저장 모달"""
        modal = ctk.CTkToplevel(self)
        modal.title("☁️ Neon DB 모듈형 RPA 스크립트 관리자 (rpa_scripts)")
        modal.geometry("900x620")
        modal.grab_set()

        db_url = self.config_mgr.get("neon_database_url", "")
        db = NeonDBManager(db_url)

        # 전체 레이아웃 (좌: 모듈 목록 / 우: 모듈 편집 및 액션)
        modal.grid_columnconfigure(0, weight=0, minsize=300)
        modal.grid_columnconfigure(1, weight=1)
        modal.grid_rowconfigure(0, weight=1)

        # 좌측: 모듈 목록 패널
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

        # 우측: 모듈 세부 정보 및 코드 편집
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


    # -------------------------------------------------------------------------
    # 탭 3: 윈도우 앱 자동화 (Desktop / UIA)
    # -------------------------------------------------------------------------
    def _build_desktop_tab(self):
        """윈도우 앱 자동화 4대 Fallback 테스트 콘솔 탭"""
        top_d = ctk.CTkFrame(self.tab_desktop, corner_radius=6)
        top_d.pack(fill="x", padx=8, pady=6)

        ctk.CTkLabel(
            top_d, text="윈도우 앱 자동화 (UIA / PIXEL_MATCH / KVM)",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left", padx=12, pady=8)

        body_d = ctk.CTkFrame(self.tab_desktop, corner_radius=6)
        body_d.pack(fill="both", expand=True, padx=8, pady=4)
        body_d.grid_columnconfigure(0, weight=0, minsize=320)
        body_d.grid_columnconfigure(1, weight=1)
        body_d.grid_rowconfigure(0, weight=1)

        # 좌: 4대 Fallback 도구 패널
        tool_panel = ctk.CTkFrame(body_d, corner_radius=6)
        tool_panel.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")

        ctk.CTkLabel(
            tool_panel, text="🛡️ 4단계 Fallback 자동화 도구",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=10, pady=(10, 4))

        # FIND_WINDOW
        fw_frame = ctk.CTkFrame(tool_panel, fg_color="#2b2b2b", corner_radius=6)
        fw_frame.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(fw_frame, text="🔍 FIND_WINDOW — 창 찾기 및 포커스", font=ctk.CTkFont(size=12, weight="bold"), text_color="#64b5f6").pack(anchor="w", padx=8, pady=(6, 2))
        ctk.CTkLabel(fw_frame, text="창 제목 키워드", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=8)
        self.entry_fw_title = ctk.CTkEntry(fw_frame, height=28, placeholder_text="예: 사내 ERP - 계약관리")
        self.entry_fw_title.pack(fill="x", padx=8, pady=(2, 4))
        ctk.CTkButton(fw_frame, text="창 찾기 및 포커스 이동", height=28, command=self._run_find_window).pack(fill="x", padx=8, pady=(0, 8))

        # UIA_CONTROL
        uia_frame = ctk.CTkFrame(tool_panel, fg_color="#2b2b2b", corner_radius=6)
        uia_frame.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(uia_frame, text="🤖 UIA_CONTROL — pywinauto 컨트롤 조작", font=ctk.CTkFont(size=12, weight="bold"), text_color="#64b5f6").pack(anchor="w", padx=8, pady=(6, 2))

        ctk.CTkLabel(uia_frame, text="프로세스명 또는 창 제목", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=8)
        self.entry_uia_wintitle = ctk.CTkEntry(uia_frame, height=28, placeholder_text="예: 계약관리")
        self.entry_uia_wintitle.pack(fill="x", padx=8, pady=(2, 4))

        uia_mid = ctk.CTkFrame(uia_frame, fg_color="transparent")
        uia_mid.pack(fill="x", padx=8, pady=2)
        uia_mid.grid_columnconfigure((0, 1), weight=1)

        f_auto_id = ctk.CTkFrame(uia_mid, fg_color="transparent")
        f_auto_id.grid(row=0, column=0, padx=(0, 4), sticky="ew")
        ctk.CTkLabel(f_auto_id, text="AutomationId", font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.entry_uia_auto_id = ctk.CTkEntry(f_auto_id, height=28, placeholder_text="예: btnSave")
        self.entry_uia_auto_id.pack(fill="x", pady=(2, 0))

        f_ctrl_type = ctk.CTkFrame(uia_mid, fg_color="transparent")
        f_ctrl_type.grid(row=0, column=1, padx=(4, 0), sticky="ew")
        ctk.CTkLabel(f_ctrl_type, text="조작 유형", font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.cbo_uia_op = ctk.CTkComboBox(f_ctrl_type, values=["Click", "SetValue", "GetValue"], height=28)
        self.cbo_uia_op.pack(fill="x", pady=(2, 0))

        ctk.CTkLabel(uia_frame, text="입력값 (SetValue 시)", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=8, pady=(4, 0))
        self.entry_uia_value = ctk.CTkEntry(uia_frame, height=28, placeholder_text="예: {{계약번호}}")
        self.entry_uia_value.pack(fill="x", padx=8, pady=(2, 4))
        ctk.CTkButton(uia_frame, text="UIA 컨트롤 조작 실행", height=28, command=self._run_uia_control).pack(fill="x", padx=8, pady=(0, 8))

        # PIXEL_MATCH
        pm_frame = ctk.CTkFrame(tool_panel, fg_color="#2b2b2b", corner_radius=6)
        pm_frame.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(pm_frame, text="🖼️ PIXEL_MATCH — 이미지 매칭 클릭", font=ctk.CTkFont(size=12, weight="bold"), text_color="#64b5f6").pack(anchor="w", padx=8, pady=(6, 2))
        ctk.CTkLabel(pm_frame, text="버튼 이미지 파일 경로", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=8)
        pm_row = ctk.CTkFrame(pm_frame, fg_color="transparent")
        pm_row.pack(fill="x", padx=8, pady=(2, 4))
        self.entry_pm_img = ctk.CTkEntry(pm_row, height=28)
        self.entry_pm_img.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(pm_row, text="파일 선택", width=70, height=28,
                      command=lambda: self._choose_image_file(self.entry_pm_img)).pack(side="right")

        pm_conf_row = ctk.CTkFrame(pm_frame, fg_color="transparent")
        pm_conf_row.pack(fill="x", padx=8, pady=2)
        ctk.CTkLabel(pm_conf_row, text="유사도 임계값 (0.0~1.0)", font=ctk.CTkFont(size=11)).pack(side="left")
        self.entry_pm_conf = ctk.CTkEntry(pm_conf_row, height=26, width=60)
        self.entry_pm_conf.pack(side="right")
        self.entry_pm_conf.insert(0, "0.85")
        ctk.CTkButton(pm_frame, text="이미지 매칭 클릭 실행", height=28, command=self._run_pixel_match).pack(fill="x", padx=8, pady=(4, 8))

        # KVM_INPUT
        kvm_frame = ctk.CTkFrame(tool_panel, fg_color="#2b2b2b", corner_radius=6)
        kvm_frame.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(kvm_frame, text="⌨️ KVM_INPUT — OS 마우스/키보드 직접 제어", font=ctk.CTkFont(size=12, weight="bold"), text_color="#64b5f6").pack(anchor="w", padx=8, pady=(6, 2))

        kvm_mid = ctk.CTkFrame(kvm_frame, fg_color="transparent")
        kvm_mid.pack(fill="x", padx=8, pady=2)
        kvm_mid.grid_columnconfigure((0, 1, 2), weight=1)

        f_x = ctk.CTkFrame(kvm_mid, fg_color="transparent"); f_x.grid(row=0, column=0, padx=(0, 2), sticky="ew")
        ctk.CTkLabel(f_x, text="X 좌표", font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.entry_kvm_x = ctk.CTkEntry(f_x, height=28); self.entry_kvm_x.pack(fill="x"); self.entry_kvm_x.insert(0, "500")

        f_y = ctk.CTkFrame(kvm_mid, fg_color="transparent"); f_y.grid(row=0, column=1, padx=2, sticky="ew")
        ctk.CTkLabel(f_y, text="Y 좌표", font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.entry_kvm_y = ctk.CTkEntry(f_y, height=28); self.entry_kvm_y.pack(fill="x"); self.entry_kvm_y.insert(0, "300")

        f_hotkey = ctk.CTkFrame(kvm_mid, fg_color="transparent"); f_hotkey.grid(row=0, column=2, padx=(2, 0), sticky="ew")
        ctk.CTkLabel(f_hotkey, text="단축키", font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.entry_kvm_hotkey = ctk.CTkEntry(f_hotkey, height=28); self.entry_kvm_hotkey.pack(fill="x"); self.entry_kvm_hotkey.insert(0, "ctrl+s")

        kvm_text_row = ctk.CTkFrame(kvm_frame, fg_color="transparent")
        kvm_text_row.pack(fill="x", padx=8, pady=(4, 2))
        ctk.CTkLabel(kvm_text_row, text="타이핑할 텍스트 (선택)", font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.entry_kvm_text = ctk.CTkEntry(kvm_text_row, height=28, placeholder_text="예: 2D2607007")
        self.entry_kvm_text.pack(fill="x", pady=(2, 0))

        kvm_btn_row = ctk.CTkFrame(kvm_frame, fg_color="transparent")
        kvm_btn_row.pack(fill="x", padx=8, pady=(4, 8))
        ctk.CTkButton(kvm_btn_row, text="좌표 클릭", width=80, height=28, command=self._run_kvm_click).pack(side="left", padx=(0, 4))
        ctk.CTkButton(kvm_btn_row, text="단축키 입력", width=80, height=28, command=self._run_kvm_hotkey).pack(side="left", padx=4)
        ctk.CTkButton(kvm_btn_row, text="텍스트 타이핑", width=90, height=28, command=self._run_kvm_type).pack(side="left", padx=4)

        # UIA Live Inspector 버튼
        ctk.CTkButton(
            tool_panel, text="🔍 마우스 위치 UIA 요소 스캔 (Live Inspector)",
            height=32, fg_color="#1f6aa5", hover_color="#144d75",
            command=self._run_uia_inspector
        ).pack(fill="x", padx=8, pady=8)

        # 우: 실행 결과 콘솔
        right_panel = ctk.CTkFrame(body_d, corner_radius=6)
        right_panel.grid(row=0, column=1, padx=6, pady=6, sticky="nsew")

        con_head = ctk.CTkFrame(right_panel, fg_color="transparent")
        con_head.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(con_head, text="💻 윈도우 앱 자동화 실행 결과", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkButton(con_head, text="로그 지우기", width=70, height=22, font=ctk.CTkFont(size=10),
                      command=lambda: self.txt_desktop_console.delete("1.0", "end")).pack(side="right")

        self.txt_desktop_console = ctk.CTkTextbox(right_panel, font=ctk.CTkFont(family="Consolas", size=12), fg_color="#181818")
        self.txt_desktop_console.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.txt_desktop_console.insert("1.0", "=== 윈도우 앱 자동화 콘솔 ===\n좌측 도구 패널에서 각 Fallback 단계를 개별 테스트하십시오.\n\n")

    def _log_desktop(self, msg: str):
        def _append():
            self.txt_desktop_console.insert("end", msg + "\n")
            self.txt_desktop_console.see("end")
        self.after(0, _append)

    def _run_find_window(self):
        title_kw = self.entry_fw_title.get().strip()
        if not title_kw:
            return
        def _worker():
            try:
                import win32gui, win32con
                results = []
                def _cb(hwnd, _):
                    if title_kw in win32gui.GetWindowText(hwnd) and win32gui.IsWindowVisible(hwnd):
                        results.append((hwnd, win32gui.GetWindowText(hwnd)))
                win32gui.EnumWindows(_cb, None)
                if results:
                    hwnd, title = results[0]
                    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                    win32gui.SetForegroundWindow(hwnd)
                    self._log_desktop(f"✅ 창 포커스 이동 완료: [{title}] (hwnd={hwnd})")
                else:
                    self._log_desktop(f"⚠️ 창을 찾지 못했습니다: '{title_kw}'")
            except ImportError:
                self._log_desktop("❌ pywin32가 설치되지 않았습니다. pip install pywin32")
            except Exception as e:
                self._log_desktop(f"❌ 오류: {e}")
        threading.Thread(target=_worker, daemon=True).start()

    def _run_uia_control(self):
        win_title = self.entry_uia_wintitle.get().strip()
        auto_id   = self.entry_uia_auto_id.get().strip()
        op_type   = self.cbo_uia_op.get()
        value     = self.entry_uia_value.get().strip()
        def _worker():
            try:
                from pywinauto import Application
                app = Application(backend="uia").connect(title_re=f".*{win_title}.*")
                win = app.top_window()
                ctrl = win.child_window(auto_id=auto_id) if auto_id else win
                if op_type == "Click":
                    ctrl.click_input()
                    self._log_desktop(f"✅ UIA Click 완료: auto_id={auto_id}")
                elif op_type == "SetValue":
                    ctrl.set_edit_text(value)
                    self._log_desktop(f"✅ UIA SetValue 완료: auto_id={auto_id}, value={value}")
                elif op_type == "GetValue":
                    text = ctrl.window_text()
                    self._log_desktop(f"✅ UIA GetValue: auto_id={auto_id}, text={text}")
            except ImportError:
                self._log_desktop("❌ pywinauto가 설치되지 않았습니다. pip install pywinauto")
            except Exception as e:
                self._log_desktop(f"❌ UIA 오류: {e}")
        threading.Thread(target=_worker, daemon=True).start()

    def _choose_image_file(self, entry_widget):
        path = filedialog.askopenfilename(filetypes=[("이미지 파일", "*.png *.jpg *.bmp")])
        if path:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, path)

    def _run_pixel_match(self):
        img_path   = self.entry_pm_img.get().strip()
        confidence = float(self.entry_pm_conf.get().strip() or "0.85")
        def _worker():
            try:
                import pyautogui
                pos = pyautogui.locateOnScreen(img_path, confidence=confidence, grayscale=True)
                if pos:
                    pyautogui.click(pos)
                    self._log_desktop(f"✅ PIXEL_MATCH 클릭 완료: {pos}")
                else:
                    self._log_desktop(f"⚠️ 이미지를 화면에서 찾지 못했습니다: {img_path}")
            except ImportError:
                self._log_desktop("❌ pyautogui가 설치되지 않았습니다. pip install pyautogui")
            except Exception as e:
                self._log_desktop(f"❌ PIXEL_MATCH 오류: {e}")
        threading.Thread(target=_worker, daemon=True).start()

    def _run_kvm_click(self):
        try:
            x, y = int(self.entry_kvm_x.get()), int(self.entry_kvm_y.get())
            import pyautogui; pyautogui.click(x, y)
            self._log_desktop(f"✅ KVM 좌표 클릭 완료: ({x}, {y})")
        except Exception as e:
            self._log_desktop(f"❌ KVM 클릭 오류: {e}")

    def _run_kvm_hotkey(self):
        try:
            hotkey = self.entry_kvm_hotkey.get().strip()
            import pyautogui; pyautogui.hotkey(*hotkey.split("+"))
            self._log_desktop(f"✅ KVM 단축키 입력 완료: {hotkey}")
        except Exception as e:
            self._log_desktop(f"❌ KVM 단축키 오류: {e}")

    def _run_kvm_type(self):
        try:
            text = self.entry_kvm_text.get().strip()
            import pyautogui; pyautogui.typewrite(text, interval=0.05)
            self._log_desktop(f"✅ KVM 타이핑 완료: {text}")
        except Exception as e:
            self._log_desktop(f"❌ KVM 타이핑 오류: {e}")

    def _run_uia_inspector(self):
        def _worker():
            try:
                import win32api
                from pywinauto import Desktop
                x, y = win32api.GetCursorPos()
                el = Desktop(backend="uia").from_point(x, y)
                info = {
                    "control_type":  el.element_info.control_type,
                    "automation_id": el.element_info.automation_id,
                    "name":          el.element_info.name,
                    "class_name":    el.element_info.class_name,
                    "rect":          str(el.element_info.rectangle),
                }
                self._log_desktop(f"✅ UIA 스캔 결과 (좌표 {x},{y}):")
                for k, v in info.items():
                    self._log_desktop(f"   {k}: {v}")
            except ImportError:
                self._log_desktop("❌ pywinauto 또는 pywin32가 설치되지 않았습니다.")
            except Exception as e:
                self._log_desktop(f"❌ UIA 스캔 오류: {e}")
        threading.Thread(target=_worker, daemon=True).start()

    # -------------------------------------------------------------------------
    # 탭 4: 시나리오 JSON 뷰어
    # -------------------------------------------------------------------------
    def _build_scenario_tab(self):
        top_sc = ctk.CTkFrame(self.tab_scenario, corner_radius=6)
        top_sc.pack(fill="x", padx=8, pady=6)

        ctk.CTkLabel(top_sc, text="적용 중인 RPA 시나리오 (scenario.json)", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=12, pady=8)
        ctk.CTkButton(top_sc, text="외부 시나리오 파일 불러오기", width=170, height=32, command=self._load_external_scenario).pack(side="right", padx=10, pady=8)

        body_sc = ctk.CTkFrame(self.tab_scenario, corner_radius=6)
        body_sc.pack(fill="both", expand=True, padx=8, pady=4)

        self.txt_scenario_view = ctk.CTkTextbox(body_sc, font=ctk.CTkFont(family="Consolas", size=12))
        self.txt_scenario_view.pack(fill="both", expand=True, padx=10, pady=10)

    def _load_external_scenario(self):
        path = filedialog.askopenfilename(filetypes=[("RPA 시나리오", "*.json")])
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.scenario_mgr.data = json.load(f)
                self.config_mgr.set("scenario_file", path)
                self._refresh_scenario_view()
                messagebox.showinfo("적용 완료", f"시나리오가 교체되었습니다:\n{path}")
            except Exception as e:
                messagebox.showerror("오류", f"시나리오 로드 실패: {e}")

    def _refresh_scenario_view(self):
        self.txt_scenario_view.delete("1.0", "end")
        self.txt_scenario_view.insert("1.0", json.dumps(self.scenario_mgr.data, ensure_ascii=False, indent=2))

    # -------------------------------------------------------------------------
    # 탭 4: PDF 테스트
    # -------------------------------------------------------------------------
    def _build_test_tab(self):
        test_frame = ctk.CTkFrame(self.tab_test, corner_radius=6)
        test_frame.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(test_frame, text="단일 PDF 키워드 추출 사전 검증", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=12, pady=(10, 6))

        file_bar = ctk.CTkFrame(test_frame, fg_color="transparent")
        file_bar.pack(fill="x", padx=12, pady=6)

        self.entry_test_file = ctk.CTkEntry(file_bar, placeholder_text="테스트할 PDF 파일을 선택하십시오.", height=32)
        self.entry_test_file.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(file_bar, text="파일 선택", width=90, height=32, command=self._choose_test_pdf).pack(side="left", padx=(0, 6))
        ctk.CTkButton(file_bar, text="추출 테스트 실행", width=120, height=32, fg_color="#1f6aa5", command=self._run_single_test).pack(side="left")

        res_box = ctk.CTkFrame(test_frame)
        res_box.pack(fill="both", expand=True, padx=12, pady=10)

        ctk.CTkLabel(res_box, text="추출 결과 (JSON 및 변경 파일명 미리보기)", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(8, 4))
        self.txt_test_result = ctk.CTkTextbox(res_box, font=ctk.CTkFont(family="Consolas", size=12))
        self.txt_test_result.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _choose_test_pdf(self):
        chosen = filedialog.askopenfilename(filetypes=[("PDF 파일", "*.pdf")])
        if chosen:
            self.entry_test_file.delete(0, "end")
            self.entry_test_file.insert(0, chosen)

    def _run_single_test(self):
        pdf_path = self.entry_test_file.get().strip()
        if not pdf_path or not os.path.exists(pdf_path):
            messagebox.showwarning("파일 확인", "올바른 PDF 파일을 선택하십시오.")
            return

        model = self.cbo_model.get().strip()
        keywords = [k.strip() for k in self.entry_keywords.get().split(",") if k.strip()]
        template = self.entry_template.get().strip()

        self.txt_test_result.delete("1.0", "end")
        self.txt_test_result.insert("1.0", f"[{model}] 모델을 통해 키워드 분석 중...\n")

        def _worker():
            try:
                extractor = PDFExtractor(self.config_mgr.get("ollama_url"), model)
                res = extractor.process_file(pdf_path, keywords)
                new_fn = self.pipeline.generate_new_filename(res, template, os.path.basename(pdf_path))
                out = (
                    "=== 키워드 추출 결과 ===\n"
                    + json.dumps(res, ensure_ascii=False, indent=2)
                    + f"\n\n=== 변경 예정 파일명 ===\n{new_fn}\n"
                )
                self.after(0, lambda: self.txt_test_result.delete("1.0", "end"))
                self.after(0, lambda: self.txt_test_result.insert("1.0", out))
            except Exception as e:
                self.after(0, lambda: self.txt_test_result.insert("end", f"\n테스트 오류: {e}"))

        threading.Thread(target=_worker, daemon=True).start()

    # -------------------------------------------------------------------------
    # 설정 로드 & 저장
    # -------------------------------------------------------------------------
    def _load_values_to_ui(self):
        self.entry_erp_url.insert(0, self.config_mgr.get("erp_url"))
        self.entry_user_id.insert(0, self.config_mgr.get("user_id"))
        self.entry_user_pw.insert(0, self.config_mgr.get("user_pw"))
        self.entry_keywords.insert(0, self.config_mgr.get("extract_keywords"))
        self.entry_template.insert(0, self.config_mgr.get("rename_template"))
        
        model_val = self.config_mgr.get("ollama_model")
        if model_val:
            self.cbo_model.set(model_val)

        if not self.config_mgr.get("headless", False):
            self.chk_headless.select()
        else:
            self.chk_headless.deselect()

        self.entry_input_dir.insert(0, self.config_mgr.get("input_dir"))
        self.entry_ocr_done_dir.insert(0, self.config_mgr.get("ocr_done_dir"))
        self.entry_rpa_done_dir.insert(0, self.config_mgr.get("rpa_done_dir"))

        self._refresh_scenario_view()

    def save_current_settings(self):
        new_config = {
            "erp_url": self.entry_erp_url.get().strip(),
            "user_id": self.entry_user_id.get().strip(),
            "user_pw": self.entry_user_pw.get().strip(),
            "extract_keywords": self.entry_keywords.get().strip(),
            "ollama_model": self.cbo_model.get().strip(),
            "rename_template": self.entry_template.get().strip(),
            "headless": not self.chk_headless.get(),
            "input_dir": self.entry_input_dir.get().strip(),
            "ocr_done_dir": self.entry_ocr_done_dir.get().strip(),
            "rpa_done_dir": self.entry_rpa_done_dir.get().strip()
        }
        self.config_mgr.save_config(new_config)
        self.pipeline.update_directories(
            new_config["input_dir"],
            new_config["ocr_done_dir"],
            new_config["rpa_done_dir"],
            self.config_mgr.get("error_dir")
        )
        self.log_message("현재 설정이 성공적으로 저장되었습니다.")

    def log_message(self, message: str, level: str = "INFO"):
        def _append():
            self.txt_log.insert("end", message + "\n")
            self.txt_log.see("end")
        self.after(0, _append)

    # -------------------------------------------------------------------------
    # 메인 파이프라인 가동
    # -------------------------------------------------------------------------
    def start_pipeline(self):
        if self.is_running:
            return

        self.save_current_settings()
        self.is_running = True
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.prog_bar.set(0)

        self.worker_thread = threading.Thread(target=self._pipeline_worker, daemon=True)
        self.worker_thread.start()

    def stop_pipeline(self):
        if not self.is_running:
            return
        self.log_message("작업 중지 요청됨...", "WARN")
        self.is_running = False
        if self.runner:
            self.runner.close_session()
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")

    def _pipeline_worker(self):
        try:
            self.log_message("==================================================")
            self.log_message("UBUS 계약서 자동화 재생 파이프라인 가동")
            self.log_message("==================================================")

            files = self.pipeline.get_input_files()
            total_count = len(files)
            if total_count == 0:
                self.log_message(f"대기 폴더에 처리할 PDF 파일이 없습니다: {self.pipeline.input_dir}", "WARN")
                return

            self.log_message(f"총 {total_count}건의 PDF 계약서 파일 감지.")

            ollama_url = self.config_mgr.get("ollama_url")
            model = self.cbo_model.get().strip()
            keywords = [k.strip() for k in self.entry_keywords.get().split(",") if k.strip()]
            template = self.entry_template.get().strip()
            erp_url = self.entry_erp_url.get().strip()
            user_id = self.entry_user_id.get().strip()
            user_pw = self.entry_user_pw.get().strip()
            headless = not self.chk_headless.get()

            extractor = PDFExtractor(ollama_url, model)
            self.runner = ScenarioRunner(self.scenario_mgr.data, headless=headless, log_callback=self.log_message)

            if not self.runner.start_session():
                self.log_message("브라우저 재생 세션 기동 실패", "ERROR")
                return

            # 1회 초기화/로그인
            global_vars = {
                "ERP_URL": erp_url,
                "USER_ID": user_id,
                "USER_PW": user_pw
            }
            if not self.runner.run_setup_steps(global_vars):
                self.log_message("초기화(로그인) 실패로 작업을 중단합니다.", "ERROR")
                return

            success_count = 0
            fail_count = 0

            for idx, pdf_path in enumerate(files):
                if not self.is_running:
                    self.log_message("사용자에 의해 중단되었습니다.", "WARN")
                    break

                current_num = idx + 1
                orig_name = os.path.basename(pdf_path)
                self.log_message(f"\n--- [{current_num}/{total_count}] 작업 처리 중: {orig_name} ---")

                # Step A: AI 키워드 추출
                self.log_message(f"[{current_num}] Ollama AI 키워드 분석 진행...")
                extracted = extractor.process_file(pdf_path, keywords)
                contract_no = extracted.get("계약번호", "").strip()

                self.log_message(f"[{current_num}] 추출 결과: {extracted}")

                if not contract_no:
                    self.log_message(f"[{current_num}] 계약번호 추출 실패 ➔ 오류 폴더 격리", "ERROR")
                    self.pipeline.move_to_error(pdf_path, f"계약번호 추출 실패: {extracted}")
                    fail_count += 1
                    self._update_stats(total_count, current_num, success_count, fail_count)
                    continue

                # Step B: 2단계 파일명 변경 및 이동
                ok_move, ocr_done_path, new_filename = self.pipeline.move_to_ocr_done(
                    pdf_path, extracted, template
                )
                if not ok_move:
                    self.log_message(f"[{current_num}] 파일 이동 실패: {orig_name}", "ERROR")
                    fail_count += 1
                    self._update_stats(total_count, current_num, success_count, fail_count)
                    continue

                self.log_message(f"[{current_num}] 파일명 변경 및 2단계 이동 ➔ {new_filename}")

                # Step C: 시나리오 반복 루프 재생
                item_vars = {
                    "ERP_URL": erp_url,
                    "계약번호": contract_no,
                    "첨부파일_경로": ocr_done_path,
                    "파일명": new_filename
                }
                item_vars.update(extracted)

                rpa_ok = self.runner.run_loop_steps(item_vars)

                if rpa_ok:
                    self.pipeline.move_to_rpa_done(ocr_done_path)
                    success_count += 1
                    self.log_message(f"[{current_num}] 3단계 최종 완료 보관 폴더로 이동됨", "SUCCESS")
                else:
                    self.pipeline.move_to_error(ocr_done_path, f"RPA 루프 실행 실패 (계약번호: {contract_no})")
                    fail_count += 1
                    self.log_message(f"[{current_num}] RPA 처리 실패 ➔ 오류 격리", "ERROR")

                self._update_stats(total_count, current_num, success_count, fail_count)

            self.log_message("\n==================================================")
            self.log_message(f"모든 작업 완료! (성공: {success_count}건, 실패: {fail_count}건)")
            self.log_message("==================================================")

        except Exception as e:
            self.log_message(f"치명적 오류 발생: {e}", "ERROR")
        finally:
            if self.runner:
                self.runner.close_session()
            self.is_running = False
            self.after(0, lambda: self.btn_start.configure(state="normal"))
            self.after(0, lambda: self.btn_stop.configure(state="disabled"))

    def _update_stats(self, total: int, current: int, success: int, fail: int):
        def _apply():
            rem = total - current
            self.lbl_stats.configure(
                text=f"대기: {rem}건 | 진행: {current}/{total} | 성공: {success} | 실패: {fail}"
            )
            if total > 0:
                self.prog_bar.set(current / total)
    def _open_windows_spy(self):
        """Microsoft Windows UIA Spy 창 열기"""
        from windows_spy import open_windows_spy
        open_windows_spy(
            self,
            on_insert=lambda code: self._insert_snippet(code)
        )

    def _open_ai_vision_generator(self):
        """Google Gemini Vision AI 코드 & 셀렉터 생성기 창 열기"""
        from ai_vision_agent import open_ai_vision_generator
        open_ai_vision_generator(
            self,
            on_insert=lambda code: self._insert_snippet(code)
        )


def main():
    app = UBUSApp()
    app.mainloop()


if __name__ == "__main__":
    main()
