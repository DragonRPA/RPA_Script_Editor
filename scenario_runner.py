"""
UBUS Contract RPA & Ollama Pipeline - Scenario Runner Engine
Universal RPA Recorder가 생성한 scenario.json을 로드하여 고속/무인 실행하는 전용 재생 엔진
"""

import time
import os
from typing import Dict, List, Any, Callable, Optional
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext


class ScenarioRunner:
    """scenario.json 워크플로우를 해석하고 실행하는 범용 재생기 엔진"""

    def __init__(
        self,
        scenario_data: Dict[str, Any],
        headless: bool = False,
        log_callback: Optional[Callable[[str, str], None]] = None
    ):
        self.scenario = scenario_data
        self.headless = headless
        self.log_callback = log_callback
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_running = False

    def log(self, message: str, level: str = "INFO"):
        timestamp = time.strftime("%H:%M:%S")
        formatted = f"[{timestamp}] [{level}] {message}"
        print(formatted)
        if self.log_callback:
            self.log_callback(formatted, level)

    def start_session(self) -> bool:
        """브라우저 세션 시작"""
        try:
            self.log(f"브라우저 재생 세션 기동 (Headless={self.headless})")
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
            )
            self.context = self.browser.new_context(no_viewport=True, ignore_https_errors=True)
            self.page = self.context.new_page()
            self.is_running = True
            return True
        except Exception as e:
            self.log(f"브라우저 세션 시작 실패: {e}", "ERROR")
            self.close_session()
            return False

    def close_session(self):
        """브라우저 세션 안전 종료"""
        self.is_running = False
        try:
            if self.page and not self.page.is_closed():
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass
        finally:
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None
            self.log("브라우저 재생 세션 종료됨")

    def run_setup_steps(self, global_variables: Dict[str, str]) -> bool:
        """1회성 초기화 스텝(로그인 등) 실행"""
        steps = self.scenario.get("setup_steps", [])
        if not steps:
            self.log("1회 실행(Setup) 스텝이 비어있습니다. 건너뜁니다.")
            return True

        self.log(f"[1회 실행 시작] 총 {len(steps)}개 초기화 스텝 실행...")
        for idx, step in enumerate(steps):
            if not self.is_running:
                return False
            ok = self._execute_step(step, global_variables, idx + 1, total=len(steps))
            if not ok:
                self.log(f"초기화 스텝 {idx + 1} 실행 실패로 중단합니다.", "ERROR")
                return False
        self.log("[1회 실행 완료] 초기화 세션이 성공적으로 완료되었습니다.", "SUCCESS")
        return True

    def run_loop_steps(self, item_variables: Dict[str, str]) -> bool:
        """데이터 1건에 대한 반복 루프 스텝 실행"""
        steps = self.scenario.get("loop_steps", [])
        if not steps:
            self.log("반복 루프(Loop) 스텝이 비어있습니다.", "WARN")
            return False

        for idx, step in enumerate(steps):
            if not self.is_running:
                return False
            ok = self._execute_step(step, item_variables, idx + 1, total=len(steps))
            if not ok:
                return False
        return True

    def _execute_step(self, step: Dict[str, Any], variables: Dict[str, str], step_num: int, total: int) -> bool:
        """개별 스텝 실행 및 변수 치환"""
        action = step.get("action", "").upper()
        target = step.get("target", "")
        raw_val = step.get("value", "")

        # 변수 치환
        val = raw_val
        for k, v in variables.items():
            val = val.replace(f"{{{{{k}}}}}", str(v))
            val = val.replace(f"${{{k}}}", str(v))

        # 대상 셀렉터 내부 변수 치환
        tgt = target
        for k, v in variables.items():
            tgt = tgt.replace(f"{{{{{k}}}}}", str(v))

        try:
            if action == "GOTO":
                self.log(f"[{step_num}/{total}] 페이지 이동: {val}")
                self.page.goto(val, wait_until="domcontentloaded", timeout=30000)

            elif action == "FILL":
                self.log(f"[{step_num}/{total}] 입력: {tgt} ➔ {val}")
                loc = self.page.locator(tgt).first
                loc.wait_for(state="visible", timeout=10000)
                loc.fill(val)

            elif action == "CLICK":
                self.log(f"[{step_num}/{total}] 클릭: {tgt}")
                loc = self.page.locator(tgt).first
                loc.wait_for(state="visible", timeout=10000)
                loc.click()

            elif action == "DBLCLICK":
                self.log(f"[{step_num}/{total}] 더블클릭: {tgt}")
                loc = self.page.locator(tgt).first
                loc.wait_for(state="visible", timeout=10000)
                loc.dblclick()

            elif action == "SET_FILES":
                self.log(f"[{step_num}/{total}] 파일 첨부 주입: {os.path.basename(val)}")
                file_inputs = self.page.locator(tgt)
                if file_inputs.count() > 0:
                    file_inputs.first.set_input_files(val)
                else:
                    # 파일 인풋 직접 탐색
                    all_file_inputs = self.page.locator("input[type='file']")
                    if all_file_inputs.count() > 0:
                        all_file_inputs.first.set_input_files(val)
                    else:
                        with self.page.expect_file_chooser(timeout=5000) as fc_info:
                            self.page.locator("button:has-text('파일 선택'), label:has-text('파일 선택')").first.click()
                        fc_info.value.set_files(val)

            elif action == "WAIT_TIME":
                ms = int(val) if val.isdigit() else 1000
                self.log(f"[{step_num}/{total}] 대기: {ms}ms")
                self.page.wait_for_timeout(ms)

            elif action == "WAIT_SELECTOR":
                self.log(f"[{step_num}/{total}] 요소 대기: {tgt}")
                self.page.wait_for_selector(tgt, timeout=15000)

            elif action == "PRESS_KEY":
                self.log(f"[{step_num}/{total}] 키 입력: {val}")
                self.page.keyboard.press(val)

            return True

        except Exception as e:
            self.log(f"[{step_num}/{total}] 스텝 실행 실패 [{action} {tgt}]: {e}", "ERROR")
            return False
