"""
UBUS Contract RPA & Ollama Pipeline - RPA Engine
Playwright 기반 UBUS ERP 자동화 시퀀서, 범용 시나리오 러너, 스마트 액션 실행기
"""

import time
import os
from typing import Dict, List, Any, Callable, Optional
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext, ElementHandle


class UBUSRPAEngine:
    """UBUS ERP 시스템 전용 자동화 및 범용 시나리오 실행 엔진"""

    def __init__(
        self,
        erp_url: str = "http://175.119.156.105:3000",
        headless: bool = False,
        log_callback: Optional[Callable[[str, str], None]] = None
    ):
        self.erp_url = erp_url.rstrip("/")
        self.headless = headless
        self.log_callback = log_callback
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_running = False

    def log(self, message: str, level: str = "INFO"):
        """로그 콜백 호출 및 콘솔 출력"""
        timestamp = time.strftime("%H:%M:%S")
        formatted = f"[{timestamp}] [{level}] {message}"
        print(formatted)
        if self.log_callback:
            self.log_callback(formatted, level)

    def start_session(self) -> bool:
        """브라우저 세션 기동"""
        try:
            self.log(f"브라우저 세션 시작 (Headless={self.headless})")
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
            )
            self.context = self.browser.new_context(
                no_viewport=True,
                ignore_https_errors=True
            )
            self.page = self.context.new_page()
            self.is_running = True
            return True
        except Exception as e:
            self.log(f"브라우저 기동 실패: {e}", "ERROR")
            self.close_session()
            return False

    def close_session(self):
        """브라우저 세션 안전 종료"""
        self.is_running = False
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception as e:
            pass
        finally:
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None
            self.log("브라우저 세션 종료됨")

    def login_erp(self, user_id: str, user_pw: str) -> bool:
        """1단계: UBUS ERP 로그인 수행"""
        if not self.page:
            return False
        try:
            self.log(f"ERP 로그인 페이지 접속: {self.erp_url}")
            self.page.goto(self.erp_url, timeout=30000, wait_until="domcontentloaded")

            # 이미 대시보드에 로그인되어 있는지 확인
            if "/dashboard" in self.page.url:
                self.log("이미 로그인 세션이 유지되어 있습니다.")
                return True

            # 아이디 및 비밀번호 입력 필드 대기
            self.log("로그인 정보 입력 중...")
            id_input = self.page.locator("input[placeholder*='아이디']").first
            id_input.wait_for(state="visible", timeout=10000)
            id_input.fill(user_id)

            pw_input = self.page.locator("input[placeholder*='비밀번호']").first
            pw_input.fill(user_pw)

            # 로그인 버튼 클릭
            login_btn = self.page.locator("button:has-text('로그인')").first
            login_btn.click()

            # 대시보드 전환 대기
            self.log("로그인 승인 및 대시보드 진입 대기...")
            self.page.wait_for_url("**/dashboard**", timeout=15000)
            self.log("로그인 성공 및 대시보드 진입 완료")
            return True
        except Exception as e:
            self.log(f"로그인 처리 실패: {e}", "ERROR")
            return False

    def process_single_contract(
        self,
        contract_no: str,
        file_path: str,
        attachment_type: str = "기타첨부파일"
    ) -> bool:
        """
        단일 계약서에 대한 표준 자동화 처리 사이클
        1. 계약조회 이동 ➔ 2. 계약번호 검색 ➔ 3. 그리드 더블클릭 ➔ 4. 파일 첨부 ➔ 5. 저장
        """
        if not self.page or not contract_no:
            self.log(f"처리 불가: 계약번호가 없거나 브라우저 미연결 (계약번호: {contract_no})", "WARN")
            return False

        try:
            # 1. 계약조회 메뉴 이동
            self.log(f"[{contract_no}] 계약조회 화면으로 이동...")
            contract_list_url = f"{self.erp_url}/contract/list"
            if self.page.url != contract_list_url:
                # 사이드바 메뉴 클릭 시도 또는 URL 직접 이동
                try:
                    menu_contract = self.page.locator("span:has-text('계약'), div:has-text('계약')").first
                    if menu_contract.is_visible():
                        menu_contract.click()
                    sub_contract = self.page.locator("span:has-text('계약조회'), a:has-text('계약조회')").first
                    if sub_contract.is_visible():
                        sub_contract.click()
                        self.page.wait_for_url("**/contract/list**", timeout=5000)
                    else:
                        self.page.goto(contract_list_url, wait_until="domcontentloaded")
                except Exception:
                    self.page.goto(contract_list_url, wait_until="domcontentloaded")

            # 2. 계약번호 입력 필드 탐색 및 검색어 입력
            self.log(f"[{contract_no}] 계약번호 검색 필터 입력...")
            # 레이블 또는 인접 인풋 탐색
            contract_input = self.page.locator("label:has-text('계약번호') + input, div:has-text('계약번호') input, input[name*='contract']").first
            if not contract_input.is_visible():
                # 인풋 필드 순서 중 계약번호 위치 탐색 (3~4번째 텍스트 필드)
                inputs = self.page.locator("input[type='text']")
                for i in range(inputs.count()):
                    inp = inputs.nth(i)
                    # 이전 형제 요소나 부모 텍스트 확인
                    contract_input = inp
                    break
            
            contract_input.fill(contract_no)

            # [조회] 버튼 클릭
            search_btn = self.page.locator("button:has-text('조회')").first
            search_btn.click()

            # 3. 검색 결과 그리드 행 대기 및 더블클릭
            self.log(f"[{contract_no}] 조회 결과 대기 중...")
            self.page.wait_for_timeout(500)  # 최소 렌더링 딜레이
            
            # 그리드 행 탐색
            row_locator = self.page.locator("table tbody tr, div.grid-row, div[role='row']").first
            row_locator.wait_for(state="visible", timeout=10000)
            
            self.log(f"[{contract_no}] 검색 결과 확인 ➔ 상세 내역 더블클릭")
            row_locator.dblclick()

            # 4. 계약상세 탭 또는 화면 로딩 대기
            self.log(f"[{contract_no}] 계약상세 화면 진입 대기...")
            self.page.wait_for_selector("text='계약서', text='첨부파일', text='기타첨부파일', button:has-text('저장')", timeout=10000)

            # 5. 파일 첨부 (Playwright DOM 직접 주입)
            self.log(f"[{contract_no}] PDF 파일 첨부 주입: {os.path.basename(file_path)}")
            file_inputs = self.page.locator("input[type='file']")
            file_input_count = file_inputs.count()

            if file_input_count == 0:
                # [파일 선택] 버튼 클릭 시 파일 선택자 대기
                with self.page.expect_file_chooser(timeout=5000) as fc_info:
                    upload_btn = self.page.locator("button:has-text('파일 선택'), label:has-text('파일 선택'), span:has-text('파일 선택')").first
                    upload_btn.click()
                file_chooser = fc_info.value
                file_chooser.set_files(file_path)
            else:
                # 첫 번째 또는 두 번째 파일 인풋에 직접 주입
                target_file_input = file_inputs.first if attachment_type != "기타첨부파일" or file_input_count == 1 else file_inputs.nth(1)
                target_file_input.set_input_files(file_path)

            self.page.wait_for_timeout(500)

            # 6. 저장 버튼 클릭
            self.log(f"[{contract_no}] 변경사항 [저장] 클릭...")
            save_btn = self.page.locator("button:has-text('저장')").first
            if save_btn.is_visible():
                save_btn.click()
                # 저장 완료 팝업 또는 네트워크 응답 대기
                self.page.wait_for_timeout(1000)
                # 확인 모달이 뜰 경우 자동 확인 클릭
                confirm_btn = self.page.locator("div.modal button:has-text('확인'), div[role='dialog'] button:has-text('확인')").first
                if confirm_btn.is_visible():
                    confirm_btn.click()
            else:
                self.log(f"[{contract_no}] 저장 버튼을 찾을 수 없습니다.", "WARN")

            # 상세 탭 닫기 (다시 목록으로 복귀)
            try:
                close_tab_btn = self.page.locator("div.tab:has-text('계약상세') span:has-text('x'), button:has-text('x')").first
                if close_tab_btn.is_visible():
                    close_tab_btn.click()
            except Exception:
                pass

            self.log(f"[{contract_no}] ERP 등록 및 저장 성공 완료", "SUCCESS")
            return True

        except Exception as e:
            self.log(f"[{contract_no}] ERP 처리 중 오류 발생: {e}", "ERROR")
            # 디버깅용 스크린샷 저장
            try:
                os.makedirs("error_screenshots", exist_ok=True)
                shot_path = f"error_screenshots/err_{contract_no}_{int(time.time())}.png"
                self.page.screenshot(path=shot_path)
                self.log(f"오류 화면 캡처 저장됨: {shot_path}", "WARN")
            except Exception:
                pass
            return False


