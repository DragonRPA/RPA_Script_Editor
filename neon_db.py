"""
UBUS Contract RPA - Neon PostgreSQL Database Manager
Neon DB 연결, 스키마 자동 초기화, RPA 실행 이력 및 모듈형 스크립트(rpa_scripts) 관리
"""

import os
import time
import json
from typing import Dict, Any, List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor


class NeonDBManager:
    """Neon PostgreSQL 연결 및 데이터 처리 매니저"""

    def __init__(self, connection_url: Optional[str] = None):
        self.connection_url = connection_url or os.environ.get("DATABASE_URL", "")
        self._conn = None

    def connect(self):
        """데이터베이스 연결 수립"""
        if not self.connection_url:
            raise ValueError("Neon DATABASE_URL이 설정되지 않았습니다.")
        
        url = self.connection_url
        if "sslmode=" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}sslmode=require"
            
        self._conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
        return self._conn

    def test_connection(self) -> Dict[str, Any]:
        """연결 상태 및 DB 버전 테스트"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT version(), current_database(), current_user, now();")
                row = cur.fetchone()
                return {
                    "success": True,
                    "version": row["version"],
                    "database": row["current_database"],
                    "user": row["current_user"],
                    "server_time": str(row["now"])
                }
        finally:
            conn.close()

    def init_tables(self) -> bool:
        """RPA에 필요한 기본 테이블 자동 생성"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                # 1. 모듈형 스크립트 저장소 (rpa_scripts)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS rpa_scripts (
                        id          SERIAL PRIMARY KEY,
                        name        VARCHAR(100) UNIQUE NOT NULL,
                        title       VARCHAR(100) NOT NULL,
                        category    VARCHAR(50)  NOT NULL,
                        description TEXT,
                        code        TEXT NOT NULL,
                        target_type VARCHAR(20) DEFAULT 'PYTHON',
                        is_active   BOOLEAN     DEFAULT TRUE,
                        created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_rpa_scripts_category ON rpa_scripts(category);
                    CREATE INDEX IF NOT EXISTS idx_rpa_scripts_name ON rpa_scripts(name);
                """)

                # 2. 계약서 처리 이력 테이블
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS rpa_contract_logs (
                        id SERIAL PRIMARY KEY,
                        contract_no VARCHAR(100) NOT NULL,
                        file_name VARCHAR(255),
                        file_path TEXT,
                        status VARCHAR(50) DEFAULT 'READY',
                        ocr_data JSONB DEFAULT '{}'::jsonb,
                        error_message TEXT,
                        executed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        duration_ms INTEGER DEFAULT 0
                    );
                    CREATE INDEX IF NOT EXISTS idx_rpa_contract_no ON rpa_contract_logs(contract_no);
                    CREATE INDEX IF NOT EXISTS idx_rpa_status ON rpa_contract_logs(status);
                """)

                # 3. RPA 작업 배치 실행 이력 테이블
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS rpa_batch_runs (
                        id SERIAL PRIMARY KEY,
                        batch_id VARCHAR(100) UNIQUE NOT NULL,
                        total_files INTEGER DEFAULT 0,
                        success_count INTEGER DEFAULT 0,
                        fail_count INTEGER DEFAULT 0,
                        started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        finished_at TIMESTAMP WITH TIME ZONE,
                        status VARCHAR(50) DEFAULT 'RUNNING'
                    );
                """)

                # 4. 완성 봇 저장소 (rpa_bots)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS rpa_bots (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(100) UNIQUE NOT NULL,
                        title VARCHAR(100) NOT NULL,
                        description TEXT,
                        modules JSONB DEFAULT '[]'::jsonb,
                        combined_code TEXT NOT NULL,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_rpa_bots_name ON rpa_bots(name);
                """)
                conn.commit()
                return True
        finally:
            conn.close()

    # =========================================================================
    # 모듈형 스크립트 (rpa_scripts) CRUD
    # =========================================================================

    def save_script(self, name: str, title: str, category: str, code: str,
                    description: str = "", target_type: str = "PYTHON",
                    is_active: bool = True) -> int:
        """모듈형 스크립트 저장 또는 업데이트 (UPSERT)"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO rpa_scripts (
                        name, title, category, description, code, target_type, is_active, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (name) DO UPDATE SET
                        title       = EXCLUDED.title,
                        category    = EXCLUDED.category,
                        description = EXCLUDED.description,
                        code        = EXCLUDED.code,
                        target_type = EXCLUDED.target_type,
                        is_active   = EXCLUDED.is_active,
                        updated_at  = NOW()
                    RETURNING id;
                """, (name, title, category, description, code, target_type, is_active))
                script_id = cur.fetchone()["id"]
                conn.commit()
                return script_id
        finally:
            conn.close()

    def get_script(self, name: str) -> Optional[Dict[str, Any]]:
        """특정 모듈 스크립트 단건 조회"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, name, title, category, description, code, target_type, is_active, updated_at
                    FROM rpa_scripts
                    WHERE name = %s;
                """, (name,))
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            conn.close()

    def list_scripts(self, category: Optional[str] = None, active_only: bool = True) -> List[Dict[str, Any]]:
        """모듈 스크립트 목록 조회 (카테고리 필터 지원)"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                query = "SELECT id, name, title, category, description, target_type, is_active, updated_at FROM rpa_scripts WHERE 1=1"
                params = []
                if active_only:
                    query += " AND is_active = TRUE"
                if category:
                    query += " AND category = %s"
                    params.append(category)
                query += " ORDER BY category, id;"
                cur.execute(query, tuple(params))
                return list(cur.fetchall())
        finally:
            conn.close()

    def delete_script(self, name: str) -> bool:
        """모듈 스크립트 삭제"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM rpa_scripts WHERE name = %s RETURNING id;", (name,))
                deleted = cur.fetchone() is not None
                conn.commit()
                return deleted
        finally:
            conn.close()

    def seed_default_modules(self) -> int:
        """기본 핵심 모듈 4종 시드 데이터 등록"""
        default_modules = [
            {
                "name": "ubus_login",
                "title": "UBUS ERP 로그인",
                "category": "로그인",
                "description": "UBUS ERP 페이지 접속 및 ID/PW 로그인",
                "code": """# [모듈: UBUS ERP 로그인]
def ubus_login(page, user_id, user_pw, erp_url="http://175.119.156.105:3000/"):
    page.goto(erp_url)
    page.get_by_role("textbox", name="ID").fill(user_id)
    page.get_by_role("textbox", name="비밀번호").fill(user_pw)
    page.get_by_role("button", name="로그인").click()
    page.wait_for_timeout(1000)
    print(f"로그인 완료: {user_id}")
    return True
"""
            },
            {
                "name": "contract_search_and_upload",
                "title": "계약번호 조회 및 PDF 첨부",
                "category": "웹조작",
                "description": "계약번호로 검색 후 상세 그리드 더블클릭, PDF 파일 첨부 및 저장",
                "code": """# [모듈: 계약번호 조회 및 PDF 첨부]
def contract_upload(page, contract_no, file_path):
    page.locator("input[name*='contract']").first.fill(contract_no)
    page.get_by_role("button", name="조회").click()
    page.wait_for_timeout(500)
    page.locator("table tbody tr").first.dblclick()
    page.locator("input[type='file']").first.set_input_files(file_path)
    page.get_by_role("button", name="저장").click()
    page.wait_for_timeout(1000)
    print(f"계약서 첨부 완료: {contract_no}")
    return True
"""
            },
            {
                "name": "find_and_focus_window",
                "title": "윈도우 창 찾기 및 포커스",
                "category": "윈도우앱",
                "description": "창 제목 키워드로 실행 중인 윈도우 앱 창을 찾아 활성화",
                "code": """# [모듈: 윈도우 창 찾기 및 포커스]
import win32gui, win32con

def find_and_focus_window(title_keyword: str) -> bool:
    results = []
    def _cb(hwnd, _):
        if title_keyword in win32gui.GetWindowText(hwnd) and win32gui.IsWindowVisible(hwnd):
            results.append(hwnd)
    win32gui.EnumWindows(_cb, None)
    if results:
        win32gui.ShowWindow(results[0], win32con.SW_MAXIMIZE)
        win32gui.SetForegroundWindow(results[0])
        print(f"창 포커스 이동 완료: {title_keyword}")
        return True
    print(f"창을 찾지 못했습니다: {title_keyword}")
    return False
"""
            },
            {
                "name": "robust_click_fallback",
                "title": "4단계 Fallback 강등 클릭",
                "category": "윈도우앱",
                "description": "CSS -> UIA -> 이미지매칭 -> KVM 좌표 순서로 자동 강등 클릭",
                "code": """# [모듈: 4단계 Fallback 강등 클릭]
import pyautogui
from pywinauto import Application

def robust_click(page, css_selector: str, uia_auto_id: str,
                 img_path: str, coord_x: int, coord_y: int):
    # 1순위: CSS 셀렉터
    try:
        page.locator(css_selector).first.click(timeout=2000)
        return "CSS_SUCCESS"
    except Exception:
        pass

    # 2순위: UIA
    try:
        app = Application(backend="uia").connect(title_re=".*ERP.*")
        app.top_window().child_window(auto_id=uia_auto_id).click()
        return "UIA_SUCCESS"
    except Exception:
        pass

    # 3순위: 이미지 매칭
    try:
        pos = pyautogui.locateOnScreen(img_path, confidence=0.85)
        if pos:
            pyautogui.click(pos)
            return "PIXEL_SUCCESS"
    except Exception:
        pass

    # 4순위: 좌표 클릭
    pyautogui.click(coord_x, coord_y)
    return "KVM_SUCCESS"
"""
            }
        ]

        count = 0
        for mod in default_modules:
            self.save_script(
                name=mod["name"],
                title=mod["title"],
                category=mod["category"],
                code=mod["code"],
                description=mod["description"]
            )
            count += 1
        return count

    # =========================================================================
    # 실행 이력 (rpa_contract_logs)
    # =========================================================================

    def log_contract_result(self, contract_no: str, file_name: str, file_path: str,
                            status: str, ocr_data: dict = None, error_message: str = None,
                            duration_ms: int = 0) -> int:
        """단일 계약서 처리 결과 DB 기록"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO rpa_contract_logs (
                        contract_no, file_name, file_path, status,
                        ocr_data, error_message, duration_ms
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (
                    contract_no,
                    file_name,
                    file_path,
                    status,
                    json.dumps(ocr_data or {}, ensure_ascii=False),
                    error_message,
                    duration_ms
                ))
                inserted_id = cur.fetchone()["id"]
                conn.commit()
                return inserted_id
        finally:
            conn.close()

    # =========================================================================
    # 완성 봇 (rpa_bots) CRUD
    # =========================================================================

    def save_bot(self, name: str, title: str, modules: List[Dict[str, Any]],
                 combined_code: str, description: str = "", is_active: bool = True) -> int:
        """완성 봇을 Neon DB에 저장 또는 업데이트 (UPSERT)"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO rpa_bots (
                        name, title, description, modules, combined_code, is_active, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (name) DO UPDATE SET
                        title         = EXCLUDED.title,
                        description   = EXCLUDED.description,
                        modules       = EXCLUDED.modules,
                        combined_code = EXCLUDED.combined_code,
                        is_active     = EXCLUDED.is_active,
                        updated_at    = NOW()
                    RETURNING id;
                """, (
                    name,
                    title,
                    description,
                    json.dumps(modules, ensure_ascii=False),
                    combined_code,
                    is_active
                ))
                bot_id = cur.fetchone()["id"]
                conn.commit()
                return bot_id
        finally:
            conn.close()

    def get_bot(self, name: str) -> Optional[Dict[str, Any]]:
        """특정 봇 단건 조회 (모듈 목록 파싱 포함)"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, name, title, description, modules, combined_code, is_active, updated_at
                    FROM rpa_bots
                    WHERE name = %s;
                """, (name,))
                row = cur.fetchone()
                if row:
                    d = dict(row)
                    if isinstance(d.get("modules"), str):
                        d["modules"] = json.loads(d["modules"])
                    return d
                return None
        finally:
            conn.close()

    def list_bots(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """저장된 봇 목록 조회"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                query = "SELECT id, name, title, description, is_active, updated_at, jsonb_array_length(modules) as module_count FROM rpa_bots WHERE 1=1"
                if active_only:
                    query += " AND is_active = TRUE"
                query += " ORDER BY id DESC;"
                cur.execute(query)
                return list(cur.fetchall())
        finally:
            conn.close()

    def delete_bot(self, name: str) -> bool:
        """봇 삭제"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM rpa_bots WHERE name = %s RETURNING id;", (name,))
                deleted = cur.fetchone() is not None
                conn.commit()
                return deleted
        finally:
            conn.close()


    def fetch_recent_logs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """최근 처리 이력 조회"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, contract_no, file_name, status,
                           error_message, executed_at, duration_ms
                    FROM rpa_contract_logs
                    ORDER BY executed_at DESC
                    LIMIT %s;
                """, (limit,))
                return list(cur.fetchall())
        finally:
            conn.close()
