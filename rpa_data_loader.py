# -*- coding: utf-8 -*-
"""
rpa_data_loader.py
──────────────────
RPA 데이터 소스 표준 로더.
Excel / CSV / JSON 파일을 읽어 모든 셀을 str로 정규화하고,
행 단위 반복 처리, 결과 추적, 재시작 지원을 제공한다.
"""

from __future__ import annotations
import json, os, re, math
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional, Tuple


def _normalize_cell(val: Any) -> str:
    if val is None:
        return ""
    try:
        import pandas as pd
        if pd.isna(val):
            return ""
    except Exception:
        pass
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return ""
        if val == int(val):
            return str(int(val))
        return str(val)
    if isinstance(val, bool):
        return str(val)
    return str(val).strip()


def _detect_encoding(file_path: str) -> str:
    try:
        import chardet
        with open(file_path, "rb") as f:
            raw = f.read(min(32768, os.path.getsize(file_path)))
        result = chardet.detect(raw)
        return result.get("encoding") or "utf-8-sig"
    except ImportError:
        pass
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            with open(file_path, encoding=enc) as f:
                f.read(1024)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    return "utf-8"


def _infer_type(sample_val: Any) -> str:
    if hasattr(sample_val, "strftime"):
        return "date"
    if isinstance(sample_val, bool):
        return "bool"
    if isinstance(sample_val, int):
        return "int"
    if isinstance(sample_val, float):
        try:
            if not math.isnan(sample_val):
                return "int" if sample_val == int(sample_val) else "float"
        except Exception:
            pass
    s = str(sample_val).strip()
    if re.match(r"^\d{4}[-./]\d{1,2}[-./]\d{1,2}$", s):
        return "date"
    try:
        int(s.replace(",", ""))
        return "int"
    except ValueError:
        pass
    try:
        float(s.replace(",", ""))
        return "float"
    except ValueError:
        pass
    return "str"


def _safe_varname(column_name: str) -> str:
    name = re.sub(r"[^\w가-힣]", "_", column_name.strip())
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "col"


