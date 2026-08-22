"""
UBUS Contract RPA - Neon PostgreSQL Database Manager
Neon DB 연결, 스키마 자동 초기화, RPA 실행 이력 및 모듈형 스크립트(rpa_scripts) 관리
"""

import os
import time
import json
from typing import Dict, Any, List, Optional, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
import base64
import hashlib


def _get_cipher_key(secret_seed: str = "DragonRPA_System_Master_Key_2026") -> bytes:
    """고정 시드로 32바이트 urlsafe base64 키 생성"""
    h = hashlib.sha256(secret_seed.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(h)


def encrypt_secret(plain_text: str) -> str:
    """비밀번호/보안 데이터 암호화 (복호화 가능)"""
    if not plain_text:
        return ""
    if plain_text.startswith("ENC:"):
        return plain_text
    try:
        from cryptography.fernet import Fernet
        f = Fernet(_get_cipher_key())
        token = f.encrypt(plain_text.encode("utf-8")).decode("utf-8")
        return f"ENC:{token}"
    except Exception:
        b = base64.b64encode(plain_text.encode("utf-8")).decode("utf-8")
        return f"ENC:B64_{b}"


def decrypt_secret(cipher_text: str) -> str:
    """암호화된 비밀번호/보안 데이터 복호화"""
    if not cipher_text:
        return ""
    if not cipher_text.startswith("ENC:"):
        return cipher_text
    raw = cipher_text[4:]
    if raw.startswith("B64_"):
        try:
            return base64.b64decode(raw[4:].encode("utf-8")).decode("utf-8")
        except Exception:
            return cipher_text
    try:
        from cryptography.fernet import Fernet
        f = Fernet(_get_cipher_key())
        return f.decrypt(raw.encode("utf-8")).decode("utf-8")
    except Exception:
        return cipher_text


class NeonDBManager:
    """Neon PostgreSQL 연결 및 데이터 처리 매니저"""

    def __init__(self, connection_url: Optional[str] = None):
        self.connection_url = connection_url or os.environ.get("DATABASE_URL", "")
        if not self.connection_url:
            # Fallback to local config files if available
            try:
                cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recorder_config.json")
                if os.path.exists(cfg_path):
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        self.connection_url = json.load(f).get("neon_database_url", "")
            except Exception:
                pass
        if not self.connection_url:
            self.connection_url = "postgresql://neondb_owner:npg_W0LzlYBckKp1@ep-small-firefly-az3rp5ve.c-3.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
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

                # 2. 완성 봇 저장소 (rpa_bots)
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

    # =========================================================================
    # 프로젝트 관리 — 테이블 초기화
    # =========================================================================

    def init_project_tables(self) -> bool:
        """프로젝트 관리용 5개 테이블 자동 생성 (멱등성 보장)"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    -- ① 프로젝트 마스터
                    CREATE TABLE IF NOT EXISTS rpa_projects (
                        id          SERIAL PRIMARY KEY,
                        name        VARCHAR(100) NOT NULL,
                        description TEXT,
                        status      VARCHAR(20) DEFAULT 'active',
                        created_at  TIMESTAMPTZ DEFAULT NOW(),
                        updated_at  TIMESTAMPTZ DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_rpa_projects_status ON rpa_projects(status);

                    -- ② 프로젝트 대상 시스템 (URL / 윈도우 앱)
                    CREATE TABLE IF NOT EXISTS rpa_targets (
                        id          SERIAL PRIMARY KEY,
                        project_id  INTEGER REFERENCES rpa_projects(id) ON DELETE CASCADE,
                        type        VARCHAR(10) NOT NULL DEFAULT 'url',
                        label       VARCHAR(100) NOT NULL,
                        value       TEXT NOT NULL,
                        login_id    VARCHAR(200),
                        login_pw    VARCHAR(500),
                        notes       TEXT,
                        created_at  TIMESTAMPTZ DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_rpa_targets_project ON rpa_targets(project_id);

                    -- ③ Keep된 DOM/UI 요소
                    CREATE TABLE IF NOT EXISTS rpa_keep_elements (
                        id           SERIAL PRIMARY KEY,
                        project_id   INTEGER REFERENCES rpa_projects(id) ON DELETE CASCADE,
                        target_id    INTEGER REFERENCES rpa_targets(id) ON DELETE SET NULL,
                        var_name     VARCHAR(100) NOT NULL,
                        label        VARCHAR(200),
                        selector     TEXT NOT NULL,
                        element_type VARCHAR(30),
                        path         TEXT,
                        created_at   TIMESTAMPTZ DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_rpa_keep_project ON rpa_keep_elements(project_id);

                    -- ④ RPA 태스크 (자연어 지시문 + AI 생성 스크립트)
                    CREATE TABLE IF NOT EXISTS rpa_tasks (
                        id              SERIAL PRIMARY KEY,
                        project_id      INTEGER REFERENCES rpa_projects(id) ON DELETE CASCADE,
                        title           VARCHAR(200) NOT NULL,
                        prompt_text     TEXT NOT NULL,
                        script_code     TEXT,
                        build_type      VARCHAR(10) DEFAULT 'debug',
                        version_tag     VARCHAR(50),
                        ai_engine       VARCHAR(50),
                        ai_model        VARCHAR(100),
                        generated_at    TIMESTAMPTZ,
                        sys_os          VARCHAR(100),
                        sys_hostname    VARCHAR(100),
                        sys_python      VARCHAR(30),
                        sys_user        VARCHAR(100),
                        sys_playwright  VARCHAR(30),
                        status          VARCHAR(20) DEFAULT 'draft',
                        test_notes      TEXT,
                        created_at      TIMESTAMPTZ DEFAULT NOW(),
                        updated_at      TIMESTAMPTZ DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_rpa_tasks_project ON rpa_tasks(project_id);
                    CREATE INDEX IF NOT EXISTS idx_rpa_tasks_status  ON rpa_tasks(status);

                    -- ⑤ 태스크-요소 연결 (M:N)
                    CREATE TABLE IF NOT EXISTS rpa_task_elements (
                        task_id         INTEGER REFERENCES rpa_tasks(id) ON DELETE CASCADE,
                        keep_element_id INTEGER REFERENCES rpa_keep_elements(id) ON DELETE CASCADE,
                        PRIMARY KEY (task_id, keep_element_id)
                    );

                    -- data_column Keep 지원 컬럼 추가 (멱등성 보장)
                    ALTER TABLE rpa_keep_elements
                        ADD COLUMN IF NOT EXISTS keep_type    VARCHAR(20) DEFAULT 'element',
                        ADD COLUMN IF NOT EXISTS column_name  VARCHAR(200),
                        ADD COLUMN IF NOT EXISTS data_type    VARCHAR(30),
                        ADD COLUMN IF NOT EXISTS source_file  TEXT;
                """)
                conn.commit()
                return True
        finally:
            conn.close()

    # =========================================================================
    # 프로젝트 CRUD
    # =========================================================================

    def create_project(self, name: str, description: str = "") -> int:
        """새 프로젝트 생성 → project_id 반환"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO rpa_projects (name, description)
                    VALUES (%s, %s) RETURNING id;
                """, (name, description))
                pid = cur.fetchone()["id"]
                conn.commit()
                return pid
        finally:
            conn.close()

    def list_projects(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """프로젝트 목록 (최근 순)"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                sql = """
                    SELECT id, name, description, status, created_at, updated_at
                    FROM rpa_projects
                    WHERE 1=1
                """
                if active_only:
                    sql += " AND status = 'active'"
                sql += " ORDER BY updated_at DESC;"
                cur.execute(sql)
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_project(self, project_id: int) -> Optional[Dict[str, Any]]:
        """프로젝트 단건 조회"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM rpa_projects WHERE id = %s;", (project_id,)
                )
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            conn.close()

    def touch_project(self, project_id: int):
        """프로젝트 updated_at 갱신"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE rpa_projects SET updated_at = NOW() WHERE id = %s;",
                    (project_id,)
                )
                conn.commit()
        finally:
            conn.close()

    # =========================================================================
    # 대상 시스템 (rpa_targets) CRUD
    # =========================================================================

    def add_target(self, project_id: int, label: str, value: str,
                   type_: str = "url", login_id: str = "",
                   login_pw: str = "", notes: str = "") -> int:
        """대상 시스템 추가 → target_id 반환 (비밀번호 암호화 저장)"""
        enc_pw = encrypt_secret(login_pw) if login_pw else ""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO rpa_targets (project_id, type, label, value, login_id, login_pw, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;
                """, (project_id, type_, label, value, login_id, enc_pw, notes))
                tid = cur.fetchone()["id"]
                conn.commit()
                return tid
        finally:
            conn.close()

    def update_target(self, target_id: int, label: Optional[str] = None,
                      value: Optional[str] = None, login_id: Optional[str] = None,
                      login_pw: Optional[str] = None, notes: Optional[str] = None) -> bool:
        """대상 시스템 정보 수정 (라벨, URL, 계정정보, 비밀번호 암호화)"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                fields = []
                params = []
                if label is not None:
                    fields.append("label = %s")
                    params.append(label)
                if value is not None:
                    fields.append("value = %s")
                    params.append(value)
                if login_id is not None:
                    fields.append("login_id = %s")
                    params.append(login_id)
                if login_pw is not None:
                    fields.append("login_pw = %s")
                    params.append(encrypt_secret(login_pw) if login_pw else "")
                if notes is not None:
                    fields.append("notes = %s")
                    params.append(notes)
                if not fields:
                    return False
                params.append(target_id)
                sql = f"UPDATE rpa_targets SET {', '.join(fields)} WHERE id = %s RETURNING id;"
                cur.execute(sql, tuple(params))
                updated = cur.fetchone() is not None
                conn.commit()
                return updated
        finally:
            conn.close()

    def list_targets(self, project_id: int) -> List[Dict[str, Any]]:
        """프로젝트의 대상 시스템 목록 (비밀번호 복호화 지원)"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, type, label, value, login_id, login_pw, notes, created_at
                    FROM rpa_targets WHERE project_id = %s ORDER BY id;
                """, (project_id,))
                rows = [dict(r) for r in cur.fetchall()]
                for r in rows:
                    if r.get("login_pw"):
                        r["login_pw_plain"] = decrypt_secret(r["login_pw"])
                return rows
        finally:
            conn.close()

    def delete_target(self, target_id: int) -> bool:
        """대상 시스템 삭제"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM rpa_targets WHERE id = %s RETURNING id;", (target_id,))
                deleted = cur.fetchone() is not None
                conn.commit()
                return deleted
        finally:
            conn.close()

    def update_keep_element_var_name(self, element_id: int, var_name: str) -> bool:
        """Keep 요소의 변수명(var_name) 변경 및 DB 영구 저장"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE rpa_keep_elements SET var_name = %s WHERE id = %s RETURNING id;",
                    (var_name, element_id)
                )
                updated = cur.fetchone() is not None
                conn.commit()
                return updated
        finally:
            conn.close()

    # =========================================================================
    # Keep 요소 (rpa_keep_elements) CRUD
    # =========================================================================

    def save_keep_element(self, project_id: int, var_name: str, selector: str,
                          label: str = "", element_type: str = "",
                          path: str = "", target_id: Optional[int] = None,
                          keep_type: str = "element", column_name: str = "",
                          data_type: str = "", source_file: str = "") -> int:
        """Keep 요소 저장 → element_id 반환.
        동일 프로젝트 내 중복 var_name 또는 selector 존재 시 UPDATE (중복 방지)
        keep_type='element'     : DOM/UI 요소 (selector 사용)
        keep_type='data_column' : 데이터 파일 컬럼 (column_name 사용)
        """
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                # 동일 project_id 및 var_name 또는 selector 존재 여부 검사
                cur.execute("""
                    SELECT id FROM rpa_keep_elements
                    WHERE project_id = %s AND (var_name = %s OR (selector != '' AND selector = %s));
                """, (project_id, var_name, selector))
                row = cur.fetchone()
                if row:
                    eid = row["id"]
                    cur.execute("""
                        UPDATE rpa_keep_elements
                        SET target_id = %s, label = %s, selector = %s, element_type = %s, path = %s,
                            keep_type = %s, column_name = %s, data_type = %s, source_file = %s
                        WHERE id = %s;
                    """, (target_id, label, selector, element_type, path,
                          keep_type, column_name, data_type, source_file, eid))
                    conn.commit()
                    return eid
                else:
                    cur.execute("""
                        INSERT INTO rpa_keep_elements
                            (project_id, target_id, var_name, label, selector, element_type, path,
                             keep_type, column_name, data_type, source_file)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
                    """, (project_id, target_id, var_name, label, selector, element_type, path,
                          keep_type, column_name, data_type, source_file))
                    eid = cur.fetchone()["id"]
                    conn.commit()
                    return eid
        finally:
            conn.close()

    def list_keep_elements(self, project_id: int,
                           target_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """프로젝트의 Keep 요소 목록 (target_id 필터 옵션)"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                sql = """
                    SELECT k.id, k.project_id, k.target_id, k.var_name, k.label,
                           k.selector, k.element_type, k.path, k.created_at,
                           k.keep_type, k.column_name, k.data_type, k.source_file,
                           t.label AS target_label
                    FROM rpa_keep_elements k
                    LEFT JOIN rpa_targets t ON t.id = k.target_id
                    WHERE k.project_id = %s
                """
                params: list = [project_id]
                if target_id is not None:
                    sql += " AND k.target_id = %s"
                    params.append(target_id)
                sql += " ORDER BY k.id;"
                cur.execute(sql, tuple(params))
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def delete_keep_element(self, element_id: int) -> bool:
        """Keep 요소 삭제"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM rpa_keep_elements WHERE id = %s RETURNING id;", (element_id,)
                )
                deleted = cur.fetchone() is not None
                conn.commit()
                return deleted
        finally:
            conn.close()

    # =========================================================================
    # RPA 태스크 (rpa_tasks) CRUD
    # =========================================================================

    def save_task(self, project_id: int, title: str, prompt_text: str,
                  script_code: str = "", build_type: str = "debug",
                  version_tag: str = "", ai_engine: str = "", ai_model: str = "",
                  generated_at=None, sys_os: str = "", sys_hostname: str = "",
                  sys_python: str = "", sys_user: str = "", sys_playwright: str = "",
                  status: str = "draft") -> int:
        """RPA 태스크 저장 → task_id 반환"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO rpa_tasks (
                        project_id, title, prompt_text, script_code,
                        build_type, version_tag,
                        ai_engine, ai_model, generated_at,
                        sys_os, sys_hostname, sys_python, sys_user, sys_playwright,
                        status
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id;
                """, (
                    project_id, title, prompt_text, script_code,
                    build_type, version_tag,
                    ai_engine, ai_model, generated_at,
                    sys_os, sys_hostname, sys_python, sys_user, sys_playwright,
                    status
                ))
                tid = cur.fetchone()["id"]
                conn.commit()
                return tid
        finally:
            conn.close()

    def update_task_status(self, task_id: int, status: str,
                           build_type: str = None, version_tag: str = None,
                           test_notes: str = None) -> bool:
        """태스크 상태/버전 업데이트"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                sets = ["status = %s", "updated_at = NOW()"]
                params: list = [status]
                if build_type is not None:
                    sets.append("build_type = %s")
                    params.append(build_type)
                if version_tag is not None:
                    sets.append("version_tag = %s")
                    params.append(version_tag)
                if test_notes is not None:
                    sets.append("test_notes = %s")
                    params.append(test_notes)
                params.append(task_id)
                cur.execute(
                    f"UPDATE rpa_tasks SET {', '.join(sets)} WHERE id = %s;",
                    tuple(params)
                )
                conn.commit()
                return True
        finally:
            conn.close()

    def list_tasks(self, project_id: int,
                   status: Optional[str] = None) -> List[Dict[str, Any]]:
        """프로젝트의 태스크 목록"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                sql = """
                    SELECT id, title, build_type, version_tag, status,
                           ai_engine, ai_model, generated_at, created_at
                    FROM rpa_tasks WHERE project_id = %s
                """
                params: list = [project_id]
                if status:
                    sql += " AND status = %s"
                    params.append(status)
                sql += " ORDER BY id DESC;"
                cur.execute(sql, tuple(params))
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        """태스크 단건 전체 조회"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM rpa_tasks WHERE id = %s;", (task_id,))
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            conn.close()

    def link_task_elements(self, task_id: int, element_ids: List[int]):
        """태스크에 사용된 Keep 요소 연결 기록"""
        if not element_ids:
            return
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                for eid in element_ids:
                    cur.execute("""
                        INSERT INTO rpa_task_elements (task_id, keep_element_id)
                        VALUES (%s, %s) ON CONFLICT DO NOTHING;
                    """, (task_id, eid))
                conn.commit()
        finally:
            conn.close()

    def load_project_context(self, project_id: int) -> Dict[str, Any]:
        """프로젝트 전체 컨텍스트 일괄 로드 (targets + keep_elements + task 요약)"""
        return {
            "project":       self.get_project(project_id),
            "targets":       self.list_targets(project_id),
            "keep_elements": self.list_keep_elements(project_id),
            "tasks":         self.list_tasks(project_id),
        }

    # =========================================================================
    # DB 탐색기 & DDL 패치 실행기 (Introspection & Raw SQL)
    # =========================================================================
    def list_all_tables_with_counts(self) -> List[Dict[str, Any]]:
        """모든 public 테이블 목록 및 행 수 조회"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    ORDER BY table_name;
                """)
                tables = [r["table_name"] for r in cur.fetchall()]
                
                result = []
                for tbl in tables:
                    try:
                        cur.execute(f'SELECT count(*) as cnt FROM "{tbl}";')
                        cnt = cur.fetchone()["cnt"]
                    except Exception:
                        cnt = 0
                    result.append({"table_name": tbl, "row_count": cnt})
                return result
        finally:
            conn.close()

    def get_table_schema(self, table_name: str) -> List[Dict[str, Any]]:
        """테이블 컬럼 메타데이터 및 PK 여부 조회"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        c.column_name,
                        c.data_type,
                        c.character_maximum_length,
                        c.is_nullable,
                        c.column_default,
                        c.ordinal_position,
                        CASE WHEN pk.column_name IS NOT NULL THEN 'PK' ELSE '' END as key_type
                    FROM information_schema.columns c
                    LEFT JOIN (
                        SELECT ku.column_name, ku.table_name
                        FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage ku
                            ON tc.constraint_name = ku.constraint_name
                            AND tc.table_schema = ku.table_schema
                        WHERE tc.constraint_type = 'PRIMARY KEY'
                          AND tc.table_schema = 'public'
                    ) pk ON pk.table_name = c.table_name AND pk.column_name = c.column_name
                    WHERE c.table_schema = 'public' AND c.table_name = %s
                    ORDER BY c.ordinal_position;
                """, (table_name,))
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_table_data(self, table_name: str, limit: Optional[int] = 100) -> Tuple[List[str], List[Dict[str, Any]], int]:
        """테이블 데이터 조회 (컬럼 목록, 행 데이터, 총 행 수)"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                # 총 행 수
                cur.execute(f'SELECT count(*) as cnt FROM "{table_name}";')
                total_cnt = cur.fetchone()["cnt"]

                # 데이터 조회
                if limit is not None and limit > 0:
                    cur.execute(f'SELECT * FROM "{table_name}" LIMIT %s;', (limit,))
                else:
                    cur.execute(f'SELECT * FROM "{table_name}";')
                
                rows = [dict(r) for r in cur.fetchall()]
                columns = [desc[0] for desc in cur.description] if cur.description else []
                return columns, rows, total_cnt
        finally:
            conn.close()

    def execute_custom_sql(self, sql: str) -> Dict[str, Any]:
        """임의의 SQL (SELECT, INSERT, UPDATE, DELETE, DDL: CREATE/ALTER/DROP) 실행"""
        conn = self.connect()
        start_t = time.time()
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                elapsed_ms = int((time.time() - start_t) * 1000)
                status_msg = cur.statusmessage or "OK"
                
                # SELECT 또는 RETURNING 쿼리인 경우 데이터 추출
                if cur.description:
                    columns = [desc[0] for desc in cur.description]
                    rows = [dict(r) for r in cur.fetchall()]
                    conn.commit()
                    return {
                        "success": True,
                        "query_type": "SELECT",
                        "columns": columns,
                        "rows": rows,
                        "rowcount": len(rows),
                        "status": status_msg,
                        "elapsed_ms": elapsed_ms
                    }
                else:
                    rowcount = cur.rowcount
                    conn.commit()
                    return {
                        "success": True,
                        "query_type": "DDL/DML",
                        "columns": [],
                        "rows": [],
                        "rowcount": rowcount,
                        "status": status_msg,
                        "elapsed_ms": elapsed_ms
                    }
        except Exception as e:
            conn.rollback()
            elapsed_ms = int((time.time() - start_t) * 1000)
            return {
                "success": False,
                "query_type": "ERROR",
                "error": str(e),
                "elapsed_ms": elapsed_ms
            }
        finally:
            conn.close()

