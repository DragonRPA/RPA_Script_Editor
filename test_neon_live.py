import sys
import time
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config_manager import ConfigManager
from neon_db import NeonDBManager

def test_neon():
    cfg = ConfigManager()
    db_url = cfg.get("neon_database_url")
    print(f"[*] Neon DB URL: {db_url[:35]}...")

    mgr = NeonDBManager(db_url)

    # 1. Connection Test
    t0 = time.time()
    res = mgr.test_connection()
    t1 = time.time()
    print(f"[1] Connection Test: SUCCESS ({int((t1-t0)*1000)}ms)")
    print(f"    - Database: {res['database']}")
    print(f"    - User: {res['user']}")
    print(f"    - Server Time: {res['server_time']}")
    print(f"    - PostgreSQL Version: {res['version'][:45]}...")

    # 2. Init Tables
    t0 = time.time()
    mgr.init_tables()
    t1 = time.time()
    print(f"[2] Init Tables (rpa_contract_logs, rpa_batch_runs): SUCCESS ({int((t1-t0)*1000)}ms)")

    # 3. Log Contract Result
    t0 = time.time()
    log_id = mgr.log_contract_result(
        contract_no="2D2607007",
        file_name="2D2607007.pdf",
        file_path="C:/UBUS_PDF/3_RPA완료/2D2607007.pdf",
        status="RPA_DONE",
        ocr_data={"계약번호": "2D2607007", "고객명": "유네스코", "금액": 5000000},
        duration_ms=1250
    )
    t1 = time.time()
    print(f"[3] Insert Contract Log: SUCCESS (ID: {log_id}, {int((t1-t0)*1000)}ms)")

    # 4. Fetch Logs
    logs = mgr.fetch_recent_logs(limit=5)
    print(f"[4] Fetch Recent Logs: SUCCESS ({len(logs)} records)")
    for row in logs:
        print(f"    -> [ID:{row['id']}] 계약번호: {row['contract_no']} | 상태: {row['status']} | 처리시간: {row['executed_at']}")

    print("\n[SUCCESS] Neon PostgreSQL 100% Live Operation Verified!")

if __name__ == "__main__":
    test_neon()
