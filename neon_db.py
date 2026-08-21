"""
UBUS Contract RPA - Neon PostgreSQL Database Manager
Neon DB 연결, 스키마 자동 초기화, RPA 실행 이력 및 계약서 데이터 관리
"""

import os
import time
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
        
        # sslmode=require 보장
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
                # 1. 계약서 처리 이력 테이블
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS rpa_contract_logs (
                        id SERIAL PRIMARY KEY,
                        contract_no VARCHAR(100) NOT NULL,
                        file_name VARCHAR(255),
                        file_path TEXT,
                        status VARCHAR(50) DEFAULT 'READY',  -- READY, OCR_DONE, RPA_DONE, ERROR
                        ocr_data JSONB DEFAULT '{}'::jsonb,
                        error_message TEXT,
                        executed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        duration_ms INTEGER DEFAULT 0
                    );
                    CREATE INDEX IF NOT EXISTS idx_rpa_contract_no ON rpa_contract_logs(contract_no);
                    CREATE INDEX IF NOT EXISTS idx_rpa_status ON rpa_contract_logs(status);
                """)

                # 2. RPA 작업 배치 실행 이력 테이블
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
                conn.commit()
                return True
        finally:
            conn.close()

    def log_contract_result(self, contract_no: str, file_name: str, file_path: str,
                            status: str, ocr_data: dict = None, error_message: str = None,
                            duration_ms: int = 0) -> int:
        """단일 계약서 처리 결과 DB 기록"""
        import json
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
