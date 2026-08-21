"""
Universal RPA Recorder & Bot Builder
범용 RPA 스크립트 IDE + 모듈 기반 2분할 봇 에디터 (Bot Builder)
Playwright 웹 + 윈도우 데스크톱 4단계 Fallback + Neon Cloud DB 실시간 연동
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
    # [2단계: PDF 건별 반복 루프]
    # -------------------------------------------------------------------------
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
    """Universal RPA 스튜디오 & 모듈형 봇 에디터 메인 GUI"""

    _CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recorder_config.json")

    def __init__(self):
        super().__init__()

        self.title("범용 RPA 스튜디오 & 봇 에디터 (Universal RPA Studio & Bot Builder)")
        self.geometry("1400x900")
        self.minsize(1180, 760)

        # 봇 파이프라인 데이터 모델 (모듈 카드들의 리스트)
        self.bot_modules: List[Dict[str, Any]] = []
        self.db_manager = NeonDBManager(self._load_neon_url())

        self._build_ui()
        self._load_default_bot_template()

    @property
    def txt_script_editor(self):
        return self.txt_code

    def _build_ui(self):
        """메인 탭 레이아웃 구성"""
        self.tabview = ctk.CTkTabview(self, corner_radius=6)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_script = self.tabview.add("🐍 파이썬 스크립트 에디터 (스니펫 지원)")
        self.tab_bot = self.tabview.add("🤖 봇 에디터 (Bot Builder)")

        self._build_script_tab()
        self._build_bot_tab()

    # =========================================================================
    # 탭 1: 스크립트 코드 에디터 (IDE)
    # =========================================================================
    def _build_script_tab(self):
        # 0. 대상 URL 설정 행
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
            top_bar, text="Playwright 인스펙터", width=160, height=34,
            fg_color="#1f6aa5", hover_color="#144d75", command=self.launch_codegen
        )
        btn_codegen.pack(side="left", padx=4, pady=6)

        btn_win_spy = ctk.CTkButton(
            top_bar, text="🔍 Windows UIA Spy", width=170, height=34,
            fg_color="#4a148c", hover_color="#311b92", font=ctk.CTkFont(weight="bold"),
            command=self.open_windows_spy
        )
        btn_win_spy.pack(side="left", padx=4, pady=6)

        btn_convert_to_bot = ctk.CTkButton(
            top_bar, text="🧩 스크립트 ➔ 봇 모듈로 변환", width=190, height=34,
            fg_color="#00838f", hover_color="#006064", font=ctk.CTkFont(weight="bold"),
            command=self._convert_script_to_bot_modules
        )
        btn_convert_to_bot.pack(side="left", padx=4, pady=6)

        btn_db_modules = ctk.CTkButton(
            top_bar, text="☁️ DB 모듈", width=110, height=34,
            fg_color="#6a1b9a", hover_color="#4a148c", command=self._open_db_modules_modal
        )
        btn_db_modules.pack(side="left", padx=4, pady=6)

        btn_save_py = ctk.CTkButton(
            top_bar, text="💾 파이썬 저장", width=110, height=34,
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

        # 좌측: 스니펫 라이브러리
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

        # 우측: 코드 텍스트 에디터 + 콘솔 출력 창
        editor_box = ctk.CTkFrame(body_frame, corner_radius=6)
        editor_box.grid(row=0, column=1, padx=6, pady=6, sticky="nsew")
        editor_box.grid_rowconfigure(0, weight=3)
        editor_box.grid_rowconfigure(1, weight=1)
        editor_box.grid_columnconfigure(0, weight=1)

        self.txt_code = ctk.CTkTextbox(
            editor_box, font=ctk.CTkFont(family="Consolas", size=13), wrap="none"
        )
        self.txt_code.grid(row=0, column=0, padx=6, pady=(6, 3), sticky="nsew")
        self.txt_code.insert("1.0", DEFAULT_PYTHON_SCRIPT)

        console_frame = ctk.CTkFrame(editor_box, corner_radius=6)
        console_frame.grid(row=1, column=0, padx=6, pady=(3, 6), sticky="nsew")

        c_top = ctk.CTkFrame(console_frame, fg_color="transparent")
        c_top.pack(fill="x", padx=8, pady=(4, 2))
        ctk.CTkLabel(c_top, text="💻 실시간 실행 콘솔 출력", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        ctk.CTkButton(
            c_top, text="로그 지우기", width=70, height=20, font=ctk.CTkFont(size=10),
            command=lambda: self.txt_console.delete("1.0", "end")
        ).pack(side="right")

        self.txt_console = ctk.CTkTextbox(
            console_frame, font=ctk.CTkFont(family="Consolas", size=11), fg_color="#181818"
        )
        self.txt_console.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    # =========================================================================
    # 탭 2: 🤖 봇 에디터 (Bot Builder - 2분할 모듈형 조립 스튜디오)
    # =========================================================================
    def _build_bot_tab(self):
        # 본문 2분할 (좌: 봇 조립 파이프라인 55% / 우: DB 모듈 라이브러리 45%)
        bot_body = ctk.CTkFrame(self.tab_bot, corner_radius=6)
        bot_body.pack(fill="both", expand=True, padx=4, pady=4)
        bot_body.grid_columnconfigure(0, weight=6, minsize=520)
        bot_body.grid_columnconfigure(1, weight=4, minsize=420)
        bot_body.grid_rowconfigure(0, weight=1)

        # ---------------------------------------------------------------------
        # 👈 [좌측] 🤖 봇(Bot) 조립 파이프라인
        # ---------------------------------------------------------------------
        left_bot_frame = ctk.CTkFrame(bot_body, corner_radius=6)
        left_bot_frame.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")

        # 봇 헤더 메타데이터 바
        bot_meta_bar = ctk.CTkFrame(left_bot_frame, fg_color="transparent")
        bot_meta_bar.pack(fill="x", padx=8, pady=(8, 4))
        bot_meta_bar.grid_columnconfigure((0, 1), weight=1)

        # 봇 식별자 & 한글명 입력
        f_bname = ctk.CTkFrame(bot_meta_bar, fg_color="transparent")
        f_bname.grid(row=0, column=0, padx=(0, 4), sticky="ew")
        ctk.CTkLabel(f_bname, text="봇 식별자 (영문 ID)", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w")
        self.ent_bot_name = ctk.CTkEntry(f_bname, height=28, placeholder_text="예: ubus_contract_bot")
        self.ent_bot_name.pack(fill="x", pady=(1, 0))
        self.ent_bot_name.insert(0, "ubus_contract_bot")

        f_btitle = ctk.CTkFrame(bot_meta_bar, fg_color="transparent")
        f_btitle.grid(row=0, column=1, padx=(4, 0), sticky="ew")
        ctk.CTkLabel(f_btitle, text="봇 이름 (Title)", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w")
        self.ent_bot_title = ctk.CTkEntry(f_btitle, height=28, placeholder_text="예: UBUS ERP 계약서 자동 등록 봇")
        self.ent_bot_title.pack(fill="x", pady=(1, 0))
        self.ent_bot_title.insert(0, "UBUS ERP 계약서 자동 등록 봇")

        # 봇 액션 툴바
        bot_act_bar = ctk.CTkFrame(left_bot_frame, corner_radius=6)
        bot_act_bar.pack(fill="x", padx=8, pady=4)

        btn_run_bot = ctk.CTkButton(
            bot_act_bar, text="▶ 봇 전체 실행", width=130, height=32,
            fg_color="#2e7d32", hover_color="#1b5e20", font=ctk.CTkFont(weight="bold"),
            command=self._run_entire_bot
        )
        btn_run_bot.pack(side="left", padx=(6, 4), pady=6)

        btn_save_bot_db = ctk.CTkButton(
            bot_act_bar, text="💾 봇 DB 저장", width=110, height=32,
            fg_color="#6a1b9a", hover_color="#4a148c", font=ctk.CTkFont(weight="bold"),
            command=self._save_bot_to_db
        )
        btn_save_bot_db.pack(side="left", padx=4, pady=6)

        btn_load_bot_db = ctk.CTkButton(
            bot_act_bar, text="📂 봇 DB 불러오기", width=120, height=32,
            fg_color="#1f6aa5", hover_color="#144d75",
            command=self._open_load_bot_modal
        )
        btn_load_bot_db.pack(side="left", padx=4, pady=6)

        btn_win_spy_bot = ctk.CTkButton(
            bot_act_bar, text="🔍 Windows UIA Spy", width=150, height=32,
            fg_color="#4a148c", hover_color="#311b92", font=ctk.CTkFont(weight="bold"),
            command=self.open_windows_spy
        )
        btn_win_spy_bot.pack(side="left", padx=4, pady=6)

        btn_add_blank = ctk.CTkButton(
            bot_act_bar, text="+ 빈 모듈 추가", width=100, height=32,
            fg_color="#444444", hover_color="#333333",
            command=self._add_blank_module_to_bot
        )
        btn_add_blank.pack(side="right", padx=(4, 6), pady=6)

        btn_clear_bot = ctk.CTkButton(
            bot_act_bar, text="초기화", width=70, height=32,
            fg_color="#772222", hover_color="#551111",
            command=self._clear_bot_modules
        )
        btn_clear_bot.pack(side="right", padx=4, pady=6)

        # 봇 모듈 카드 스크롤 영역
        self.scroll_bot_modules = ctk.CTkScrollableFrame(left_bot_frame, corner_radius=6)
        self.scroll_bot_modules.pack(fill="both", expand=True, padx=8, pady=(2, 8))

        # ---------------------------------------------------------------------
        # 👉 [우측] 🗄️ Neon DB 모듈 라이브러리
        # ---------------------------------------------------------------------
        right_db_frame = ctk.CTkFrame(bot_body, corner_radius=6)
        right_db_frame.grid(row=0, column=1, padx=(0, 6), pady=6, sticky="nsew")

        r_head = ctk.CTkFrame(right_db_frame, fg_color="transparent")
        r_head.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(r_head, text="🗄️ Neon DB 모듈 저장소", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")

        ctk.CTkButton(
            r_head, text="🔄 새로고침", width=75, height=24, font=ctk.CTkFont(size=11),
            command=self._refresh_db_module_list
        ).pack(side="right")

        # 필터 & 검색 바
        filter_bar = ctk.CTkFrame(right_db_frame, fg_color="transparent")
        filter_bar.pack(fill="x", padx=8, pady=(0, 6))

        self.cbo_bot_cat_filter = ctk.CTkComboBox(
            filter_bar, values=["전체", "로그인", "웹조작", "윈도우앱", "OCR", "DB", "스니펫", "유틸", "사용자정의"],
            width=120, height=28, command=lambda _: self._refresh_db_module_list()
        )
        self.cbo_bot_cat_filter.pack(side="left", padx=(0, 6))
        self.cbo_bot_cat_filter.set("전체")

        self.ent_search_db = ctk.CTkEntry(filter_bar, height=28, placeholder_text="🔍 모듈 검색...")
        self.ent_search_db.pack(side="left", fill="x", expand=True)
        self.ent_search_db.bind("<KeyRelease>", lambda _: self._refresh_db_module_list())

        # DB 모듈 스크롤 목록
        self.scroll_db_modules = ctk.CTkScrollableFrame(right_db_frame, corner_radius=6)
        self.scroll_db_modules.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._refresh_db_module_list()

    # =========================================================================
    # 봇 파이프라인 카드 렌더링 & 제어 로직
    # =========================================================================
    def _render_bot_cards(self):
        """좌측 봇 파이프라인의 모듈 카드들을 다시 렌더링"""
        for w in self.scroll_bot_modules.winfo_children():
            w.destroy()

        if not self.bot_modules:
            empty_lbl = ctk.CTkLabel(
                self.scroll_bot_modules,
                text="🤖 조립된 모듈이 없습니다.\n우측 Neon DB 목록에서 [➕ 봇에 모듈 삽입 ➔] 버튼을 눌러 모듈을 추가하십시오.",
                font=ctk.CTkFont(size=12), text_color="#aaaaaa"
            )
            empty_lbl.pack(pady=40)
            return

        for idx, mod in enumerate(self.bot_modules):
            card = ctk.CTkFrame(self.scroll_bot_modules, corner_radius=8, fg_color="#262626", border_width=1, border_color="#3a3a3a")
            card.pack(fill="x", pady=6, padx=4)

            # 1행: 헤더 (순번, 카테고리, 제목, 액션 버튼들)
            head = ctk.CTkFrame(card, fg_color="transparent")
            head.pack(fill="x", padx=10, pady=(8, 4))

            cat = mod.get("category", "웹조작")
            title = mod.get("title", f"모듈 {idx + 1}")
            name = mod.get("name", f"mod_{idx + 1}")

            ctk.CTkLabel(
                head, text=f"Module {idx + 1}.", font=ctk.CTkFont(size=12, weight="bold"), text_color="#64b5f6"
            ).pack(side="left", padx=(0, 4))

            ctk.CTkLabel(
                head, text=f"[{cat}]", font=ctk.CTkFont(size=11, weight="bold"), text_color="#81c784"
            ).pack(side="left", padx=(0, 6))

            ctk.CTkLabel(
                head, text=title, font=ctk.CTkFont(size=12, weight="bold")
            ).pack(side="left", padx=(0, 4))

            ctk.CTkLabel(
                head, text=f"({name})", font=ctk.CTkFont(size=10), text_color="#888888"
            ).pack(side="left")

            # 우측 액션 버튼들
            ctk.CTkButton(
                head, text="✕", width=24, height=22, fg_color="#772222", hover_color="#551111",
                command=lambda i=idx: self._delete_bot_module(i)
            ).pack(side="right", padx=(4, 0))

            if idx < len(self.bot_modules) - 1:
                ctk.CTkButton(
                    head, text="▼", width=24, height=22, fg_color="#3a3a3a", hover_color="#222222",
                    command=lambda i=idx: self._move_bot_module(i, 1)
                ).pack(side="right", padx=2)

            if idx > 0:
                ctk.CTkButton(
                    head, text="▲", width=24, height=22, fg_color="#3a3a3a", hover_color="#222222",
                    command=lambda i=idx: self._move_bot_module(i, -1)
                ).pack(side="right", padx=2)

            ctk.CTkButton(
                head, text="▶ 단독실행", width=75, height=22, fg_color="#2e7d32", hover_color="#1b5e20",
                font=ctk.CTkFont(size=10, weight="bold"), command=lambda i=idx: self._run_single_module(i)
            ).pack(side="right", padx=4)

            ctk.CTkButton(
                head, text="💾 DB저장", width=65, height=22, fg_color="#6a1b9a", hover_color="#4a148c",
                font=ctk.CTkFont(size=10), command=lambda m=mod, i=idx: self._save_single_module_to_db(m, i)
            ).pack(side="right", padx=2)

            # 2행: 인라인 파이썬 코드 에디터
            f_code = ctk.CTkFrame(card, fg_color="transparent")
            f_code.pack(fill="both", expand=True, padx=10, pady=(2, 8))

            txt_card_code = ctk.CTkTextbox(
                f_code, height=140, font=ctk.CTkFont(family="Consolas", size=11),
                fg_color="#181818", wrap="none"
            )
            txt_card_code.pack(fill="both", expand=True)
            txt_card_code.insert("1.0", mod.get("code", ""))

            # 코드 포커스 아웃 시 실시간 모델 동기화
            txt_card_code.bind(
                "<FocusOut>",
                lambda e, m=mod, t=txt_card_code: self._sync_card_code(m, t.get("1.0", "end").strip())
            )

    def _sync_card_code(self, mod_dict: Dict[str, Any], new_code: str):
        mod_dict["code"] = new_code

    def _add_module_to_bot(self, mod_data: Dict[str, Any]):
        """우측 DB에서 모듈을 복사하여 좌측 봇 파이프라인에 추가"""
        new_card = {
            "name": mod_data.get("name", "custom_mod"),
            "title": mod_data.get("title", "신규 모듈"),
            "category": mod_data.get("category", "웹조작"),
            "description": mod_data.get("description", ""),
            "code": mod_data.get("code", "")
        }
        self.bot_modules.append(new_card)
        self._render_bot_cards()

    def _add_blank_module_to_bot(self):
        """빈 파이썬 모듈 카드 추가"""
        count = len(self.bot_modules) + 1
        new_card = {
            "name": f"step_{count}",
            "title": f"사용자 정의 모듈 {count}",
            "category": "사용자정의",
            "description": "파이썬 자동화 스크립트 모듈",
            "code": f"# [모듈 {count}: 사용자 정의 동작]\nprint('모듈 {count} 실행 중...')\n"
        }
        self.bot_modules.append(new_card)
        self._render_bot_cards()

    def _delete_bot_module(self, index: int):
        if 0 <= index < len(self.bot_modules):
            self.bot_modules.pop(index)
            self._render_bot_cards()

    def _move_bot_module(self, index: int, delta: int):
        new_idx = index + delta
        if 0 <= new_idx < len(self.bot_modules):
            item = self.bot_modules.pop(index)
            self.bot_modules.insert(new_idx, item)
            self._render_bot_cards()

    def _clear_bot_modules(self):
        if messagebox.askyesno("초기화 확인", "현재 조립된 봇 모듈을 모두 초기화하시겠습니까?"):
            self.bot_modules = []
            self._render_bot_cards()

    def _load_default_bot_template(self):
        """초기 기본 봇 템플릿 로드 (DB에서 핵심 모듈 자동 배치)"""
        try:
            mods = self.db_manager.list_scripts()
            if mods:
                for m_meta in mods[:3]:
                    m_full = self.db_manager.get_script(m_meta["name"])
                    if m_full:
                        self.bot_modules.append(m_full)
            self._render_bot_cards()
        except Exception:
            pass

    # =========================================================================
    # 우측: Neon DB 모듈 라이브러리 목록 렌더링
    # =========================================================================
    def _refresh_db_module_list(self):
        for w in self.scroll_db_modules.winfo_children():
            w.destroy()

        cat_filter = self.cbo_bot_cat_filter.get()
        cat_val = None if cat_filter == "전체" else cat_filter
        search_kw = self.ent_search_db.get().strip().lower()

        try:
            mods = self.db_manager.list_scripts(category=cat_val)
            if not mods:
                ctk.CTkLabel(
                    self.scroll_db_modules, text="저장된 모듈이 없습니다.", font=ctk.CTkFont(size=11)
                ).pack(pady=30)
                return

            rendered_count = 0
            for m in mods:
                if search_kw:
                    if search_kw not in m["title"].lower() and search_kw not in m["name"].lower() and search_kw not in (m.get("description") or "").lower():
                        continue

                rendered_count += 1
                card = ctk.CTkFrame(self.scroll_db_modules, corner_radius=6, fg_color="#2b2b2b")
                card.pack(fill="x", pady=4, padx=2)

                top_r = ctk.CTkFrame(card, fg_color="transparent")
                top_r.pack(fill="x", padx=8, pady=(6, 2))

                ctk.CTkLabel(
                    top_r, text=f"[{m['category']}]", font=ctk.CTkFont(size=10, weight="bold"), text_color="#64b5f6"
                ).pack(side="left")

                ctk.CTkLabel(
                    top_r, text=m['title'], font=ctk.CTkFont(size=12, weight="bold")
                ).pack(side="left", padx=6)

                ctk.CTkLabel(
                    top_r, text=m['name'], font=ctk.CTkFont(size=10), text_color="#888888"
                ).pack(side="right")

                if m.get("description"):
                    ctk.CTkLabel(
                        card, text=m["description"], font=ctk.CTkFont(size=10), text_color="#aaaaaa", anchor="w"
                    ).pack(fill="x", padx=8, pady=(0, 4))

                # 삽입 버튼
                btn_insert = ctk.CTkButton(
                    card, text="➕ 봇에 모듈 삽입 ➔", height=28, fg_color="#00838f", hover_color="#006064",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    command=lambda k=m["name"]: self._fetch_and_add_db_module(k)
                )
                btn_insert.pack(fill="x", padx=8, pady=(2, 6))

            if rendered_count == 0:
                ctk.CTkLabel(
                    self.scroll_db_modules, text="검색 결과가 없습니다.", font=ctk.CTkFont(size=11)
                ).pack(pady=20)

        except Exception as e:
            ctk.CTkLabel(
                self.scroll_db_modules, text=f"DB 연결 오류:\n{e}", text_color="#ff5555", font=ctk.CTkFont(size=11)
            ).pack(pady=20)

    def _fetch_and_add_db_module(self, mod_name: str):
        try:
            m = self.db_manager.get_script(mod_name)
            if m:
                self._add_module_to_bot(m)
        except Exception as e:
            messagebox.showerror("오류", f"모듈 가져오기 실패: {e}")

    def _save_single_module_to_db(self, mod_dict: Dict[str, Any], index: int):
        """좌측 카드에서 직접 Neon DB rpa_scripts로 저장"""
        name = mod_dict.get("name", f"mod_{index + 1}")
        title = mod_dict.get("title", f"모듈 {index + 1}")
        cat = mod_dict.get("category", "사용자정의")
        desc = mod_dict.get("description", "")
        code = mod_dict.get("code", "")

        try:
            self.db_manager.save_script(name, title, cat, code, desc)
            self._refresh_db_module_list()
            messagebox.showinfo("저장 완료", f"Neon DB에 모듈 '{title}'이(가) 저장되었습니다!")
        except Exception as e:
            messagebox.showerror("저장 오류", f"DB 저장 실패: {e}")

    # =========================================================================
    # 봇 전체 실행 및 DB 저장/불러오기
    # =========================================================================
    def _combine_bot_code(self) -> str:
        """좌측 조립된 모든 모듈의 코드를 하나의 파이썬 스크립트로 결합"""
        header = f"# =============================================================================\n" \
                 f"# RPA Bot: {self.ent_bot_title.get()} ({self.ent_bot_name.get()})\n" \
                 f"# Generated by Universal RPA Studio Bot Builder\n" \
                 f"# =============================================================================\n\n"
        
        body_parts = []
        for idx, m in enumerate(self.bot_modules, start=1):
            part = f"# -----------------------------------------------------------------------------\n" \
                   f"# [Module {idx}] {m.get('title', '')} ({m.get('name', '')})\n" \
                   f"# -----------------------------------------------------------------------------\n" \
                   f"{m.get('code', '').strip()}\n"
            body_parts.append(part)

        return header + "\n".join(body_parts)

    def _run_entire_bot(self):
        """조립된 봇 전체 결합 실행"""
        if not self.bot_modules:
            messagebox.showwarning("실행 확인", "실행할 모듈이 없습니다. 모듈을 먼저 추가하십시오.")
            return

        combined_code = self._combine_bot_code()

        # 탭 1의 에디터와 콘솔에 코드 동기화 후 실행
        self.txt_code.delete("1.0", "end")
        self.txt_code.insert("1.0", combined_code)
        self.tabview.set("🐍 파이썬 스크립트 에디터 (스니펫 지원)")
        self.run_current_script()

    def _run_single_module(self, index: int):
        """특정 모듈 1개만 단독 테스트 실행"""
        if 0 <= index < len(self.bot_modules):
            m = self.bot_modules[index]
            code = m.get("code", "").strip()
            if not code:
                messagebox.showwarning("실행 확인", "모듈 코드가 비어 있습니다.")
                return

            self.txt_code.delete("1.0", "end")
            self.txt_code.insert("1.0", code)
            self.tabview.set("🐍 파이썬 스크립트 에디터 (스니펫 지원)")
            self.run_current_script()

    def _save_bot_to_db(self):
        """완성 봇을 Neon DB rpa_bots 테이블에 저장"""
        name = self.ent_bot_name.get().strip()
        title = self.ent_bot_title.get().strip()

        if not name or not title:
            messagebox.showwarning("입력 확인", "봇 식별자(영문)와 봇 이름(한글)은 필수 항목입니다.")
            return

        if not self.bot_modules:
            messagebox.showwarning("저장 확인", "저장할 모듈 카드가 없습니다.")
            return

        combined_code = self._combine_bot_code()
        try:
            bot_id = self.db_manager.save_bot(
                name=name,
                title=title,
                modules=self.bot_modules,
                combined_code=combined_code,
                description=f"총 {len(self.bot_modules)}개 모듈로 구성된 자동화 봇"
            )
            messagebox.showinfo("저장 완료", f"Neon DB에 봇 '{title}' (ID: {bot_id})이(가) 성공적으로 저장되었습니다!")
        except Exception as e:
            messagebox.showerror("저장 오류", f"봇 DB 저장 실패: {e}")

    def _open_load_bot_modal(self):
        """Neon DB에 저장된 봇 목록을 불러오는 모달 팝업"""
        modal = ctk.CTkToplevel(self)
        modal.title("📂 Neon DB 완성 봇 불러오기")
        modal.geometry("600x480")
        modal.grab_set()

        ctk.CTkLabel(
            modal, text="🗄️ 저장된 완성 봇(Bot) 목록", font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=16, pady=(16, 8))

        scroll = ctk.CTkScrollableFrame(modal)
        scroll.pack(fill="both", expand=True, padx=16, pady=8)

        try:
            bots = self.db_manager.list_bots()
            if not bots:
                ctk.CTkLabel(scroll, text="저장된 봇이 없습니다.", font=ctk.CTkFont(size=12)).pack(pady=30)
            else:
                for b in bots:
                    card = ctk.CTkFrame(scroll, corner_radius=6, fg_color="#2b2b2b")
                    card.pack(fill="x", pady=4)

                    top_f = ctk.CTkFrame(card, fg_color="transparent")
                    top_f.pack(fill="x", padx=10, pady=(6, 2))

                    ctk.CTkLabel(
                        top_f, text=b["title"], font=ctk.CTkFont(size=13, weight="bold")
                    ).pack(side="left")

                    ctk.CTkLabel(
                        top_f, text=f"({b['name']})", font=ctk.CTkFont(size=11), text_color="#888888"
                    ).pack(side="left", padx=6)

                    # 불러오기 버튼
                    ctk.CTkButton(
                        top_f, text="불러오기 ➔", width=90, height=26, fg_color="#1f6aa5",
                        command=lambda bname=b["name"]: _do_load_bot(bname)
                    ).pack(side="right")

                    ctk.CTkButton(
                        top_f, text="삭제", width=50, height=26, fg_color="#772222", hover_color="#551111",
                        command=lambda bname=b["name"]: _do_delete_bot(bname)
                    ).pack(side="right", padx=4)

                    desc = b.get("description") or f"모듈 {b.get('module_count', 0)}개"
                    ctk.CTkLabel(
                        card, text=desc, font=ctk.CTkFont(size=10), text_color="#aaaaaa", anchor="w"
                    ).pack(fill="x", padx=10, pady=(0, 6))

        except Exception as e:
            ctk.CTkLabel(scroll, text=f"DB 조회 오류:\n{e}", text_color="#ff5555").pack(pady=20)

        def _do_load_bot(bname: str):
            try:
                full_bot = self.db_manager.get_bot(bname)
                if full_bot:
                    self.ent_bot_name.delete(0, "end"); self.ent_bot_name.insert(0, full_bot.get("name", ""))
                    self.ent_bot_title.delete(0, "end"); self.ent_bot_title.insert(0, full_bot.get("title", ""))
                    self.bot_modules = full_bot.get("modules", [])
                    self._render_bot_cards()
                    modal.destroy()
                    messagebox.showinfo("불러오기 완료", f"봇 '{full_bot.get('title')}'을(를) 성공적으로 불러왔습니다!")
            except Exception as e:
                messagebox.showerror("오류", f"봇 로드 실패: {e}")

        def _do_delete_bot(bname: str):
            if messagebox.askyesno("삭제 확인", f"정말로 봇 '{bname}'을(를) DB에서 삭제하시겠습니까?"):
                try:
                    self.db_manager.delete_bot(bname)
                    modal.destroy()
                    self._open_load_bot_modal()
                    messagebox.showinfo("삭제 완료", f"봇 '{bname}'이(가) 삭제되었습니다.")
                except Exception as e:
                    messagebox.showerror("삭제 오류", f"삭제 실패: {e}")

    def _convert_script_to_bot_modules(self):
        """현재 에디터의 파이썬 코드를 분석하여 봇 모듈 카드로 변환하고 봇 에디터 탭으로 이동"""
        code = self.txt_code.get("1.0", "end").strip()
        if not code:
            messagebox.showwarning("입력 확인", "에디터에 변환할 파이썬 코드가 없습니다.")
            return

        setup_steps, loop_steps = parse_advanced_python_to_scenario(code)
        if not setup_steps and not loop_steps:
            messagebox.showerror("변환 실패", "유효한 동작 스텝을 추출하지 못했습니다.")
            return

        # Setup 스텝들을 모듈 1로 묶고, Loop 스텝들을 모듈 2로 묶음
        new_modules = []
        if setup_steps:
            setup_code_lines = ["# [1회 실행 영역: 초기화 및 로그인]"]
            for s in setup_steps:
                if s["action"] == "GOTO":
                    setup_code_lines.append(f"page.goto('{s['value']}')")
                elif s["action"] == "FILL":
                    setup_code_lines.append(f"page.locator(\"{s['target']}\").fill('{s['value']}')")
                elif s["action"] == "CLICK":
                    setup_code_lines.append(f"page.locator(\"{s['target']}\").click()")
                elif s["action"] == "WAIT_TIME":
                    setup_code_lines.append(f"page.wait_for_timeout({s['value']})")
                else:
                    setup_code_lines.append(s.get("value") or f"# {s['title']}")

            new_modules.append({
                "name": "bot_setup_module",
                "title": "초기 세션 및 로그인 모듈",
                "category": "로그인",
                "description": f"{len(setup_steps)}개 초기 설정 동작",
                "code": "\n".join(setup_code_lines) + "\n"
            })

        if loop_steps:
            loop_code_lines = ["# [반복 실행 영역: 건별 데이터 처리 루프]", "for item in pdf_items:"]
            for s in loop_steps:
                val = s['value']
                if s["action"] == "FILL":
                    loop_code_lines.append(f"    page.locator(\"{s['target']}\").fill({val if '{{' in val else repr(val)})")
                elif s["action"] == "CLICK":
                    loop_code_lines.append(f"    page.locator(\"{s['target']}\").click()")
                elif s["action"] == "DBLCLICK":
                    loop_code_lines.append(f"    page.locator(\"{s['target']}\").dblclick()")
                elif s["action"] == "SET_FILES":
                    loop_code_lines.append(f"    page.locator(\"{s['target']}\").set_input_files({val if '{{' in val else repr(val)})")
                elif s["action"] == "WAIT_TIME":
                    loop_code_lines.append(f"    page.wait_for_timeout({s['value']})")
                else:
                    loop_code_lines.append(f"    # {s['title']}")

            new_modules.append({
                "name": "bot_loop_module",
                "title": "데이터 건별 반복 처리 모듈",
                "category": "웹조작",
                "description": f"{len(loop_steps)}개 반복 동작",
                "code": "\n".join(loop_code_lines) + "\n"
            })

        self.bot_modules = new_modules
        self._render_bot_cards()
        self.tabview.set("🤖 봇 에디터 (Bot Builder)")
        messagebox.showinfo("변환 완료", f"파이썬 코드가 총 {len(new_modules)}개의 봇 모듈로 변환되었습니다!")

    # =========================================================================
    # 공통 유틸리티 (URL 설정, Codegen, DB 모달, 파이썬 파일 I/O)
    # =========================================================================
    def _load_neon_url(self) -> str:
        """Neon DB 연결 URL 불러오기"""
        try:
            if os.path.exists(self._CONFIG_FILE):
                with open(self._CONFIG_FILE, "r", encoding="utf-8") as f:
                    u = json.load(f).get("neon_database_url", "")
                    if u:
                        return u
            ubus_cfg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "UBUS_contract", "config.json")
            if os.path.exists(ubus_cfg):
                with open(ubus_cfg, "r", encoding="utf-8") as f:
                    return json.load(f).get("neon_database_url", "")
        except Exception:
            pass
        return "postgresql://neondb_owner:npg_W0LzlYBckKp1@ep-small-firefly-az3rp5ve.c-3.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"

    def _load_script_url(self) -> str:
        try:
            if os.path.exists(self._CONFIG_FILE):
                with open(self._CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f).get("target_url", "http://175.119.156.105:3000")
        except Exception:
            pass
        return "http://175.119.156.105:3000"

    def _save_script_url(self):
        url = self.entry_script_url.get().strip()
        try:
            existing = {}
            if os.path.exists(self._CONFIG_FILE):
                with open(self._CONFIG_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            existing["target_url"] = url
            with open(self._CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("저장 완료", f"대상 URL이 저장되었습니다:\n{url}")
        except Exception as e:
            messagebox.showerror("저장 오류", f"URL 저장 실패: {e}")

    def launch_codegen(self):
        """Playwright 비주얼 인스펙터(codegen) 실행"""
        url = self.entry_script_url.get().strip() or "http://175.119.156.105:3000"
        def _run():
            cmd = [sys.executable, "-m", "playwright", "codegen", url]
            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        threading.Thread(target=_run, daemon=True).start()

    def run_current_script(self):
        """현재 에디터의 파이썬 코드 실행"""
        code = self.txt_code.get("1.0", "end").strip()
        if not code:
            messagebox.showwarning("실행 확인", "실행할 코드가 없습니다.")
            return

        self.txt_console.delete("1.0", "end")
        self.txt_console.insert("end", f"[{time.strftime('%H:%M:%S')}] ▶ RPA 파이썬 스크립트 실행 시작...\n")

        def _worker():
            temp_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_temp_run.py")
            try:
                with open(temp_py, "w", encoding="utf-8") as f:
                    f.write(code)

                p = subprocess.Popen(
                    [sys.executable, temp_py],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
                for line in p.stdout:
                    self.after(0, lambda l=line: self.txt_console.insert("end", l))
                    self.after(0, lambda: self.txt_console.see("end"))
                p.wait()
                self.after(0, lambda: self.txt_console.insert("end", f"\n[{time.strftime('%H:%M:%S')}] ✅ 실행 완료 (Exit Code: {p.returncode})\n"))
            except Exception as ex:
                self.after(0, lambda e=ex: self.txt_console.insert("end", f"\n[오류] {e}\n"))
            finally:
                if os.path.exists(temp_py):
                    try:
                        os.remove(temp_py)
                    except Exception:
                        pass

        threading.Thread(target=_worker, daemon=True).start()

    def insert_snippet_code(self, snippet: str):
        self.txt_code.insert("insert", "\n" + snippet + "\n")
        self.txt_code.focus_set()

    def save_python_file(self):
        p = filedialog.asksaveasfilename(defaultextension=".py", filetypes=[("파이썬 파일", "*.py")], initialfile="custom_bot.py")
        if p:
            with open(p, "w", encoding="utf-8") as f:
                f.write(self.txt_code.get("1.0", "end"))
            messagebox.showinfo("저장 완료", f"파일이 저장되었습니다:\n{p}")

    def load_python_file(self):
        p = filedialog.askopenfilename(filetypes=[("파이썬 파일", "*.py")])
        if p:
            with open(p, "r", encoding="utf-8") as f:
                c = f.read()
            self.txt_code.delete("1.0", "end")
            self.txt_code.insert("1.0", c)

    def reset_python_code(self):
        if messagebox.askyesno("복원 확인", "기본 예제 스크립트로 초기화하시겠습니까?"):
            self.txt_code.delete("1.0", "end")
            self.txt_code.insert("1.0", DEFAULT_PYTHON_SCRIPT)

    def _open_db_modules_modal(self):
        """DB 모듈 관리자 팝업"""
        modal = ctk.CTkToplevel(self)
        modal.title("☁️ Neon DB 모듈 라이브러리 관리자")
        modal.geometry("850x580")
        modal.grab_set()

        db = self.db_manager

        modal.grid_columnconfigure(0, weight=0, minsize=280)
        modal.grid_columnconfigure(1, weight=1)
        modal.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(modal, corner_radius=6)
        left.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")

        ctk.CTkLabel(left, text="🗄️ 모듈 목록", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=8, pady=(8, 4))
        scroll_m = ctk.CTkScrollableFrame(left)
        scroll_m.pack(fill="both", expand=True, padx=8, pady=4)

        right = ctk.CTkFrame(modal, corner_radius=6)
        right.grid(row=0, column=1, padx=(0, 8), pady=8, sticky="nsew")

        ent_name = ctk.CTkEntry(right, placeholder_text="모듈 식별자 (예: ubus_login)")
        ent_name.pack(fill="x", padx=8, pady=(8, 4))

        ent_title = ctk.CTkEntry(right, placeholder_text="모듈 한글명 (예: UBUS ERP 로그인)")
        ent_title.pack(fill="x", padx=8, pady=4)

        txt_c = ctk.CTkTextbox(right, font=ctk.CTkFont(family="Consolas", size=11), fg_color="#181818")
        txt_c.pack(fill="both", expand=True, padx=8, pady=4)

        b_row = ctk.CTkFrame(right, fg_color="transparent")
        b_row.pack(fill="x", padx=8, pady=6)

        def _refresh():
            for w in scroll_m.winfo_children():
                w.destroy()
            for item in db.list_scripts():
                btn = ctk.CTkButton(
                    scroll_m, text=f"[{item['category']}] {item['title']}", anchor="w",
                    fg_color="#333333", hover_color="#1f6aa5",
                    command=lambda k=item["name"]: _sel(k)
                )
                btn.pack(fill="x", pady=2)

        def _sel(k):
            full = db.get_script(k)
            if full:
                ent_name.delete(0, "end"); ent_name.insert(0, full["name"])
                ent_title.delete(0, "end"); ent_title.insert(0, full["title"])
                txt_c.delete("1.0", "end"); txt_c.insert("1.0", full["code"])

        def _insert():
            c = txt_c.get("1.0", "end").strip()
            if c:
                self.txt_code.insert("insert", f"\n{c}\n")
                modal.destroy()

        def _save():
            n = ent_name.get().strip()
            t = ent_title.get().strip()
            c = txt_c.get("1.0", "end").strip()
            if n and t and c:
                db.save_script(n, t, "사용자정의", c)
                _refresh()
                self._refresh_db_module_list()
                messagebox.showinfo("저장 완료", "모듈이 저장되었습니다!")

        ctk.CTkButton(b_row, text="📋 에디터에 삽입", fg_color="#2e7d32", command=_insert).pack(side="left", padx=4)
        ctk.CTkButton(b_row, text="💾 DB 저장", fg_color="#6a1b9a", command=_save).pack(side="left", padx=4)

        _refresh()

    def open_windows_spy(self):
        """Microsoft Windows UIA Spy 창 열기"""
        from windows_spy import open_windows_spy
        open_windows_spy(
            self,
            on_insert=lambda code: self.insert_snippet_code(code),
            on_add_bot=lambda mod: self._add_module_to_bot(mod)
        )



def main():
    app = RecorderGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
