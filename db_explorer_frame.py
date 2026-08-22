"""
Universal RPA Studio - Neon Database Explorer & DDL Patch Runner
- 좌측: 테이블 목록 사이드바 (실시간 행 수, 검색 필터)
- 우측 상단: 데이터 목록 및 테이블 구조(스키마) 그리드 뷰 (Treeview 다크 테마)
- 우측 하단: DDL/SQL 패치 에디터 (5줄 높이, 템플릿, 쿼리 즉시 실행, 단축키 지원)
- thread-safe Queue 패턴 적용
- 건조한 명사/동사 UI 표준 준수
"""

import os
import json
import time
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, Any, List, Optional, Tuple

import customtkinter as ctk
from neon_db import NeonDBManager


class DBExplorerFrame(ctk.CTkFrame):
    """Neon PostgreSQL 탐색기 및 DDL 패치 실행기 프레임"""

    def __init__(self, parent, db_manager: Optional[NeonDBManager] = None):
        super().__init__(parent, fg_color="transparent")

        self.db = db_manager or NeonDBManager()
        self.all_tables: List[Dict[str, Any]] = []
        self.selected_table: Optional[str] = None
        self.current_data_columns: List[str] = []
        self.current_data_rows: List[Dict[str, Any]] = []
        self.current_schema_rows: List[Dict[str, Any]] = []
        self.view_mode: str = "data"  # "data" | "schema"

        # 스레드 안전 큐
        self._task_queue: queue.Queue = queue.Queue()

        self._setup_treeview_style()
        self._build_ui()
        self._poll_task_queue()
        self._async_load_tables()

    def _poll_task_queue(self):
        """메인 스레드에서 백그라운드 작업 결과 소비"""
        try:
            while not self._task_queue.empty():
                callback, args = self._task_queue.get_nowait()
                callback(*args)
        except Exception:
            pass
        self.after(40, self._poll_task_queue)

    def _run_in_background(self, target_func, on_success, on_error=None):
        """스레드 안전 백그라운드 실행 래퍼"""
        def _worker():
            try:
                res = target_func()
                self._task_queue.put((on_success, (res,)))
            except Exception as e:
                if on_error:
                    self._task_queue.put((on_error, (str(e),)))
                else:
                    self._task_queue.put((print, (f"[DBExplorer Error] {e}",)))
        threading.Thread(target=_worker, daemon=True).start()

    def _setup_treeview_style(self):
        """다크 테마 Treeview 스타일 설정"""
        style = ttk.Style()
        try:
            style.theme_use("default")
        except Exception:
            pass

        style.configure(
            "DBView.Treeview",
            background="#1a1a1a",
            foreground="#e0e0e0",
            fieldbackground="#1a1a1a",
            rowheight=26,
            font=("Consolas", 10),
            borderwidth=0
        )
        style.configure(
            "DBView.Treeview.Heading",
            background="#252526",
            foreground="#ffffff",
            relief="flat",
            font=("Malgun Gothic", 10, "bold"),
            padding=(6, 4)
        )
        style.map(
            "DBView.Treeview.Heading",
            background=[("active", "#37373d")]
        )
        style.map(
            "DBView.Treeview",
            background=[("selected", "#094771")],
            foreground=[("selected", "#ffffff")]
        )

    def _build_ui(self):
        """전체 2분할 레이아웃 (좌: 테이블 사이드바 / 우: 그리드 & SQL 에디터)"""
        # =====================================================================
        # [좌측] 테이블 목록 사이드바
        # =====================================================================
        self.frm_sidebar = ctk.CTkFrame(self, width=250, corner_radius=6)
        self.frm_sidebar.pack(side="left", fill="y", padx=(4, 3), pady=4)
        self.frm_sidebar.pack_propagate(False)

        # 사이드바 상단 헤더
        sb_head = ctk.CTkFrame(self.frm_sidebar, fg_color="transparent")
        sb_head.pack(fill="x", padx=8, pady=(8, 4))
        
        self.lbl_table_count = ctk.CTkLabel(
            sb_head, text="테이블 목록",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.lbl_table_count.pack(side="left")

        btn_refresh_tbls = ctk.CTkButton(
            sb_head, text="새로고침", width=60, height=24,
            font=ctk.CTkFont(size=11), fg_color="#333333", hover_color="#444444",
            command=self._async_load_tables
        )
        btn_refresh_tbls.pack(side="right")

        # 테이블 검색 필터
        self.ent_search_tbl = ctk.CTkEntry(
            self.frm_sidebar, height=26, font=ctk.CTkFont(size=11),
            placeholder_text="테이블 검색..."
        )
        self.ent_search_tbl.pack(fill="x", padx=8, pady=(0, 6))
        self.ent_search_tbl.bind("<KeyRelease>", lambda e: self._filter_tables())

        # 테이블 리스트 스크롤 영역
        self.sf_tables = ctk.CTkScrollableFrame(self.frm_sidebar, fg_color="transparent")
        self.sf_tables.pack(fill="both", expand=True, padx=4, pady=(0, 6))

        # =====================================================================
        # [우측] 메인 컨테이너 (상단: 데이터/스키마 그리드 + 하단: DDL/SQL 에디터)
        # =====================================================================
        self.frm_main = ctk.CTkFrame(self, corner_radius=6, fg_color="transparent")
        self.frm_main.pack(side="left", fill="both", expand=True, padx=(3, 4), pady=4)

        # 1. 상단 액션 컨트롤 바
        top_bar = ctk.CTkFrame(self.frm_main, corner_radius=6)
        top_bar.pack(fill="x", pady=(0, 4))

        self.lbl_current_table = ctk.CTkLabel(
            top_bar, text="테이블: (선택 안됨)",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#ffd54f"
        )
        self.lbl_current_table.pack(side="left", padx=10, pady=6)

        self.lbl_data_stats = ctk.CTkLabel(
            top_bar, text="",
            font=ctk.CTkFont(size=11), text_color="#888888"
        )
        self.lbl_data_stats.pack(side="left", padx=4)

        # 우측 액션 버튼들
        btn_copy_csv = ctk.CTkButton(
            top_bar, text="CSV 복사", width=70, height=26,
            font=ctk.CTkFont(size=11), fg_color="#333333", hover_color="#444444",
            command=self._copy_data_to_csv
        )
        btn_copy_csv.pack(side="right", padx=6, pady=4)

        btn_refresh_data = ctk.CTkButton(
            top_bar, text="조회", width=55, height=26,
            font=ctk.CTkFont(size=11, weight="bold"), fg_color="#1f6aa5", hover_color="#144d75",
            command=self._reload_current_table
        )
        btn_refresh_data.pack(side="right", padx=2, pady=4)

        self.cbo_limit = ctk.CTkComboBox(
            top_bar, values=["50", "100", "300", "500", "전체"], width=80, height=26,
            font=ctk.CTkFont(size=11), command=lambda v: self._reload_current_table()
        )
        self.cbo_limit.pack(side="right", padx=4, pady=4)
        self.cbo_limit.set("100")

        self.seg_view = ctk.CTkSegmentedButton(
            top_bar, values=["데이터 목록", "테이블 구조"],
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._on_view_mode_changed
        )
        self.seg_view.pack(side="right", padx=8, pady=4)
        self.seg_view.set("데이터 목록")

        # 2. 그리드 뷰 (Treeview + 스크롤바)
        self.frm_grid_container = ctk.CTkFrame(self.frm_main, corner_radius=6, fg_color="#1a1a1a")
        self.frm_grid_container.pack(fill="both", expand=True, pady=(0, 4))

        # Y 스크롤바
        self.scroll_y = ttk.Scrollbar(self.frm_grid_container, orient="vertical")
        self.scroll_y.pack(side="right", fill="y")

        # X 스크롤바
        self.scroll_x = ttk.Scrollbar(self.frm_grid_container, orient="horizontal")
        self.scroll_x.pack(side="bottom", fill="x")

        # Treeview 생성
        self.tree = ttk.Treeview(
            self.frm_grid_container,
            style="DBView.Treeview",
            show="headings",
            yscrollcommand=self.scroll_y.set,
            xscrollcommand=self.scroll_x.set
        )
        self.tree.pack(side="left", fill="both", expand=True)

        self.scroll_y.config(command=self.tree.yview)
        self.scroll_x.config(command=self.tree.xview)

        # 더블 클릭 시 행 상세 모달 팝업
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        # 3. 하단 DDL / SQL 패치 에디터 (약 5줄 높이)
        self.frm_sql = ctk.CTkFrame(self.frm_main, corner_radius=6, height=140)
        self.frm_sql.pack(fill="x", pady=0)
        self.frm_sql.pack_propagate(False)

        # SQL 헤더 바
        sql_head = ctk.CTkFrame(self.frm_sql, fg_color="transparent")
        sql_head.pack(fill="x", padx=8, pady=(6, 2))

        ctk.CTkLabel(
            sql_head, text="SQL / DDL 실행기",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#00bcd4"
        ).pack(side="left")

        # 실행 버튼
        btn_exec = ctk.CTkButton(
            sql_head, text="쿼리 실행 (Ctrl+Enter)", width=150, height=26,
            font=ctk.CTkFont(size=11, weight="bold"), fg_color="#00838f", hover_color="#006064",
            command=self._execute_sql
        )
        btn_exec.pack(side="right", padx=2)

        btn_clear_sql = ctk.CTkButton(
            sql_head, text="초기화", width=55, height=26,
            font=ctk.CTkFont(size=11), fg_color="#444444", hover_color="#555555",
            command=lambda: self.txt_sql.delete("1.0", "end")
        )
        btn_clear_sql.pack(side="right", padx=4)

        # 템플릿 드롭다운
        self.cbo_sql_template = ctk.CTkComboBox(
            sql_head,
            values=[
                "서식 선택...",
                "SELECT * FROM {table} LIMIT 50;",
                "SELECT count(*) FROM {table};",
                "ALTER TABLE {table} ADD COLUMN new_col VARCHAR(100);",
                "CREATE INDEX idx_name ON {table}(column);",
                "CREATE TABLE IF NOT EXISTS new_table (id SERIAL PRIMARY KEY, name VARCHAR(100));"
            ],
            width=260, height=26, font=ctk.CTkFont(size=11),
            command=self._on_template_selected
        )
        self.cbo_sql_template.pack(side="right", padx=6)

        # SQL 텍스트 에디터 (높이 약 65px, 4~5줄)
        self.txt_sql = ctk.CTkTextbox(
            self.frm_sql, height=65,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#121212", text_color="#e0e0e0"
        )
        self.txt_sql.pack(fill="x", padx=8, pady=(2, 2))
        self.txt_sql.bind("<Control-Return>", lambda e: self._execute_sql())
        self.txt_sql.bind("<F5>", lambda e: self._execute_sql())

        # 하단 상태 표시줄
        self.lbl_sql_status = ctk.CTkLabel(
            self.frm_sql, text="준비됨. SQL 쿼리 또는 DDL 문을 입력 후 [쿼리 실행]을 누르세요.",
            font=ctk.CTkFont(size=11), text_color="#888888", anchor="w"
        )
        self.lbl_sql_status.pack(fill="x", padx=8, pady=(0, 4))

    # =========================================================================
    # 테이블 목록 조회 및 렌더링
    # =========================================================================
    def _async_load_tables(self):
        """백그라운드에서 테이블 목록 로드"""
        self.lbl_table_count.configure(text="테이블 목록 (조회 중...)")
        
        def _fetch():
            return self.db.list_all_tables_with_counts()

        self._run_in_background(_fetch, self._on_tables_loaded, self._on_tables_error)

    def _on_tables_loaded(self, tables: List[Dict[str, Any]]):
        self.all_tables = tables
        self.lbl_table_count.configure(text=f"테이블 목록 ({len(tables)})")
        self._filter_tables()
        
        # 첫 번째 테이블 자동 선택
        if tables and not self.selected_table:
            self._select_table(tables[0]["table_name"])

    def _on_tables_error(self, err_msg: str):
        self.lbl_table_count.configure(text="테이블 목록 (오류)")
        self.lbl_sql_status.configure(text=f"DB 연결/조회 오류: {err_msg}", text_color="#ff5252")

    def _filter_tables(self):
        """검색어에 따른 테이블 목록 필터링 렌더링"""
        query = self.ent_search_tbl.get().strip().lower()
        for w in self.sf_tables.winfo_children():
            w.destroy()

        filtered = [t for t in self.all_tables if query in t["table_name"].lower()]
        for t in filtered:
            name = t["table_name"]
            cnt = t.get("row_count", 0)
            is_active = (name == self.selected_table)
            
            btn = ctk.CTkButton(
                self.sf_tables,
                text=f"{name} ({cnt:,})",
                anchor="w", height=30,
                font=ctk.CTkFont(size=11, weight="bold" if is_active else "normal"),
                fg_color="#1f6aa5" if is_active else "#222222",
                hover_color="#2b7bb9" if is_active else "#333333",
                command=lambda n=name: self._select_table(n)
            )
            btn.pack(fill="x", pady=2)

    def _select_table(self, table_name: str):
        """테이블 선택 시 데이터 및 스키마 로드"""
        self.selected_table = table_name
        self.lbl_current_table.configure(text=f"테이블: [{table_name}]")
        self._filter_tables()
        self._reload_current_table()

    def _reload_current_table(self):
        """현재 선택된 테이블의 데이터/스키마 다시 불러오기"""
        if not self.selected_table:
            return

        table_name = self.selected_table
        limit_val = self.cbo_limit.get()
        limit = None if limit_val == "전체" else int(limit_val)

        def _fetch():
            cols, rows, total_cnt = self.db.get_table_data(table_name, limit=limit)
            schema = self.db.get_table_schema(table_name)
            return (table_name, cols, rows, total_cnt, schema)

        def _success(result):
            t_name, cols, rows, total_cnt, schema = result
            self._on_table_data_loaded(t_name, cols, rows, total_cnt, schema)

        self._run_in_background(_fetch, _success, self._on_data_error)

    def _on_table_data_loaded(self, table_name: str, cols: List[str], rows: List[Dict[str, Any]], total_cnt: int, schema: List[Dict[str, Any]]):
        self.current_data_columns = cols
        self.current_data_rows = rows
        self.current_schema_rows = schema

        limit_val = self.cbo_limit.get()
        shown_cnt = len(rows)
        self.lbl_data_stats.configure(
            text=f"(총 {total_cnt:,}개 행 중 {shown_cnt:,}개 표시 / 컬럼 {len(cols)}개)"
        )

        if self.view_mode == "data":
            self._render_data_grid(cols, rows)
        else:
            self._render_schema_grid(schema)

    def _on_data_error(self, err: str):
        self.lbl_data_stats.configure(text=f"(조회 실패: {err})", text_color="#ff5252")

    # =========================================================================
    # 그리드 렌더링 (데이터 / 스키마)
    # =========================================================================
    def _on_view_mode_changed(self, choice: str):
        if choice == "테이블 구조":
            self.view_mode = "schema"
            if self.current_schema_rows:
                self._render_schema_grid(self.current_schema_rows)
        else:
            self.view_mode = "data"
            if self.current_data_columns:
                self._render_data_grid(self.current_data_columns, self.current_data_rows)

    def _render_data_grid(self, columns: List[str], rows: List[Dict[str, Any]]):
        """데이터 목록을 Treeview에 렌더링"""
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = columns

        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=130, minwidth=70, stretch=True)

        for row in rows:
            values = []
            for col in columns:
                val = row.get(col)
                if val is None:
                    values.append("<NULL>")
                elif isinstance(val, (dict, list)):
                    values.append(json.dumps(val, ensure_ascii=False))
                else:
                    values.append(str(val))
            self.tree.insert("", "end", values=values)

    def _render_schema_grid(self, schema_rows: List[Dict[str, Any]]):
        """테이블 스키마 메타데이터를 Treeview에 렌더링"""
        self.tree.delete(*self.tree.get_children())
        cols = ["No", "컬럼명", "데이터 타입", "Null 허용", "기본값", "Key"]
        self.tree["columns"] = cols

        for col in cols:
            self.tree.heading(col, text=col)
            width = 60 if col in ("No", "Key", "Null 허용") else 150
            self.tree.column(col, width=width, minwidth=50, stretch=True)

        for r in schema_rows:
            dt = r.get("data_type", "")
            maxlen = r.get("character_maximum_length")
            if maxlen:
                dt = f"{dt}({maxlen})"
            
            values = [
                str(r.get("ordinal_position", "")),
                str(r.get("column_name", "")),
                dt,
                "YES" if r.get("is_nullable") == "YES" else "NO",
                str(r.get("column_default") or ""),
                str(r.get("key_type") or "")
            ]
            self.tree.insert("", "end", values=values)

    def _on_tree_double_click(self, event):
        """행 더블 클릭 시 상세 보기 모달 표출"""
        item_id = self.tree.focus()
        if not item_id:
            return
        values = self.tree.item(item_id, "values")
        cols = self.tree["columns"]
        if not cols or not values:
            return

        # 상세 모달 팝업
        pop = ctk.CTkToplevel(self)
        pop.title("데이터 상세 보기")
        pop.geometry("600x450")
        pop.attributes("-topmost", True)

        txt = ctk.CTkTextbox(pop, font=ctk.CTkFont(family="Consolas", size=12))
        txt.pack(fill="both", expand=True, padx=10, pady=10)

        lines = []
        for c, v in zip(cols, values):
            lines.append(f"[{c}]\n{v}\n" + "-"*40)
        txt.insert("1.0", "\n".join(lines))

    # =========================================================================
    # SQL / DDL 실행기
    # =========================================================================
    def _on_template_selected(self, choice: str):
        if not choice or choice.startswith("서식"):
            return
        tbl = self.selected_table or "rpa_projects"
        formatted = choice.replace("{table}", tbl)
        self.txt_sql.delete("1.0", "end")
        self.txt_sql.insert("1.0", formatted)

    def _execute_sql(self):
        """에디터 내의 SQL / DDL 실행"""
        sql = self.txt_sql.get("1.0", "end").strip()
        if not sql:
            messagebox.showwarning("입력 필요", "실행할 SQL 쿼리를 입력하세요.")
            return

        self.lbl_sql_status.configure(text="쿼리 실행 중...", text_color="#ffd54f")

        def _run():
            return (self.db.execute_custom_sql(sql), sql)

        def _success(result):
            res, raw_sql = result
            self._on_sql_finished(res, raw_sql)

        self._run_in_background(_run, _success, lambda err: self._on_sql_finished({"success": False, "error": err, "elapsed_ms": 0}, sql))

    def _on_sql_finished(self, res: Dict[str, Any], raw_sql: str):
        if not res["success"]:
            err_msg = res.get("error", "알 수 없는 오류")
            self.lbl_sql_status.configure(
                text=f"❌ 실행 오류 ({res['elapsed_ms']}ms): {err_msg}",
                text_color="#ff5252"
            )
            return

        qtype = res.get("query_type", "")
        status = res.get("status", "OK")
        elapsed = res.get("elapsed_ms", 0)

        if qtype == "SELECT":
            cols = res.get("columns", [])
            rows = res.get("rows", [])
            cnt = len(rows)
            self.lbl_sql_status.configure(
                text=f"✅ SELECT 실행 완료: {cnt:,}개 행 반환 ({elapsed}ms)",
                text_color="#4caf50"
            )
            self.lbl_current_table.configure(text="테이블: [SQL 사용자 쿼리 결과]")
            self.lbl_data_stats.configure(text=f"({cnt:,}개 행 / {len(cols)}개 컬럼)")
            self.seg_view.set("데이터 목록")
            self.view_mode = "data"
            self._render_data_grid(cols, rows)

        else:
            # DDL / DML 실행 성공
            rc = res.get("rowcount", 0)
            self.lbl_sql_status.configure(
                text=f"✅ {status} 완료 ({rc}건 영향, {elapsed}ms)",
                text_color="#4caf50"
            )
            # DDL 관련 키워드가 있으면 테이블 목록 및 현재 테이블 재로드
            sql_upper = raw_sql.upper()
            if any(k in sql_upper for k in ["CREATE", "ALTER", "DROP", "TRUNCATE", "RENAME"]):
                self._async_load_tables()
            else:
                self._reload_current_table()

    def _copy_data_to_csv(self):
        """현재 렌더링된 데이터를 CSV 형식으로 클립보드에 복사"""
        if not self.current_data_columns or not self.current_data_rows:
            return
        
        lines = []
        # Header
        lines.append("\t".join(self.current_data_columns))
        # Rows
        for r in self.current_data_rows:
            row_vals = []
            for col in self.current_data_columns:
                v = str(r.get(col, ""))
                row_vals.append(v.replace("\t", " ").replace("\n", " "))
            lines.append("\t".join(row_vals))

        tsv_data = "\n".join(lines)
        self.clipboard_clear()
        self.clipboard_append(tsv_data)
        messagebox.showinfo("복사 완료", f"총 {len(self.current_data_rows):,}개 행이 클립보드(TSV)에 복사되었습니다.")