class DataLoader:
    """RPA 데이터 소스 표준 로더."""

    _STATUS_COL  = "_status"
    _RESULT_COL  = "_result"
    _ERROR_COL   = "_error"
    _PROC_AT_COL = "_processed_at"
    _RESERVED    = {_STATUS_COL, _RESULT_COL, _ERROR_COL, _PROC_AT_COL}

    def __init__(self, file_path: str, result_path: Optional[str] = None):
        self.file_path   = file_path
        self.result_path = result_path or self._default_result_path(file_path)
        self.headers: List[str] = []
        self.rows:    List[Dict[str, str]] = []
        self._header_info_cache: Optional[List[Dict]] = None

    # ── 파일 읽기 ──────────────────────────────────────────────────────────

    def load(self) -> "DataLoader":
        ext = os.path.splitext(self.file_path)[1].lower()
        if ext in (".xlsx", ".xls"):
            self._load_excel()
        elif ext == ".csv":
            self._load_csv()
        elif ext == ".json":
            self._load_json()
        else:
            raise ValueError(f"지원하지 않는 파일 형식: {ext}")
        if os.path.exists(self.result_path):
            self._restore_status()
        print(f"[DataLoader] 로드 완료: {len(self.rows)}행 / {len(self.headers)}컬럼")
        return self

    def _load_excel(self):
        import pandas as pd
        df = pd.read_excel(self.file_path, dtype=str)
        self.headers = list(df.columns)
        self.rows = [{col: _normalize_cell(row[col]) for col in self.headers} for _, row in df.iterrows()]
        self._add_tracking_columns()

    def _load_csv(self):
        import pandas as pd
        enc = _detect_encoding(self.file_path)
        try:
            df = pd.read_csv(self.file_path, encoding=enc, dtype=str)
        except UnicodeDecodeError:
            df = pd.read_csv(self.file_path, encoding="cp949", dtype=str)
        self.headers = list(df.columns)
        self.rows = [{col: _normalize_cell(row[col]) for col in self.headers} for _, row in df.iterrows()]
        self._add_tracking_columns()

    def _load_json(self):
        enc = _detect_encoding(self.file_path)
        with open(self.file_path, encoding=enc) as f:
            data = json.load(f)
        if isinstance(data, dict):
            import pandas as pd
            df = pd.DataFrame(data)
            self.headers = list(df.columns)
            self.rows = [{col: _normalize_cell(row[col]) for col in self.headers} for _, row in df.iterrows()]
        elif isinstance(data, list) and data:
            self.headers = list(data[0].keys())
            self.rows = [{k: _normalize_cell(v) for k, v in item.items()} for item in data]
        else:
            raise ValueError("JSON 구조를 파싱할 수 없습니다.")
        self._add_tracking_columns()

    def _add_tracking_columns(self):
        for row in self.rows:
            for col in (self._STATUS_COL, self._RESULT_COL, self._ERROR_COL, self._PROC_AT_COL):
                row.setdefault(col, "")

    def _restore_status(self):
        try:
            import pandas as pd
            ext = os.path.splitext(self.result_path)[1].lower()
            df = pd.read_excel(self.result_path, dtype=str).fillna("") if ext in (".xlsx", ".xls") else pd.read_csv(self.result_path, dtype=str).fillna("")
            for i, rrow in df.iterrows():
                if i < len(self.rows):
                    for col in self._RESERVED:
                        if col in rrow:
                            self.rows[i][col] = str(rrow[col])
            done = sum(1 for r in self.rows if r.get(self._STATUS_COL) == "done")
            print(f"[DataLoader] 이전 진행 복원: {done}행 완료 상태 유지")
        except Exception as e:
            print(f"[DataLoader] 이전 결과 복원 실패 (무시): {e}")

    # ── 헤더 정보 ──────────────────────────────────────────────────────────

    def headers_info(self) -> List[Dict]:
        """UI 표시용 헤더 정보: [{name, var_name, sample, inferred_type}]"""
        if self._header_info_cache is not None:
            return self._header_info_cache
        import pandas as pd
        ext = os.path.splitext(self.file_path)[1].lower()
        try:
            if ext in (".xlsx", ".xls"):
                df_raw = pd.read_excel(self.file_path, nrows=5)
            elif ext == ".csv":
                df_raw = pd.read_csv(self.file_path, encoding=_detect_encoding(self.file_path), nrows=5)
            else:
                df_raw = None
        except Exception:
            df_raw = None

        result = []
        for col in self.headers:
            if col in self._RESERVED:
                continue
            sample_raw = None
            if df_raw is not None and col in df_raw.columns:
                for v in df_raw[col]:
                    try:
                        if not pd.isna(v):
                            sample_raw = v
                            break
                    except Exception:
                        if v is not None:
                            sample_raw = v
                            break
            inferred   = _infer_type(sample_raw) if sample_raw is not None else "str"
            sample_str = _normalize_cell(sample_raw) if sample_raw is not None else ""
            result.append({"name": col, "var_name": _safe_varname(col), "sample": sample_str, "inferred_type": inferred})

        self._header_info_cache = result
        return result

    # ── 반복 처리 ──────────────────────────────────────────────────────────

    def iterate(self) -> Iterator[Tuple[int, Dict[str, str]]]:
        """행 단위 순회. _status='done' 행은 건너뜀."""
        for i, row in enumerate(self.rows):
            if row.get(self._STATUS_COL) == "done":
                continue
            yield i, row

    def mark_done(self, idx: int, result: str = ""):
        self.rows[idx][self._STATUS_COL]  = "done"
        self.rows[idx][self._RESULT_COL]  = result
        self.rows[idx][self._ERROR_COL]   = ""
        self.rows[idx][self._PROC_AT_COL] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def mark_error(self, idx: int, error: str):
        self.rows[idx][self._STATUS_COL]  = "error"
        self.rows[idx][self._ERROR_COL]   = error[:500]
        self.rows[idx][self._PROC_AT_COL] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def mark_skip(self, idx: int, reason: str = ""):
        self.rows[idx][self._STATUS_COL] = "skip"
        self.rows[idx][self._RESULT_COL] = reason

    def progress(self, current_idx: int):
        total = len(self.rows)
        done  = sum(1 for r in self.rows if r.get(self._STATUS_COL) == "done")
        pct   = done / total * 100 if total else 0
        print(f"[{done}/{total}] 행 {current_idx + 1} 처리 중... ({pct:.1f}%)")

    # ── 결과 저장 ──────────────────────────────────────────────────────────

    def save_result(self):
        import pandas as pd
        df        = pd.DataFrame(self.rows)
        data_cols = [c for c in df.columns if c not in self._RESERVED]
        track_cols = [c for c in (self._STATUS_COL, self._RESULT_COL, self._ERROR_COL, self._PROC_AT_COL) if c in df.columns]
        df = df[data_cols + track_cols]
        ext = os.path.splitext(self.result_path)[1].lower()
        if ext in (".xlsx", ".xls"):
            df.to_excel(self.result_path, index=False)
        else:
            df.to_csv(self.result_path, index=False, encoding="utf-8-sig")
        s = self.summary()
        print(f"[DataLoader] 결과 저장: {self.result_path}")
        print(f"             완료={s['done']} | 오류={s['error']} | 건너뜀={s['skip']} | 미처리={s['remaining']}")

    def summary(self) -> Dict[str, int]:
        total = len(self.rows)
        done  = sum(1 for r in self.rows if r.get(self._STATUS_COL) == "done")
        error = sum(1 for r in self.rows if r.get(self._STATUS_COL) == "error")
        skip  = sum(1 for r in self.rows if r.get(self._STATUS_COL) == "skip")
        return {"total": total, "done": done, "error": error, "skip": skip, "remaining": total - done - error - skip}

    @staticmethod
    def _default_result_path(file_path: str) -> str:
        base, ext = os.path.splitext(file_path)
        return f"{base}_결과{ext}"
