"""
Universal RPA Recorder - Advanced Code to Card Parser
파이썬 스크립트(Playwright + WinApp + Custom Code)를 지능적으로 분석하여
1회 실행(Setup)과 반복 실행(Loop) 스텝 카드로 자동 변환하는 고급 파서 엔진
"""

import re
from typing import Dict, List, Any, Tuple


def parse_advanced_python_to_scenario(code_text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    파이썬 코드를 분석하여 (setup_steps, loop_steps) 2개 영역으로 지능적 분할 변환
    """
    setup_steps: List[Dict[str, Any]] = []
    loop_steps: List[Dict[str, Any]] = []

    lines = code_text.splitlines()
    current_zone = "setup"  # 기본은 1회 실행(setup), for 루프나 반복 주석 발견 시 loop로 전환

    step_counter = 1

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1

        if not line:
            continue

        # 1. 주석 기반 명시적 영역 전환 감지
        if "# [1회" in line or "# [초기" in line or "# [setup" in line.lower():
            current_zone = "setup"
            continue
        if "# [반복" in line or "# [루프" in line or "# [loop" in line.lower() or "for " in line:
            current_zone = "loop"
            if line.startswith("for ") or line.startswith("#"):
                continue

        # 무시할 기본 임포트 및 세션 코드
        if line.startswith("import ") or line.startswith("from ") or line.startswith("#"):
            continue
        if any(kw in line for kw in ["sync_playwright", "playwright.chromium", "browser.new_context", "context.new_page"]):
            continue

        step_dict = None

        # 2. GOTO (페이지 이동)
        m = re.search(r'page\.goto\(["\'](.*?)["\']\)', line)
        if m:
            step_dict = {
                "id": f"step_{step_counter}",
                "action": "GOTO",
                "target": "",
                "value": m.group(1),
                "title": f"페이지 이동: {m.group(1)}"
            }

        # 3. FILL (get_by_role)
        elif "get_by_role" in line and ".fill(" in line:
            m = re.search(r'get_by_role\(["\'](\w+)["\'],\s*name=["\'](.*?)["\']\)\.fill\((.*?)\)', line)
            if m:
                role, name, raw_val = m.groups()
                val = raw_val.strip('"\'')
                target = f'input[placeholder*="{name}"], [aria-label*="{name}"]' if role == "textbox" else f'[role="{role}"][name="{name}"]'
                step_dict = {
                    "id": f"step_{step_counter}",
                    "action": "FILL",
                    "target": target,
                    "value": val,
                    "title": f"입력: {name} -> {val}"
                }

        # 4. CLICK (get_by_role)
        elif "get_by_role" in line and ".click(" in line:
            m = re.search(r'get_by_role\(["\'](\w+)["\'],\s*name=["\'](.*?)["\']\)\.click\(\)', line)
            if m:
                role, name = m.groups()
                target = f'button:has-text("{name}")' if role == "button" else f'[role="{role}"]:has-text("{name}")'
                step_dict = {
                    "id": f"step_{step_counter}",
                    "action": "CLICK",
                    "target": target,
                    "value": "",
                    "title": f"클릭: {name}"
                }

        # 5. DBLCLICK (더블클릭)
        elif ".dblclick(" in line:
            m = re.search(r'page\.locator\(["\'](.*?)["\']\).*?\.dblclick\(\)', line)
            target = m.group(1) if m else "table tbody tr"
            step_dict = {
                "id": f"step_{step_counter}",
                "action": "DBLCLICK",
                "target": target,
                "value": "",
                "title": f"더블클릭: {target}"
            }

        # 6. SET_FILES (파일 첨부)
        elif ".set_input_files(" in line:
            m = re.search(r'page\.locator\(["\'](.*?)["\']\).*?\.set_input_files\((.*?)\)', line)
            if m:
                target = m.group(1)
                raw_val = m.group(2).strip('"\'')
                val = "{{첨부파일_경로}}" if "file_path" in raw_val or "item" in raw_val else raw_val
                step_dict = {
                    "id": f"step_{step_counter}",
                    "action": "SET_FILES",
                    "target": target,
                    "value": val,
                    "title": f"파일 첨부: {target}"
                }

        # 7. FILL (locator)
        elif ".fill(" in line:
            m = re.search(r'page\.locator\(["\'](.*?)["\']\).*?\.fill\((.*?)\)', line)
            if m:
                target = m.group(1)
                raw_val = m.group(2).strip('"\'')
                val = "{{계약번호}}" if "contract_no" in raw_val or "item" in raw_val else raw_val
                step_dict = {
                    "id": f"step_{step_counter}",
                    "action": "FILL",
                    "target": target,
                    "value": val,
                    "title": f"입력: {target} -> {val}"
                }

        # 8. CLICK (locator)
        elif ".click(" in line:
            m = re.search(r'page\.locator\(["\'](.*?)["\']\).*?\.click\(\)', line)
            if m:
                target = m.group(1)
                step_dict = {
                    "id": f"step_{step_counter}",
                    "action": "CLICK",
                    "target": target,
                    "value": "",
                    "title": f"클릭: {target}"
                }

        # 9. CHECK (체크박스)
        elif ".check(" in line:
            m = re.search(r'page\.locator\(["\'](.*?)["\']\).*?\.check\(\)', line)
            target = m.group(1) if m else "input[type='checkbox']"
            step_dict = {
                "id": f"step_{step_counter}",
                "action": "CHECK",
                "target": target,
                "value": "true",
                "title": f"체크박스 선택: {target}"
            }

        # 10. SELECT_OPTION (드롭다운)
        elif ".select_option(" in line:
            m = re.search(r'page\.locator\(["\'](.*?)["\']\).*?\.select_option\(["\'](.*?)["\']\)', line)
            if m:
                target, val = m.groups()
                step_dict = {
                    "id": f"step_{step_counter}",
                    "action": "SELECT_OPTION",
                    "target": target,
                    "value": val,
                    "title": f"옵션 선택: {target} -> {val}"
                }

        # 11. WAIT_TIME (시간 대기)
        elif "wait_for_timeout(" in line or "time.sleep(" in line:
            m = re.search(r'wait_for_timeout\((\d+)\)', line)
            if not m:
                m = re.search(r'time\.sleep\(([0-9.]+)\)', line)
                ms = int(float(m.group(1)) * 1000) if m else 1000
            else:
                ms = int(m.group(1))
            step_dict = {
                "id": f"step_{step_counter}",
                "action": "WAIT_TIME",
                "target": "",
                "value": str(ms),
                "title": f"시간 대기: {ms}ms"
            }

        # 12. WAIT_SELECTOR (요소 대기)
        elif "wait_for_selector(" in line:
            m = re.search(r'wait_for_selector\(["\'](.*?)["\']', line)
            if m:
                target = m.group(1)
                step_dict = {
                    "id": f"step_{step_counter}",
                    "action": "WAIT_SELECTOR",
                    "target": target,
                    "value": "",
                    "title": f"요소 로딩 대기: {target}"
                }

        # 13. PRESS_KEY (키 입력)
        elif "keyboard.press(" in line or "press(" in line:
            m = re.search(r'press\(["\'](.*?)["\']\)', line)
            if m:
                key = m.group(1)
                step_dict = {
                    "id": f"step_{step_counter}",
                    "action": "PRESS_KEY",
                    "target": "",
                    "value": key,
                    "title": f"키 입력: {key}"
                }

        # 14. FIND_WINDOW (윈도우 창 찾기)
        elif "find_and_focus_window(" in line:
            m = re.search(r'find_and_focus_window\(["\'](.*?)["\']\)', line)
            title_kw = m.group(1) if m else "사내 ERP"
            step_dict = {
                "id": f"step_{step_counter}",
                "action": "FIND_WINDOW",
                "target": title_kw,
                "value": "",
                "title": f"윈도우 창 포커스: {title_kw}"
            }

        # 15. PIXEL_MATCH / KVM Click
        elif "pyautogui.click(" in line:
            m = re.search(r'pyautogui\.click\((\d+),\s*(\d+)\)', line)
            if m:
                x, y = m.groups()
                step_dict = {
                    "id": f"step_{step_counter}",
                    "action": "KVM_CLICK",
                    "target": f"{x},{y}",
                    "value": "",
                    "title": f"OS 좌표 클릭: ({x}, {y})"
                }
            else:
                step_dict = {
                    "id": f"step_{step_counter}",
                    "action": "PIXEL_MATCH",
                    "target": "image",
                    "value": "",
                    "title": "이미지 매칭 클릭"
                }

        # 16. 기타 파이썬 로직/함수 블록 -> EXEC_CODE 카드로 보존
        else:
            # 단순 변수 할당이나 짧은 문장은 건너뛰고, 실제 로직이 있는 경우 EXEC_CODE 카드로 생성
            if len(line) > 10 and not line.startswith("print(") and not line.startswith("return "):
                step_dict = {
                    "id": f"step_{step_counter}",
                    "action": "EXEC_CODE",
                    "target": "",
                    "value": line,
                    "title": f"파이썬 실행: {line[:30]}..."
                }

        if step_dict:
            step_counter += 1
            if current_zone == "loop":
                loop_steps.append(step_dict)
            else:
                setup_steps.append(step_dict)

    return setup_steps, loop_steps
