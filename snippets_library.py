"""
Universal RPA - Snippet Library
RPA 개발 및 자동화에 필요한 모든 Playwright, 파이썬 제어문, 변수, 팝업 제어 스니펫 라이브러리
"""

from typing import Dict, List, Any

SNIPPET_CATEGORIES: Dict[str, List[Dict[str, str]]] = {
    "📁 템플릿 (Templates)": [
        {
            "name": "전체 PDF 반복 루프 뼈대",
            "desc": "Ollama 추출 변수와 함께 전체 PDF를 순회하는 표준 루프",
            "code": """# [PDF 전체 순회 루프]
for idx, item in enumerate(pdf_items, start=1):
    contract_no = item.get("계약번호", "")
    file_path = item.get("file_path", "")
    print(f"[{idx}/{len(pdf_items)}] 처리 시작: {contract_no}")

    # 1. 계약번호 검색 및 조회
    page.locator("input[name*='contract']").first.fill(contract_no)
    page.get_by_role("button", name="조회").click()
    page.wait_for_timeout(500)

    # 2. 첫 번째 결과 상세 진입
    page.locator("table tbody tr").first.dblclick()

    # 3. 파일 첨부 및 저장
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
    file_path = item["file_path"]

    # 계약번호 검색
    page.locator("input[name*='contract']").fill(contract_no)
    page.get_by_role("button", name="조회").click()
    
    # 상세 열기 및 파일 첨부
    page.locator("table tbody tr").first.dblclick()
    page.locator("input[type='file']").set_input_files(file_path)
    page.get_by_role("button", name="저장").click()
    return True
"""
        }
    ],

    "🖱️ 웹 조작 (Actions)": [
        {
            "name": "버튼 / 링크 클릭",
            "desc": "텍스트 기반 버튼 클릭",
            "code": "page.get_by_role(\"button\", name=\"조회\").click()"
        },
        {
            "name": "텍스트 입력 (Fill)",
            "desc": "입력창에 0.001초 만에 값 주입",
            "code": "page.locator(\"input[name='contractNo']\").fill(item[\"계약번호\"])"
        },
        {
            "name": "그리드 첫 행 더블클릭",
            "desc": "조회 결과 테이블 1행 더블클릭",
            "code": "page.locator(\"table tbody tr\").first.dblclick()"
        },
        {
            "name": "파일 첨부 (DOM 직접 주입)",
            "desc": "윈도우 창 없이 input[type=file]에 직접 주입",
            "code": "page.locator(\"input[type='file']\").first.set_input_files(item[\"file_path\"])"
        },
        {
            "name": "체크박스 / 라디오 선택",
            "desc": "체크박스 체크",
            "code": "page.locator(\"input[type='checkbox']\").first.check()"
        },
        {
            "name": "드롭다운 옵션 선택 (Select)",
            "desc": "select 엘리먼트 옵션 선택",
            "code": "page.locator(\"select[name='본부']\").select_option(\"2본부\")"
        },
        {
            "name": "키보드 키 입력 (Enter, Tab 등)",
            "desc": "특수 키 입력",
            "code": "page.keyboard.press(\"Enter\")"
        },
        {
            "name": "마우스 오버 (Hover)",
            "desc": "요소에 마우스 올리기",
            "code": "page.locator(\"div.menu-item\").hover()"
        }
    ],

    "⏳ 대기 및 검증 (Wait)": [
        {
            "name": "지정 시간 대기 (ms)",
            "desc": "밀리초 단위 고정 대기",
            "code": "page.wait_for_timeout(1000) # 1초 대기"
        },
        {
            "name": "요소 나타날 때까지 대기",
            "desc": "특정 텍스트/셀렉터 렌더링 대기",
            "code": "page.wait_for_selector(\"text='계약상세'\", timeout=10000)"
        },
        {
            "name": "네트워크 완료 대기",
            "desc": "네트워크 통신이 잠잠해질 때까지 대기",
            "code": "page.wait_for_load_state(\"networkidle\")"
        },
        {
            "name": "특정 API 서버 응답 대기",
            "desc": "저장/조회 API 응답 수신 대기",
            "code": "with page.expect_response(lambda r: \"/api/contract\" in r.url and r.status == 200):\n    page.get_by_role(\"button\", name=\"저장\").click()"
        }
    ],

    "📑 다중 창 및 팝업 (Windows & Popups)": [
        {
            "name": "자식 팝업창 열기 및 제어",
            "desc": "클릭 시 새로 뜨는 팝업 창 핸들 낚아채기",
            "code": """# [자식 팝업창 캡처 및 제어]
with page.expect_popup() as popup_info:
    page.locator("button:has-text('상세팝업')").click()
popup_page = popup_info.value

# 자식 창에서 작업
popup_page.wait_for_load_state("domcontentloaded")
popup_page.locator("input[type='file']").set_input_files(item["file_path"])
popup_page.get_by_role("button", name="저장").click()
popup_page.close() # 작업 후 자식창 닫기
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
            "desc": "브라우저 Alert/Confirm 창 자동 수락",
            "code": """# 다이얼로그 자동 확인 리스너
page.on("dialog", lambda dialog: dialog.accept())
"""
        }
    ],

    "🛡️ 제어문 및 방어 로직 (Control Flow)": [
        {
            "name": "예외 방어 및 스크린샷 캡처 (try-except)",
            "desc": "에러 발생 시 프로그램 중단 없이 스크린샷 캡처 및 복구",
            "code": """try:
    # 핵심 실행 코드
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
    pass # 팝업 미발생 시 정상 통과
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
        break # 성공 시 루프 탈출
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
else:
    page.locator("select[name='dept']").select_option("1본부")
"""
        }
    ],

    "🔤 동적 변수 (Variables)": [
        {
            "name": "item['계약번호']",
            "desc": "AI가 추출한 계약번호",
            "code": "item[\"계약번호\"]"
        },
        {
            "name": "item['file_path']",
            "desc": "OCR 완료된 PDF 파일 전체 경로",
            "code": "item[\"file_path\"]"
        },
        {
            "name": "item['고객명']",
            "desc": "AI가 추출한 고객사명",
            "code": "item.get(\"고객명\", \"\")"
        },
        {
            "name": "env['USER_ID']",
            "desc": "사용자 ID",
            "code": "env[\"USER_ID\"]"
        },
        {
            "name": "env['USER_PW']",
            "desc": "사용자 비밀번호",
            "code": "env[\"USER_PW\"]"
        },
        {
            "name": "env['ERP_URL']",
            "desc": "ERP 기본 URL",
            "code": "env[\"ERP_URL\"]"
        }
    ]
}
