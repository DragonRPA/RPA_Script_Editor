"""
Universal RPA Recorder - Advanced Code to Card Parser
파이썬 스크립트(Playwright + WinApp + 변수 할당 패턴)를 지능적으로 분석하여
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
    locator_vars: Dict[str, str] = {}  # 변수 할당된 셀렉터 추적 (예: contract_input = page.locator(...))

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1

        if not line:
            continue

        # 1. 주석 기반 명시적 영역 전환 감지
        if any(kw in line for kw in ["# [1단계", "# [1회", "# [초기", "# [setup", "# [Setup"]):
            current_zone = "setup"
            continue
        if any(kw in line for kw in ["# [2단계", "# [반복", "# [루프", "# [loop", "# [Loop"]):
            current_zone = "loop"
            continue

        if line.startswith("for ") and "in " in line:
            current_zone = "loop"
            continue

        # 무시할 기본 보일러플레이트 코드
        if line.startswith("import ") or line.startswith("from ") or line.startswith("#"):
            continue
        if any(kw in line for kw in [
            "sync_playwright", "playwright.chromium", "browser.new_context", "context.new_page",
            "def run(", "if __name__", "with sync_playwright", "test_items = [", "pdf_items = [",
            "context.close()", "browser.close()"
        ]):
            continue
        if line in ["[", "]", "}", "{", "],"]:
            continue
        if line.startswith('{"계약번호"') or line.startswith("{'계약번호'"):
            continue

        step_dict = None

        # 2. 로케이터 변수 할당 감지 (예: var_name = page.locator("..."))
        var_assign_match = re.search(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*page\.locator\(["\'](.*?)["\']\)', line)
        if var_assign_match:
            var_name, sel = var_assign_match.groups()
            locator_vars[var_name] = sel
            continue

        # 3. GOTO (페이지 이동)
        m = re.search(r'page\.goto\(["\'](.*?)["\']\)', line)
        if m:
            step_dict = {
                "id": f"step_{step_counter}",
                "action": "GOTO",
                "target": "",
                "value": m.group(1),
                "title": f"페이지 이동: {m.group(1)}"
            }

        # 4. FILL (get_by_role)
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

        # 5. CLICK (get_by_role)
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

        # 6. DBLCLICK (더블클릭)
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

        # 7. SET_FILES (파일 첨부)
        elif ".set_input_files(" in line:
            m = re.search(r'page\.locator\(["\'](.*?)["\']\).*?\.set_input_files\((.*?)\)', line)
            if m:
                target = m.group(1)
                raw_val = m.group(2).strip('"\'')
                val = "{{첨부파일_경로}}" if ("file_path" in raw_val or "item" in raw_val) else raw_val
                step_dict = {
                    "id": f"step_{step_counter}",
                    "action": "SET_FILES",
                    "target": target,
                    "value": val,
                    "title": f"파일 첨부: {target}"
                }

        # 8. FILL (locator 또는 로케이터 변수)
        elif ".fill(" in line:
            # 8-1: page.locator("...").fill(...)
            m = re.search(r'page\.locator\(["\'](.*?)["\']\).*?\.fill\((.*?)\)', line)
            if m:
                target = m.group(1)
                raw_val = m.group(2).strip('"\'')
                val = "{{계약번호}}" if ("contract" in raw_val or "item" in raw_val) else raw_val
                step_dict = {
                    "id": f"step_{step_counter}",
                    "action": "FILL",
                    "target": target,
                    "value": val,
                    "title": f"입력: {target} -> {val}"
                }
            else:
                # 8-2: var_name.fill(...)
                m_var = re.search(r'^([a-zA-Z_][a-zA-Z0-9_]*)\.fill\((.*?)\)', line)
                if m_var:
                    v_name, raw_val = m_var.groups()
                    target = locator_vars.get(v_name, v_name)
                    val = "{{계약번호}}" if ("contract" in raw_val or "item" in raw_val) else raw_val.strip('"\'')
                    step_dict = {
                        "id": f"step_{step_counter}",
                        "action": "FILL",
                        "target": target,
                        "value": val,
                        "title": f"입력: {target} -> {val}"
                    }

        # 9. CLICK (locator 필터 또는 클릭)
        elif "locator(" in line and ".filter(" in line and ".click(" in line:
            m = re.search(r'page\.locator\(["\'](.*?)["\']\)\.filter\(has_text=.*?["\'](.*?)["\']\)\.click\(\)', line)
            if m:
                tag, text = m.groups()
                clean_text = text.strip("^$")
                target = f'{tag}:has-text("{clean_text}")'
                step_dict = {
                    "id": f"step_{step_counter}",
                    "action": "CLICK",
                    "target": target,
                    "value": "",
                    "title": f"클릭: {clean_text}"
                }
            else:
                m2 = re.search(r'page\.locator\(["\'](.*?)["\']\).*?\.click\(\)', line)
                target = m2.group(1) if m2 else "button"
                step_dict = {
                    "id": f"step_{step_counter}",
                    "action": "CLICK",
                    "target": target,
                    "value": "",
                    "title": f"클릭: {target}"
                }

        # 10. CLICK (일반 locator.click)
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

        # 11. CHECK (체크박스)
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

        # 12. SELECT_OPTION (드롭다운)
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

        # 13. WAIT_TIME (시간 대기)
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

        # 14. WAIT_SELECTOR / WAIT_LOAD_STATE
        elif "wait_for_selector(" in line or "wait_for_load_state(" in line:
            if "wait_for_load_state(" in line:
                step_dict = {
                    "id": f"step_{step_counter}",
                    "action": "WAIT_TIME",
                    "target": "",
                    "value": "1000",
                    "title": "화면 로딩 대기 (1000ms)"
                }
            else:
                m = re.search(r'wait_for_selector\(["\'](.*?)["\']', line)
                target = m.group(1) if m else ""
                step_dict = {
                    "id": f"step_{step_counter}",
                    "action": "WAIT_SELECTOR",
                    "target": target,
                    "value": "",
                    "title": f"요소 로딩 대기: {target}"
                }

        # 15. PRESS_KEY (키 입력)
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

        # 16. FIND_WINDOW (윈도우 창 찾기)
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

        # 17. PIXEL_MATCH / KVM Click
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

        # 18. 기타 실질적 파이썬 실행문 -> EXEC_CODE
        else:
            # 단순 변수 할당(`contract_no = item[...]`)이나 print문은 카드로 만들지 않고 스킵
            if any(line.startswith(prefix) for prefix in [
                "print(", "return ", "contract_no =", "file_path =", "idx =", "item ="
            ]):
                continue

            if len(line) > 10:
                step_dict = {
                    "id": f"step_{step_counter}",
                    "action": "EXEC_CODE",
                    "target": "",
                    "value": line,
                    "title": f"파이썬 실행: {line[:25]}..."
                }

        if step_dict:
            step_counter += 1
            if current_zone == "loop":
                loop_steps.append(step_dict)
            else:
                setup_steps.append(step_dict)

    return setup_steps, loop_steps
