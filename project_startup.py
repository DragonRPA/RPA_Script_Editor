"""
Universal RPA Studio — 프로젝트 시작 모달
앱 실행 시 가장 먼저 표시. 프로젝트 선택 / 신규 생성 / 오프라인 시작을 처리한다.
"""

import os
import threading
from typing import Optional, Dict, Any, List

import customtkinter as ctk
from tkinter import messagebox


class ProjectStartupDialog(ctk.CTkToplevel):
    """
    앱 시작 시 표시되는 프로젝트 선택 모달.
    result: 선택된 project 딕셔너리 또는 None(오프라인)
    """

    def __init__(self, parent, db_manager=None):
        super().__init__(parent)
        self.db = db_manager
        self.result: Optional[Dict[str, Any]] = None
        self._projects: List[Dict[str, Any]] = []

        self.title("Universal RPA Studio")
        self.geometry("580x460")
        self.minsize(520, 400)
        self.resizable(True, True)
        self.attributes("-topmost", True)
        self.grab_set()

        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width() - 580) // 2
        py = parent.winfo_y() + (parent.winfo_height() - 460) // 2
        self.geometry(f"580x460+{px}+{py}")

        self._build_ui()
        self._load_projects()

    def _build_ui(self):
        self.configure(fg_color="#1c1c1c")

        hdr = ctk.CTkFrame(self, fg_color="#111111", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(
            hdr, text="Universal RPA Studio",
            font=ctk.CTkFont(size=18, weight="bold"), text_color="#00bcd4"
        ).pack(side="left", padx=20, pady=14)

        self.lbl_db_status = ctk.CTkLabel(
            hdr, text="● DB 연결 중...",
            font=ctk.CTkFont(size=11), text_color="#888888"
        )
        self.lbl_db_status.pack(side="right", padx=16)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=12)

        ctk.CTkLabel(
            body, text="프로젝트 선택",
            font=ctk.CTkFont(size=13, weight="bold"), anchor="w"
        ).pack(fill="x", pady=(0, 6))

        self.frm_list = ctk.CTkScrollableFrame(body, height=220, fg_color="#161616", corner_radius=6)
        self.frm_list.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            self.frm_list, text="프로젝트 목록을 불러오는 중...",
            font=ctk.CTkFont(size=11), text_color="#555555"
        ).pack(pady=20)

        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x")

        ctk.CTkButton(
            btn_row, text="새 프로젝트 생성", width=160, height=38,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#00695c", hover_color="#004d40",
            command=self._on_new_project
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="오프라인 시작", width=130, height=38,
            font=ctk.CTkFont(size=12),
            fg_color="#444444", hover_color="#333333",
            command=self._on_offline
        ).pack(side="left")

        ctk.CTkLabel(
            self, text="v2.5.1  |  Universal RPA Studio & Bot Builder",
            font=ctk.CTkFont(size=10), text_color="#333333"
        ).pack(pady=(0, 8))

    def _load_projects(self):
        def _worker():
            if not self.db:
                self.after(0, lambda: self._on_load_done([], db_ok=False))
                return
            try:
                self.db.init_project_tables()
                projects = self.db.list_projects(active_only=True)
                self.after(0, lambda p=projects: self._on_load_done(p, db_ok=True))
            except Exception as e:
                self.after(0, lambda err=str(e): self._on_load_done([], db_ok=False, err=err))
        threading.Thread(target=_worker, daemon=True).start()

    def _on_load_done(self, projects: list, db_ok: bool, err: str = ""):
        if db_ok:
            self.lbl_db_status.configure(text="● DB 연결됨", text_color="#4caf50")
        else:
            self.lbl_db_status.configure(
                text="● DB 미연결", text_color="#e57373"
            )

        self._projects = projects
        for w in self.frm_list.winfo_children():
            w.destroy()

        if not projects:
            ctk.CTkLabel(
                self.frm_list,
                text="프로젝트가 없습니다. 새 프로젝트를 생성하세요." if db_ok
                     else "DB에 연결할 수 없습니다. 오프라인으로 시작하거나 DATABASE_URL을 확인하세요.",
                font=ctk.CTkFont(size=11), text_color="#555555", wraplength=480
            ).pack(pady=20)
            return

        for proj in projects:
            self._render_project_row(proj)

    def _render_project_row(self, proj: Dict[str, Any]):
        row = ctk.CTkFrame(self.frm_list, fg_color="#222222", corner_radius=5)
        row.pack(fill="x", pady=3, padx=4)

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, padx=10, pady=8)

        ctk.CTkLabel(
            info, text=proj["name"],
            font=ctk.CTkFont(size=13, weight="bold"), anchor="w"
        ).pack(fill="x")

        if proj.get("description"):
            ctk.CTkLabel(
                info, text=proj["description"],
                font=ctk.CTkFont(size=11), text_color="#888888", anchor="w"
            ).pack(fill="x")

        updated = proj.get("updated_at")
        if updated:
            ts = str(updated)[:16].replace("T", " ")
            ctk.CTkLabel(
                info, text=f"최종 작업: {ts}",
                font=ctk.CTkFont(size=10), text_color="#555555", anchor="w"
            ).pack(fill="x")

        ctk.CTkButton(
            row, text="열기", width=70, height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#1f6aa5", hover_color="#144d75",
            command=lambda p=proj: self._on_select_project(p)
        ).pack(side="right", padx=10)

    def _on_select_project(self, proj: Dict[str, Any]):
        self.result = proj
        if self.db:
            try:
                self.db.touch_project(proj["id"])
                ctx = self.db.load_project_context(proj["id"])
                self.result["_context"] = ctx
            except Exception:
                pass
        self.grab_release()
        self.destroy()

    def _on_new_project(self):
        if not self.db:
            messagebox.showwarning("DB 미연결", "오프라인 시작을 이용하십시오.")
            return

        pop = ctk.CTkToplevel(self)
        pop.title("새 프로젝트")
        pop.geometry("400x200")
        pop.attributes("-topmost", True)
        pop.grab_set()

        ctk.CTkLabel(pop, text="프로젝트명", font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(16, 4))
        ent_name = ctk.CTkEntry(pop, width=340, font=ctk.CTkFont(size=12))
        ent_name.pack()
        ctk.CTkLabel(pop, text="설명 (선택)", font=ctk.CTkFont(size=11)).pack(pady=(10, 2))
        ent_desc = ctk.CTkEntry(pop, width=340, font=ctk.CTkFont(size=11))
        ent_desc.pack()

        def _create():
            name = ent_name.get().strip()
            if not name:
                messagebox.showwarning("입력 확인", "프로젝트명을 입력하십시오.")
                return
            try:
                pid = self.db.create_project(name, ent_desc.get().strip())
                proj = self.db.get_project(pid)
                proj["_context"] = self.db.load_project_context(pid)
                self.result = proj
                pop.destroy()
                self.grab_release()
                self.destroy()
            except Exception as e:
                messagebox.showerror("오류", f"프로젝트 생성 실패:\n{e}")

        ctk.CTkButton(pop, text="생성", width=120, height=34, command=_create,
                      fg_color="#00695c", hover_color="#004d40").pack(pady=14)

    def _on_offline(self):
        self.result = None
        self.grab_release()
        self.destroy()


def show_startup_dialog(parent, db_manager=None) -> Optional[Dict[str, Any]]:
    """시작 모달을 표시하고 선택된 프로젝트를 반환. 오프라인 시 None."""
    dlg = ProjectStartupDialog(parent, db_manager=db_manager)
    parent.wait_window(dlg)
    return dlg.result
