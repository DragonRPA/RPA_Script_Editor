"""
Universal RPA - Snippet Library (Full Edition)
웹 브라우저(Playwright) + 윈도우 앱(pywinauto/pyautogui) + 제어문 + 변수
ImageScan 프로젝트 4대 Fallback 아키텍처 완전 이식 버전
"""

from typing import Dict, List

SNIPPET_CATEGORIES: Dict[str, List[Dict[str, str]]] = {

    # =========================================================================
    # 📁 템플릿
    # =========================================================================
    "📁 템플릿 (Templates)": [
        {
            "name": "전체 PDF 반복 루프 뼈대",
            "desc": "Ollama 추출 변수와 함께 전체 PDF를 순회하는 표준 루프",
            "code": """# [PDF 전체 순회 루프]
for idx, item in enumerate(pdf_items, start=1):
    contract_no = item.get("계약번호", "")
    file_path   = item.get("file_path", "")
    print(f"[{idx}/{len(pdf_items)}] 처리 시작: {contract_no}")

    page.locator("input[name*='contract']").first.fill(contract_no)
    page.get_by_role("button", name="조회").click()
    page.wait_for_timeout(500)
    page.locator("table tbody tr").first.dblclick()
    page.locator("input[type='file']").first.set_input_files(file_path)
    page.get_by_role("button", name="저장").click()
    page.wait_for_timeout(1000)
    print(f"[{idx}/{len(pdf_items)}] 완료: {contract_no}")
"""
        },
        {
            "name": "단일 건 처리 함수 뼈대",
            "desc": "재사용 가능한 단일 계약서 처리 서브 함수",
            "code": """def process_single_contract(page, item, env):
    \"\"\"단일 계약서 처리 로직\"\"\"
    contract_no = item["계약번호"]
    file_path   = item["file_path"]

    page.locator("input[name*='contract']").fill(contract_no)
    page.get_by_role("button", name="조회").click()
    page.locator("table tbody tr").first.dblclick()
    page.locator("input[type='file']").set_input_files(file_path)
    page.get_by_role("button", name="저장").click()
    return True
"""
        },
        {
            "name": "중첩 루프 (LOOP_ROWS 구조)",
            "desc": "부모 루프 안에 서브 루프를 중첩하는 계층형 반복",
            "code": """# [LOOP_ROWS 계층형 중첩 루프]
for row_idx, row in enumerate(excel_rows, start=1):
    print(f"  [행 {row_idx}] 처리 시작: {row}")

    # 하위 서브스텝들 (부모 루프 1건에 대한 세부 동작)
    for field_key, field_value in row.items():
        if not field_value:
            continue
        target_input = page.locator(f"input[data-field='{field_key}']")
        if target_input.count() > 0:
            target_input.fill(str(field_value))

    page.get_by_role("button", name="저장").click()
    page.wait_for_timeout(500)
    print(f"  [행 {row_idx}] 저장 완료")
"""
        },
    ],

    # =========================================================================
    # 🖱️ 웹 조작 (Playwright - 브라우저)
    # =========================================================================
    "🖱️ 웹 조작 (Browser Actions)": [
        {
            "name": "버튼 / 링크 클릭",
            "desc": "텍스트 기반 버튼 클릭",
            "code": 'page.get_by_role("button", name="조회").click()'
        },
        {
            "name": "텍스트 입력 (Fill)",
            "desc": "입력창에 0.001초 만에 값 주입",
            "code": 'page.locator("input[name=\'contractNo\']").fill(item["계약번호"])'
        },
        {
            "name": "그리드 첫 행 더블클릭",
            "desc": "조회 결과 테이블 1행 더블클릭",
            "code": 'page.locator("table tbody tr").first.dblclick()'
        },
        {
            "name": "파일 첨부 (DOM 직접 주입)",
            "desc": "윈도우 창 없이 input[type=file]에 직접 주입",
            "code": 'page.locator("input[type=\'file\']").first.set_input_files(item["file_path"])'
        },
        {
            "name": "체크박스 / 라디오 선택",
            "desc": "체크박스 체크",
            "code": 'page.locator("input[type=\'checkbox\']").first.check()'
        },
        {
            "name": "드롭다운 옵션 선택 (Select)",
            "desc": "select 엘리먼트 옵션 선택",
            "code": 'page.locator("select[name=\'본부\']").select_option("2본부")'
        },
        {
            "name": "키보드 키 입력 (Enter, Tab 등)",
            "desc": "특수 키 입력",
            "code": 'page.keyboard.press("Enter")'
        },
        {
            "name": "마우스 오버 (Hover)",
            "desc": "요소에 마우스 올리기",
            "code": 'page.locator("div.menu-item").hover()'
        },
        {
            "name": "React/Vue 가상DOM 강제 값 주입 (JS Inject Fallback)",
            "desc": "Playwright fill이 안 될 때 JS로 강제 주입 (React onChange 이벤트 포함)",
            "code": """# [JS Inject Fallback] React/Vue가 관리하는 입력창 강제 값 주입
page.evaluate(\"\"\"(val) => {
    const el = document.querySelector("input[name='contract_no']");
    const nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value'
    ).set;
    nativeSetter.call(el, val);
    el.dispatchEvent(new Event('input',  { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
}\"\"\", item["계약번호"])
"""
        },
    ],

    # =========================================================================
    # ⏳ 대기 및 검증
    # =========================================================================
    "⏳ 대기 및 검증 (Wait & Assert)": [
        {
            "name": "지정 시간 대기 (ms)",
            "desc": "밀리초 단위 고정 대기",
            "code": "page.wait_for_timeout(1000)  # 1초 대기"
        },
        {
            "name": "요소 나타날 때까지 대기",
            "desc": "특정 텍스트/셀렉터 렌더링 대기",
            "code": 'page.wait_for_selector("text=\'계약상세\'", timeout=10000)'
        },
        {
            "name": "네트워크 완료 대기",
            "desc": "네트워크 통신이 잠잠해질 때까지 대기",
            "code": 'page.wait_for_load_state("networkidle")'
        },
        {
            "name": "특정 API 서버 응답 대기",
            "desc": "저장/조회 API 응답 수신 대기",
            "code": """with page.expect_response(lambda r: "/api/contract" in r.url and r.status == 200):
    page.get_by_role("button", name="저장").click()
"""
        },
    ],

    # =========================================================================
    # 📑 다중 창 및 팝업
    # =========================================================================
    "📑 다중 창 및 팝업 (Multi-Window)": [
        {
            "name": "자식 팝업창 열기 및 제어 (Alias 방식)",
            "desc": "팝업창 핸들을 Alias 딕셔너리로 관리하여 스위칭",
            "code": """# [창 Alias 딕셔너리 방식] 부모/자식 창을 별칭으로 관리
windows = {"main": page}  # 부모창 등록

# 팝업창 캡처 및 Alias 등록
with page.expect_popup() as popup_info:
    page.locator("button:has-text('상세팝업')").click()
windows["popup_1"] = popup_info.value

# Alias로 자식창 접근 및 조작
target = windows["popup_1"]
target.wait_for_load_state("domcontentloaded")
target.locator("input[type='file']").set_input_files(item["file_path"])
target.get_by_role("button", name="저장").click()
target.close()
del windows["popup_1"]  # Alias 해제
"""
        },
        {
            "name": "새 탭 생성 및 이동",
            "desc": "새 탭을 띄워 독립 작업",
            "code": """new_tab = context.new_page()
new_tab.goto("http://175.119.156.105:3000/another_page")
# ... 작업 후 ...
new_tab.close()
"""
        },
        {
            "name": "알림창(Alert/Confirm) 자동 확인",
            "desc": "브라우저 Alert/Confirm 창 자동 수락 또는 취소",
            "code": """# ACCEPT: 확인 클릭 / 취소는 dialog.dismiss()
page.on("dialog", lambda dialog: (
    print(f"알림창: {dialog.message}"),
    dialog.accept()
))
"""
        },
        {
            "name": "프레임(iframe) 전환",
            "desc": "iframe 내부 요소로 접근",
            "code": """# iframe 내부 요소 접근
frame = page.frame_locator("iframe[name='contentFrame']")
frame.locator("input[name='asset_no']").fill(item["계약번호"])
"""
        },
    ],

    # =========================================================================
    # 🛡️ 제어문 및 방어 로직
    # =========================================================================
    "🛡️ 제어문 및 방어 로직 (Control Flow)": [
        {
            "name": "예외 방어 및 스크린샷 캡처 (try-except)",
            "desc": "에러 발생 시 프로그램 중단 없이 스크린샷 캡처 및 복구",
            "code": """import os
try:
    page.locator("input[name='contract']").fill(item["계약번호"])
    page.get_by_role("button", name="저장").click()
except Exception as err:
    print(f"🚨 오류 발생: {err}")
    os.makedirs("error_shots", exist_ok=True)
    page.screenshot(path=f"error_shots/err_{item.get('계약번호', 'unknown')}.png")
"""
        },
        {
            "name": "선택적 공지 팝업 무음 닫기",
            "desc": "팝업이 있으면 닫고, 없어도 에러 없이 통과",
            "code": """try:
    page.locator("div.modal button:has-text('닫기')").click(timeout=1000)
except Exception:
    pass  # 팝업 미발생 시 정상 통과
"""
        },
        {
            "name": "최대 N회 재시도 루프 (while retry)",
            "desc": "네트워크 불안정 시 N번까지 재시도",
            "code": """max_retries = 3
retry = 0
while retry < max_retries:
    try:
        page.get_by_role("button", name="조회").click(timeout=5000)
        break  # 성공 시 루프 탈출
    except Exception:
        retry += 1
        print(f"재시도 {retry}/{max_retries}...")
        page.wait_for_timeout(1000)
"""
        },
        {
            "name": "다중 조건 분기 (Select Case / match-case)",
            "desc": "문서 유형이나 계약 유형별 분기 처리",
            "code": """match item.get("계약구분", "일반"):
    case "유동":
        page.locator("input[name='opt_dynamic']").check()
    case "고정":
        page.locator("input[name='opt_fixed']").check()
    case _:
        print("기본 처리 진행")
"""
        },
        {
            "name": "조건문 분기 (if - elif - else)",
            "desc": "조건에 따른 분기",
            "code": """if "유네스코" in item.get("고객명", ""):
    page.locator("select[name='dept']").select_option("2본부")
elif item.get("금액", 0) >= 5000000:
    page.locator("button:has-text('임원 결재 상신')").click()
else:
    page.locator("select[name='dept']").select_option("1본부")
"""
        },
        {
            "name": "지역변수 격리 (def 함수로 감싸기)",
            "desc": "함수 내부 변수를 전역 공간에 노출시키지 않고 격리",
            "code": """def _process_temp(page, item):
    # 이 함수 내부 변수는 전역에 노출되지 않는 순수 지역변수
    temp_tax = float(item.get("금액", 0)) * 1.1
    temp_memo = f"부가세 포함: {temp_tax:,.0f}원"
    page.locator("input[name='memo']").fill(temp_memo)
    # 함수 종료 시 temp_tax, temp_memo 즉시 자동 소멸

_process_temp(page, item)
"""
        },
    ],

    # =========================================================================
    # 🖥️ 윈도우 앱 자동화 (Desktop Automation - ImageScan 이식)
    # =========================================================================
    "🖥️ 윈도우 앱 자동화 (Desktop / UIA)": [
        {
            "name": "윈도우 창 찾기 및 포커스 이동 (FIND_WINDOW)",
            "desc": "창 제목으로 윈도우 앱 창을 찾아 최앞으로 가져오기",
            "code": """# [FIND_WINDOW] 윈도우 앱 창 찾아 포커스 이동
import win32gui
import win32con

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

find_and_focus_window("사내 ERP - 계약관리")
"""
        },
        {
            "name": "UIA 컨트롤 조작 (UIA_CONTROL) - pywinauto",
            "desc": "윈도우 앱의 버튼, 입력창을 AutomationId/ClassName으로 제어",
            "code": """# [UIA_CONTROL] pywinauto로 윈도우 앱 컨트롤 조작
from pywinauto import Application

app = Application(backend="uia").connect(title_re=".*계약관리.*")
win = app.window(title_re=".*계약관리.*")

# 텍스트 입력
win.child_window(auto_id="txtContractNo", control_type="Edit").set_edit_text(item["계약번호"])

# 버튼 클릭
win.child_window(auto_id="btnSearch", control_type="Button").click()

# 값 읽기 (GET_VALUE)
result_text = win.child_window(auto_id="lblResult").window_text()
print(f"결과: {result_text}")
"""
        },
        {
            "name": "이미지 매칭 클릭 (PIXEL_MATCH) - pyautogui",
            "desc": "화면에서 버튼 이미지를 찾아 클릭 (CSS 셀렉터 불가 시 Fallback)",
            "code": """# [PIXEL_MATCH Fallback] 화면 이미지 매칭으로 버튼 클릭
import pyautogui
import time

# 스크린샷으로 저장한 버튼 이미지로 위치 탐색
btn_pos = pyautogui.locateOnScreen(
    "images/save_button.png",
    confidence=0.85,   # 85% 이상 유사도
    grayscale=True
)
if btn_pos:
    pyautogui.click(btn_pos)
    print(f"이미지 매칭 클릭 완료: {btn_pos}")
else:
    print("버튼 이미지를 찾지 못했습니다. 좌표 클릭으로 전환합니다.")
    pyautogui.click(520, 340)  # Fallback: 절대 좌표 클릭
"""
        },
        {
            "name": "OS 마우스/키보드 직접 제어 (KVM_INPUT)",
            "desc": "절대 좌표 클릭, 단축키, 키보드 탭 시퀀스 등 OS 레벨 입력",
            "code": """# [KVM_INPUT] OS 전역 마우스/키보드 직접 제어
import pyautogui
import time

# 절대 좌표 클릭
pyautogui.click(520, 340)

# 전역 단축키
pyautogui.hotkey("ctrl", "s")      # Ctrl+S: 저장
pyautogui.hotkey("alt", "F4")      # Alt+F4: 창 닫기

# 키보드 탭/엔터 시퀀스 (Tab으로 필드 이동)
pyautogui.press("tab")
pyautogui.typewrite(item["계약번호"], interval=0.05)
pyautogui.press("enter")

# 클립보드 붙여넣기
import pyperclip
pyperclip.copy(item["계약번호"])
pyautogui.hotkey("ctrl", "v")
time.sleep(0.3)
"""
        },
        {
            "name": "마우스 아래 UIA 요소 실시간 스캔",
            "desc": "현재 마우스 커서 위치의 윈도우 앱 컨트롤 정보 추출 (Live Inspector)",
            "code": """# [UIA Live Inspector] 마우스 아래 윈도우 컨트롤 정보 읽기
import win32api
from pywinauto import Desktop

def scan_element_under_mouse() -> dict:
    x, y = win32api.GetCursorPos()
    try:
        el = Desktop(backend="uia").from_point(x, y)
        info = {
            "control_type":  el.element_info.control_type,
            "automation_id": el.element_info.automation_id,
            "name":          el.element_info.name,
            "class_name":    el.element_info.class_name,
            "rect":          str(el.element_info.rectangle),
        }
        print(info)
        return info
    except Exception as e:
        print(f"스캔 실패: {e}")
        return {}

# Ctrl+클릭 시 스캔 (테스트용 즉시 실행)
scan_element_under_mouse()
"""
        },
        {
            "name": "4단계 Fallback 체계 (자동 강등 보호 로직)",
            "desc": "CSS → UIA → PIXEL_MATCH → KVM 순서로 자동 강등 시도",
            "code": """# [4단계 Fallback 완전 보호 체계]
import pyautogui
from pywinauto import Application

def robust_click(page, css_selector: str, uia_auto_id: str,
                 img_path: str, coord_x: int, coord_y: int):
    \"\"\"
    1순위: CSS 셀렉터 (Playwright 웹)
    2순위: UIA AutomationId (pywinauto 윈도우 앱)
    3순위: 이미지 매칭 (pyautogui PIXEL_MATCH)
    4순위: 절대 좌표 클릭 (KVM)
    \"\"\"
    # 1순위: 웹 CSS 셀렉터
    try:
        el = page.locator(css_selector).first
        el.click(timeout=2000)
        print(f"1순위 CSS 클릭 성공: {css_selector}")
        return
    except Exception:
        pass

    # 2순위: UIA (pywinauto)
    try:
        app = Application(backend="uia").connect(title_re=".*ERP.*")
        app.top_window().child_window(auto_id=uia_auto_id).click()
        print(f"2순위 UIA 클릭 성공: {uia_auto_id}")
        return
    except Exception:
        pass

    # 3순위: PIXEL_MATCH
    try:
        pos = pyautogui.locateOnScreen(img_path, confidence=0.85)
        if pos:
            pyautogui.click(pos)
            print(f"3순위 PIXEL_MATCH 클릭 성공: {img_path}")
            return
    except Exception:
        pass

    # 4순위: KVM 절대 좌표 (최후 수단)
    pyautogui.click(coord_x, coord_y)
    print(f"4순위 KVM 좌표 클릭: ({coord_x}, {coord_y})")

# 사용 예시
robust_click(
    page,
    css_selector = "button:has-text('저장')",
    uia_auto_id  = "btnSave",
    img_path     = "images/btn_save.png",
    coord_x      = 520, coord_y = 340
)
"""
        },
    ],

    # =========================================================================
    # 🔤 동적 변수
    # =========================================================================
    "🔤 동적 변수 (Variables)": [
        {
            "name": "item['계약번호']",
            "desc": "AI가 추출한 계약번호",
            "code": 'item["계약번호"]'
        },
        {
            "name": "item['file_path']",
            "desc": "OCR 완료된 PDF 파일 전체 경로",
            "code": 'item["file_path"]'
        },
        {
            "name": "item.get('고객명', '')",
            "desc": "AI가 추출한 고객사명 (없으면 빈 문자열)",
            "code": 'item.get("고객명", "")'
        },
        {
            "name": "item.get('금액', 0)",
            "desc": "AI가 추출한 계약금액 (없으면 0)",
            "code": 'item.get("금액", 0)'
        },
        {
            "name": "env['USER_ID']",
            "desc": "ERP 로그인 사용자 ID",
            "code": 'env["USER_ID"]'
        },
        {
            "name": "env['USER_PW']",
            "desc": "ERP 로그인 비밀번호",
            "code": 'env["USER_PW"]'
        },
        {
            "name": "env['ERP_URL']",
            "desc": "ERP 기본 접속 URL",
            "code": 'env["ERP_URL"]'
        },
        {
            "name": "del 변수명 (지역변수 즉시 삭제)",
            "desc": "사용 후 전역 공간에서 즉시 삭제",
            "code": "del temp_var  # 전역 메모리에서 즉시 제거"
        },
    ],

    # =========================================================================
    # 📊 데이터 및 파일 처리
    # =========================================================================
    "📊 데이터 및 파일 처리 (Data & File)": [
        {
            "name": "엑셀 파일 읽기 (pandas)",
            "desc": "엑셀 파일을 행 단위 딕셔너리 리스트로 로드",
            "code": """import pandas as pd

excel_path = "C:/data/계약목록.xlsx"
df = pd.read_excel(excel_path)
excel_rows = df.to_dict(orient="records")

for row in excel_rows:
    print(row)  # {'계약번호': '2D2607007', '고객명': '유네스코', ...}
"""
        },
        {
            "name": "JSON 파일 읽기/쓰기",
            "desc": "JSON 설정 또는 데이터 파일 입출력",
            "code": """import json

# 읽기
with open("config.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# 쓰기
with open("result.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
"""
        },
        {
            "name": "폴더 내 PDF 파일 목록 가져오기",
            "desc": "지정 폴더의 모든 PDF 파일 경로 리스트 반환",
            "code": """import glob
import os

input_dir = "C:/UBUS_PDF/1_대기"
pdf_files = sorted(glob.glob(os.path.join(input_dir, "*.pdf")))
print(f"총 {len(pdf_files)}개 파일 감지")
for f in pdf_files:
    print(f"  {os.path.basename(f)}")
"""
        },
        {
            "name": "파일 이동 (성공/실패 분기)",
            "desc": "처리 결과에 따라 완료 또는 오류 폴더로 파일 이동",
            "code": """import shutil, os

def move_file(src_path: str, success: bool):
    done_dir  = "C:/UBUS_PDF/3_RPA완료"
    error_dir = "C:/UBUS_PDF/4_오류격리"
    target_dir = done_dir if success else error_dir
    os.makedirs(target_dir, exist_ok=True)
    shutil.move(src_path, os.path.join(target_dir, os.path.basename(src_path)))
    print(f"파일 이동: {src_path} → {target_dir}")
"""
        },
        {
            "name": "현재 날짜/시간 변수",
            "desc": "파일명 등에 사용하는 날짜/시간 포맷",
            "code": """from datetime import datetime

now      = datetime.now()
date_str = now.strftime("%Y%m%d")       # 20260821
time_str = now.strftime("%H%M%S")       # 150030
dt_str   = now.strftime("%Y-%m-%d %H:%M:%S")  # 2026-08-21 15:00:30
print(f"실행 시각: {dt_str}")
"""
        },
    ],

    # =========================================================================
    # 🗄️ 클라우드 데이터베이스 (Neon PostgreSQL)
    # =========================================================================
    "🗄️ 데이터베이스 (Neon PostgreSQL)": [
        {
            "name": "Neon DB 매니저로 단일 계약서 로그 기록",
            "desc": "neon_db.py를 사용해 RPA 성공/실패 이력을 Neon 클라우드 DB에 저장",
            "code": """# [Neon PostgreSQL] RPA 처리 결과 클라우드 DB에 기록
from neon_db import NeonDBManager
from config_manager import ConfigManager

cfg = ConfigManager()
db = NeonDBManager(cfg.get("neon_database_url"))

# 단일 계약서 처리 결과 즉시 저장
log_id = db.log_contract_result(
    contract_no = item["계약번호"],
    file_name   = os.path.basename(item["file_path"]),
    file_path   = item["file_path"],
    status      = "RPA_DONE",  # 또는 "ERROR"
    ocr_data    = {"계약번호": item["계약번호"], "고객명": item.get("고객명", "")},
    duration_ms = 1200
)
print(f"Neon DB 로그 기록 완료 (ID: {log_id})")
"""
        },
        {
            "name": "직접 SQL 쿼리 실행 (psycopg2)",
            "desc": "Neon PostgreSQL에 직접 SELECT / INSERT 쿼리 실행",
            "code": """import psycopg2
from config_manager import ConfigManager

cfg = ConfigManager()
conn = psycopg2.connect(cfg.get("neon_database_url"))
cur = conn.cursor()

# 계약 조회 쿼리 예시
cur.execute("SELECT contract_no, status, executed_at FROM rpa_contract_logs ORDER BY executed_at DESC LIMIT 10;")
rows = cur.fetchall()
for r in rows:
    print(r)

cur.close()
conn.close()
"""
        },
        {
            "name": "RPA 배치 실행 요약 통계 저장 (rpa_batch_runs)",
            "desc": "전체 작업 완료 시 배치 통계(총건수, 성공, 실패) 기록",
            "code": """import psycopg2
import uuid
from datetime import datetime
from config_manager import ConfigManager

cfg = ConfigManager()
conn = psycopg2.connect(cfg.get("neon_database_url"))
cur = conn.cursor()

batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
cur.execute(\"\"\"
    INSERT INTO rpa_batch_runs (batch_id, total_files, success_count, fail_count, finished_at, status)
    VALUES (%s, %s, %s, %s, NOW(), 'COMPLETED')
\"\"\", (batch_id, len(pdf_items), success_count, fail_count))
conn.commit()
cur.close()
conn.close()
print(f"배치 실행 이력 저장 완료: {batch_id}")
"""
        },
    ],
}