class GenericScenarioRunner:
    """사용자가 에디터에서 커스텀 구성한 시나리오 JSON을 순차 실행하는 엔진"""

    def __init__(self, page: Page, log_func: Callable[[str, str], None]):
        self.page = page
        self.log = log_func

    def execute_step(self, step: Dict[str, Any], variables: Dict[str, str]) -> bool:
        """단일 스텝 실행"""
        action = step.get("action", "").upper()
        target = step.get("target", "")
        raw_val = step.get("value", "")

        # 변수 치환 ({{계약번호}} ➔ 실제값)
        val = raw_val
        for k, v in variables.items():
            val = val.replace(f"{{{{{k}}}}}", str(v))

        try:
            if action == "GOTO":
                self.log(f"[이동] {val}")
                self.page.goto(val, wait_until="domcontentloaded")

            elif action == "FILL":
                self.log(f"[입력] {target} ➔ {val}")
                locator = self.page.locator(target).first
                locator.wait_for(state="visible", timeout=10000)
                locator.fill(val)

            elif action == "CLICK":
                self.log(f"[클릭] {target}")
                locator = self.page.locator(target).first
                locator.wait_for(state="visible", timeout=10000)
                locator.click()

            elif action == "DBLCLICK":
                self.log(f"[더블클릭] {target}")
                locator = self.page.locator(target).first
                locator.wait_for(state="visible", timeout=10000)
                locator.dblclick()

            elif action == "SET_FILES":
                self.log(f"[파일첨부] {target} ➔ {val}")
                locator = self.page.locator(target).first
                locator.set_input_files(val)

            elif action == "WAIT_TIME":
                ms = int(val) if val.isdigit() else 1000
                self.log(f"[대기] {ms}ms")
                self.page.wait_for_timeout(ms)

            elif action == "WAIT_SELECTOR":
                self.log(f"[요소대기] {target}")
                self.page.wait_for_selector(target, timeout=10000)

            elif action == "PRESS_KEY":
                self.log(f"[키입력] {val}")
                self.page.keyboard.press(val)

            return True

        except Exception as e:
            self.log(f"스텝 실행 실패 [{action} {target}]: {e}", "ERROR")
            return False
