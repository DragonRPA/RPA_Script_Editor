# -*- coding: utf-8 -*-
"""
[BACKUP] 단계별 조립 (Step-by-step Builder) 기능 백업
- 작성일: 2026-08-22
- 사유: 선행 작업 완결 자동판단 및 UX 복잡도 이슈로 인해 기본 프롬프트 에디터 중심 UI로 간소화.
        향후 필요 시 재참조를 위해 별도 백업 파일로 보존.
"""

import customtkinter as ctk

class StepBuilderBackupMixin:
    """단계별 조립 탭 UI 구성 및 데이터 추출 백업 로직"""

    def _build_step_builder_tab(self, parent_tab):
        self.step_widgets = []
        self.sf_steps = ctk.CTkScrollableFrame(parent_tab, fg_color="transparent")
        self.sf_steps.pack(fill="both", expand=True, padx=2, pady=2)
        
        btn_add_step = ctk.CTkButton(
            parent_tab, text="+ 단계 추가", height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._add_step_ui
        )
        btn_add_step.pack(fill="x", padx=2, pady=2)

    def _add_step_ui(self):
        idx = len(self.step_widgets) + 1
        step_f = ctk.CTkFrame(self.sf_steps, fg_color="#1a1a1a", corner_radius=6)
        step_f.pack(fill="x", padx=2, pady=4)

        # 헤더
        hdr = ctk.CTkFrame(step_f, fg_color="#222222", corner_radius=0)
        hdr.pack(fill="x")
        lbl_idx = ctk.CTkLabel(hdr, text=f"Step {idx}", font=ctk.CTkFont(weight="bold", size=11), text_color="#64b5f6")
        lbl_idx.pack(side="left", padx=8, pady=4)
        
        def _del(sf=step_f):
            sf.destroy()
            self.step_widgets = [w for w in self.step_widgets if w["frame"] != sf]
            self._renumber_steps()
            
        ctk.CTkButton(hdr, text="✕", width=24, height=24, fg_color="transparent", hover_color="#444", command=_del).pack(side="right", padx=4)

        keep_names = [k["var_name"] for k in getattr(self, "keep_list", []) if k.get("keep_type", "element") == "element"]
        if not keep_names:
            keep_names = ["(Keep 요소 없음)"]

        # 행 1: 액션
        r1 = ctk.CTkFrame(step_f, fg_color="transparent")
        r1.pack(fill="x", padx=6, pady=4)

        f_act = ctk.CTkFrame(r1, fg_color="transparent")
        f_act.pack(side="left", padx=4)
        ctk.CTkLabel(f_act, text="액션", font=ctk.CTkFont(size=11)).pack(anchor="w")
        cb_act = ctk.CTkComboBox(f_act, values=["클릭", "입력", "수집", "키입력", "대기"], width=90, font=ctk.CTkFont(size=11))
        cb_act.set("클릭")
        cb_act.pack(anchor="w")

        f_tgt = ctk.CTkFrame(r1, fg_color="transparent")
        f_tgt.pack(side="left", padx=4)
        ctk.CTkLabel(f_tgt, text="대상 요소", font=ctk.CTkFont(size=11)).pack(anchor="w")
        cb_tgt = ctk.CTkComboBox(f_tgt, values=keep_names, width=140, font=ctk.CTkFont(size=11))
        cb_tgt.pack(anchor="w")

        f_val = ctk.CTkFrame(r1, fg_color="transparent")
        f_val.pack(side="left", padx=4, fill="x", expand=True)
        ctk.CTkLabel(f_val, text="입력 값 (필요시)", font=ctk.CTkFont(size=11)).pack(anchor="w")
        ent_val = ctk.CTkEntry(f_val, font=ctk.CTkFont(size=11))
        ent_val.pack(fill="x")

        # 행 2: 완료조건
        r2 = ctk.CTkFrame(step_f, fg_color="transparent")
        r2.pack(fill="x", padx=6, pady=(0, 6))

        f_ctype = ctk.CTkFrame(r2, fg_color="transparent")
        f_ctype.pack(side="left", padx=4)
        ctk.CTkLabel(f_ctype, text="완료조건", font=ctk.CTkFont(size=11)).pack(anchor="w")
        cb_ctype = ctk.CTkComboBox(f_ctype, values=["없음", "요소 출현", "요소 사라짐", "텍스트 일치", "고정 지연"], width=100, font=ctk.CTkFont(size=11))
        cb_ctype.set("없음")
        cb_ctype.pack(anchor="w")

        f_ctgt = ctk.CTkFrame(r2, fg_color="transparent")
        f_ctgt.pack(side="left", padx=4)
        ctk.CTkLabel(f_ctgt, text="조건 대상", font=ctk.CTkFont(size=11)).pack(anchor="w")
        cb_ctgt = ctk.CTkComboBox(f_ctgt, values=keep_names, width=140, font=ctk.CTkFont(size=11))
        cb_ctgt.pack(anchor="w")

        f_cval = ctk.CTkFrame(r2, fg_color="transparent")
        f_cval.pack(side="left", padx=4, fill="x", expand=True)
        ctk.CTkLabel(f_cval, text="기대값 / 지연(ms)", font=ctk.CTkFont(size=11)).pack(anchor="w")
        ent_cval = ctk.CTkEntry(f_cval, font=ctk.CTkFont(size=11))
        ent_cval.pack(fill="x")

        f_to = ctk.CTkFrame(r2, fg_color="transparent")
        f_to.pack(side="left", padx=4)
        ctk.CTkLabel(f_to, text="타임아웃(s)", font=ctk.CTkFont(size=11)).pack(anchor="w")
        ent_to = ctk.CTkEntry(f_to, width=60, font=ctk.CTkFont(size=11))
        ent_to.insert(0, "10")
        ent_to.pack(anchor="w")

        self.step_widgets.append({
            "frame": step_f,
            "hdr_label": lbl_idx,
            "cb_act": cb_act,
            "cb_tgt": cb_tgt,
            "ent_val": ent_val,
            "cb_ctype": cb_ctype,
            "cb_ctgt": cb_ctgt,
            "ent_cval": ent_cval,
            "ent_to": ent_to
        })

    def _renumber_steps(self):
        for i, w in enumerate(self.step_widgets):
            w["hdr_label"].configure(text=f"Step {i+1}")

    def _extract_step_builder_prompt(self, lines: list):
        lines.append("[실행 단계 및 완료조건]")
        for i, w in enumerate(getattr(self, "step_widgets", [])):
            act = w["cb_act"].get()
            tgt = w["cb_tgt"].get()
            val = w["ent_val"].get().strip()
            ctype = w["cb_ctype"].get()
            ctgt = w["cb_ctgt"].get()
            cval = w["ent_cval"].get().strip()
            to = w["ent_to"].get().strip() or "10"
            
            lines.append(f"Step {i+1}:")
            lines.append(f"  - 액션: {act}")
            lines.append(f"  - 대상: {{{tgt}}}")
            if val:
                lines.append(f"  - 입력값: {val}")
                
            if ctype != "없음":
                c_str = ""
                if ctype == "고정 지연":
                    c_str = f"{cval}ms 강제 대기 (고정 지연)"
                else:
                    c_str = f"{{{ctgt}}} 요소가"
                    if ctype == "요소 출현":
                        c_str += " 화면에 나타날 때까지 대기 (visible)"
                    elif ctype == "요소 사라짐":
                        c_str += " 화면에서 사라질 때까지 대기 (hidden)"
                    elif ctype == "텍스트 일치":
                        c_str += f" 텍스트 '{cval}'와(과) 일치할 때까지 대기"
                lines.append(f"  - 완료조건: {c_str} (timeout: {to}s)")
            lines.append("")
