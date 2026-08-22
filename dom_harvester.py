"""
Universal RPA - Live Interactive DOM & Window UI Harvester
- 열려있는 윈도우 창(HWND) 직통 검사 (새로고침/깜빡임 0%, 로그인 세션 100% 보존)
- Windows UIAutomation COM 트리 순회로 화면에 렌더링된 실시간 컨트롤 전수 수집
- 웹 브라우저(Chrome/Edge) 및 데스크톱 앱(ERP/더존/SAP) 전천후 지원
"""

import os
import sys
import time
import re
from typing import Dict, Any, List, Optional, Tuple

try:
    import uiautomation as uia
    HAS_UIA = True
except ImportError:
    HAS_UIA = False

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


class DOMHarvester:
    """실시간 UI/DOM 객체 수집기 (깜빡임/새로고침 없는 윈도우 핸들 직통 검사)"""

    _active_playwright_page = None

    @classmethod
    def set_active_page(cls, page):
        cls._active_playwright_page = page

    @classmethod
    def harvest_live_dom(cls, url: str = "", hwnd: int = 0, window_title: str = "", browser_type: str = "chrome", timeout_sec: int = 15) -> Dict[str, Any]:
        """
        1. 윈도우 핸들(HWND) 또는 창 타이틀이 주어지면, 브라우저를 새로 열거나 새로고침하지 않고
           현재 화면에 열려있는 바로 그 창에서 실시간 UIA 트리로 0.1초 만에 전수 추출 (깜빡임 0%, 세션 100% 보존)
        2. 활성 Playwright 페이지가 있으면 페이지 리로드 없이 즉시 DOM 추출
        3. URL만 있을 때만 지정된 브라우저(Chrome/Edge) 엔진으로 안전하게 렌더링 대기 후 추출
        """
        start_time = time.time()

        # ---------------------------------------------------------------------
        # [전략 1: 최우선] 윈도우 핸들(HWND) 직통 UIA 수집 (새로고침 0%, 깜빡임 0%)
        # ---------------------------------------------------------------------
        if HAS_UIA and (hwnd > 0 or window_title):
            try:
                with uia.UIAutomationInitializerInThread():
                    target_ctrl = None
                    if hwnd > 0:
                        try:
                            target_ctrl = uia.ControlFromHandle(hwnd)
                        except Exception:
                            target_ctrl = None

                    if target_ctrl is None and window_title:
                        clean_title = window_title.replace("[웹]", "").replace("[앱]", "").replace("[창]", "").strip()
                        target_ctrl = uia.WindowControl(searchDepth=2, SubName=clean_title)

                    if target_ctrl and target_ctrl.Exists(maxSearchSeconds=1):
                        catalog = cls._walk_uia_controls(target_ctrl)
                        total_count = sum(len(v) for v in catalog.values())
                        if total_count > 0:
                            elapsed = round(time.time() - start_time, 2)
                            return {
                                "status": "success",
                                "engine": "윈도우 창 직통 UIA 수집",
                                "url": url or window_title,
                                "title": target_ctrl.Name or window_title,
                                "count": total_count,
                                "catalog": catalog,
                                "elapsed_sec": elapsed
                            }
            except Exception:
                pass

        # ---------------------------------------------------------------------
        # [전략 2] 활성 Playwright 브라우저 페이지 세션 직통 수집 (새로고침 없음)
        # ---------------------------------------------------------------------
        if cls._active_playwright_page is not None:
            try:
                cur_page = cls._active_playwright_page
                extracted = cur_page.evaluate(cls._get_js_extractor())
                elapsed = round(time.time() - start_time, 2)
                return {
                    "status": "success",
                    "engine": "활성 브라우저 직통 수집",
                    "url": extracted.get("url", url),
                    "title": extracted.get("title", ""),
                    "count": extracted.get("totalCount", 0),
                    "catalog": extracted.get("catalog", {}),
                    "elapsed_sec": elapsed
                }
            except Exception:
                pass

        # ---------------------------------------------------------------------
        # [전략 3] URL 기반 지정 브라우저(Chrome/Edge) 안전 수집 (충분한 렌더링 대기)
        # ---------------------------------------------------------------------
        if HAS_PLAYWRIGHT and url:
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "http://" + url
            try:
                with sync_playwright() as p:
                    launch_kwargs = {"headless": True}
                    b_low = (browser_type or "").lower()
                    if "chrome" in b_low:
                        launch_kwargs["channel"] = "chrome"
                    elif "edge" in b_low or "msedge" in b_low:
                        launch_kwargs["channel"] = "msedge"

                    try:
                        browser = p.chromium.launch(**launch_kwargs)
                    except Exception:
                        browser = p.chromium.launch(headless=True)

                    context = browser.new_context(viewport={"width": 1920, "height": 1080})
                    page = context.new_page()

                    page.goto(url, timeout=timeout_sec * 1000)
                    page.wait_for_load_state("domcontentloaded")
                    time.sleep(2.0)  # React/Vue/AG-Grid 동적 렌더링 완료 대기

                    extracted = page.evaluate(cls._get_js_extractor())
                    browser.close()

                    elapsed = round(time.time() - start_time, 2)
                    engine_name = f"{browser_type.upper()} 렌더링 수집" if browser_type else "웹 렌더링 수집"
                    return {
                        "status": "success",
                        "engine": engine_name,
                        "url": extracted.get("url", url),
                        "title": extracted.get("title", ""),
                        "count": extracted.get("totalCount", 0),
                        "catalog": extracted.get("catalog", {}),
                        "elapsed_sec": elapsed
                    }
            except Exception:
                pass


        # ---------------------------------------------------------------------
        # [전략 4] 정적 HTML Fallback
        # ---------------------------------------------------------------------
        if HAS_BS4 and url:
            try:
                headers = {"User-Agent": "Mozilla/5.0"}
                resp = requests.get(url, headers=headers, timeout=timeout_sec)
                soup = BeautifulSoup(resp.text, "html.parser")

                catalog = {"inputs": [], "buttons": [], "selects": [], "checks_radios": [], "grids": [], "links": []}
                for inp in soup.find_all("input")[:50]:
                    t = (inp.get("type") or "text").lower()
                    i = inp.get("id") or ""
                    n = inp.get("name") or ""
                    ph = inp.get("placeholder") or ""
                    if t in ["checkbox", "radio"]:
                        catalog["checks_radios"].append({"label": ph or i or n or "체크", "id": i, "name": n, "type": t, "selector": f"#{i}" if i else f"input[name='{n}']", "playwrightCode": f'page.locator("#{i}").check()' if i else f'page.locator("input[name=\'{n}\']").check()'})
                    else:
                        catalog["inputs"].append({"label": ph or i or n or "입력창", "id": i, "name": n, "placeholder": ph, "type": t, "selector": f"#{i}" if i else f"input[name='{n}']", "playwrightCode": f'page.locator("#{i}").fill("값")' if i else f'page.locator("input[name=\'{n}\']").fill("값")'})

                for btn in soup.find_all(["button", "a"])[:40]:
                    bt = btn.get_text(strip=True)[:30]
                    if btn.name == "button" and bt:
                        catalog["buttons"].append({"text": bt, "id": btn.get("id", ""), "className": btn.get("class", ""), "selector": f"button:has-text('{bt}')", "playwrightCode": f'page.locator("button:has-text(\'{bt}\')").click()'})
                    elif btn.name == "a" and bt and len(bt) >= 2:
                        catalog["links"].append({"text": bt, "selector": f"a:has-text('{bt}')", "playwrightCode": f'page.locator("a:has-text(\'{bt}\')").click()'})

                elapsed = round(time.time() - start_time, 2)
                return {
                    "status": "success",
                    "engine": "HTML 파서 수집",
                    "url": url,
                    "title": soup.title.string if soup.title else "",
                    "count": sum(len(v) for v in catalog.values()),
                    "catalog": catalog,
                    "elapsed_sec": elapsed
                }
            except Exception as ex:
                raise RuntimeError(f"수집 실패: {ex}")

        raise RuntimeError("조작 가능한 컨트롤을 찾을 수 없습니다. 창을 선택하거나 URL을 확인하십시오.")

    @classmethod
    def _walk_uia_controls(cls, win_ctrl) -> Dict[str, List[Dict[str, Any]]]:
        """UIA COM 트리를 순회하여 실시간 화면 컨트롤 전수 분류"""
        catalog = {"inputs": [], "buttons": [], "selects": [], "checks_radios": [], "grids": [], "links": []}
        seen_keys = set()
        count = 0

        for ctrl, depth in uia.WalkControl(win_ctrl, maxDepth=14):
            if count >= 200:
                break
            try:
                ctype = ctrl.ControlTypeName
                name = (ctrl.Name or "").strip()
                auto_id = (ctrl.AutomationId or "").strip()
                cls_name = (ctrl.ClassName or "").strip()
                val_pattern = ctrl.GetPattern(uia.PatternId.ValuePattern)
                cur_val = val_pattern.Value if val_pattern else ""

                key = f"{ctype}_{name}_{auto_id}_{cls_name}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                # 1. 텍스트 입력창
                if ctype in ["EditControl", "DocumentControl"] or "edit" in cls_name.lower():
                    disp = name or auto_id or "입력창"
                    sel = f"#{auto_id}" if auto_id else (f"input[name='{name}']" if name else f"div:has(> label:has-text('{disp}')) input")
                    catalog["inputs"].append({
                        "label": disp,
                        "id": auto_id,
                        "name": name,
                        "placeholder": cur_val,
                        "selector": sel,
                        "playwrightCode": f'page.locator("{sel}").fill("값입력")'
                    })
                    count += 1

                # 2. 버튼
                elif ctype in ["ButtonControl", "MenuItemControl"] or "button" in cls_name.lower() or "btn" in cls_name.lower():
                    if name:
                        sel = f"button:has-text('{name}')"
                        catalog["buttons"].append({
                            "text": name,
                            "id": auto_id,
                            "className": cls_name,
                            "selector": sel,
                            "playwrightCode": f'page.locator("{sel}").click()'
                        })
                        count += 1

                # 3. 체크박스 / 라디오
                elif ctype in ["CheckBoxControl", "RadioButtonControl"]:
                    disp = name or auto_id or "체크박스"
                    sel = f"#{auto_id}" if auto_id else f"input[type='checkbox']"
                    catalog["checks_radios"].append({
                        "label": disp,
                        "id": auto_id,
                        "selector": sel,
                        "playwrightCode": f'page.locator("{sel}").check()'
                    })
                    count += 1

                # 4. 드롭다운 / 콤보박스
                elif ctype in ["ComboBoxControl", "ListControl"]:
                    disp = name or auto_id or "드롭다운"
                    sel = f"select[name='{name}']" if name else (f"#{auto_id}" if auto_id else "select")
                    catalog["selects"].append({
                        "label": disp,
                        "id": auto_id,
                        "selector": sel,
                        "playwrightCode": f'page.locator("{sel}").select_option(label="선택")'
                    })
                    count += 1

                # 5. 그리드 / 테이블
                elif ctype in ["DataGridControl", "TableControl", "ListControl"] or "grid" in cls_name.lower() or "ag-" in cls_name.lower():
                    disp = name or "데이터 그리드"
                    sel = ".ag-row, table tbody tr"
                    catalog["grids"].append({
                        "type": disp,
                        "selector": sel,
                        "playwrightCode": f'page.locator("{sel}").first.dblclick()'
                    })
                    count += 1

                # 6. 하이퍼링크 / 탭
                elif ctype in ["HyperlinkControl", "TabItemControl"] and name and len(name) <= 30:
                    sel = f"a:has-text('{name}')"
                    catalog["links"].append({
                        "text": name,
                        "selector": sel,
                        "playwrightCode": f'page.locator("{sel}").click()'
                    })
                    count += 1

            except Exception:
                continue

        return catalog

    @classmethod
    def _get_js_extractor(cls) -> str:
        return """() => {
            const catalog = { inputs: [], buttons: [], selects: [], checks_radios: [], grids: [], links: [] };
            const elements = document.querySelectorAll('input, button, select, textarea, [role="button"], [role="textbox"], [role="tab"], [role="checkbox"], [role="radio"], a, table, .ag-root, .ag-row, form');
            let count = 0;
            elements.forEach((el) => {
                if (count >= 200) return;
                const tag = el.tagName.toLowerCase();
                if (el.type !== 'file' && el.type !== 'hidden') {
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return;
                }
                const id = el.id ? el.id.trim() : '';
                const name = el.name ? el.name.trim() : '';
                const type = (el.type || '').toLowerCase();
                const placeholder = el.placeholder ? el.placeholder.trim() : '';
                const ariaLabel = el.getAttribute('aria-label') ? el.getAttribute('aria-label').trim() : '';
                const role = el.getAttribute('role') ? el.getAttribute('role').trim() : '';
                const className = typeof el.className === 'string' ? el.className.trim().split(/\\s+/).slice(0, 3).join(' ') : '';
                const rawText = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
                const text = rawText.slice(0, 35);

                let label = '';
                const lbl = el.closest('label') || (id ? document.querySelector(`label[for="${id}"]`) : null) || el.parentElement?.querySelector('label');
                if (lbl) label = lbl.innerText.trim().replace(/\\s+/g, ' ').slice(0, 30);
                if (!label && placeholder) label = placeholder;
                if (!label && ariaLabel) label = ariaLabel;

                if (type === 'checkbox' || type === 'radio' || role === 'checkbox' || role === 'radio') {
                    const disp = label || text || id || '체크박스';
                    const sel = id ? `#${id}` : (name ? `input[name='${name}']` : `input[type='${type}']`);
                    catalog.checks_radios.push({ label: disp, id, name, selector: sel, playwrightCode: `page.locator("${sel}").check()` });
                    count++;
                } else if (tag === 'textarea' || (tag === 'input' && !['submit', 'button', 'reset', 'image', 'checkbox', 'radio'].includes(type))) {
                    const disp = label || placeholder || id || '입력창';
                    let sel = id ? `#${id}` : (name ? `input[name='${name}']` : (placeholder ? `input[placeholder*='${placeholder}']` : (label ? `div:has(> label:has-text('${label}')) input` : 'input[type="text"]')));
                    catalog.inputs.push({ tag, type, label: disp, id, name, placeholder, selector: sel, playwrightCode: `page.locator("${sel}").fill("값입력")` });
                    count++;
                } else if (tag === 'button' || role === 'button' || (tag === 'input' && ['submit', 'button', 'reset'].includes(type))) {
                    const btnText = text || label || ariaLabel || id || '버튼';
                    let sel = (btnText && btnText.length <= 25) ? `button:has-text('${btnText}')` : (id ? `#${id}` : (className ? `.${className.replace(/\\s+/g, '.')}` : 'button'));
                    catalog.buttons.push({ text: btnText, id, className, type, selector: sel, playwrightCode: `page.locator("${sel}").click()` });
                    count++;
                } else if (tag === 'select' || role === 'combobox' || role === 'listbox') {
                    const disp = label || id || '드롭다운';
                    const sel = id ? `#${id}` : (name ? `select[name='${name}']` : 'select');
                    catalog.selects.push({ label: disp, id, name, selector: sel, playwrightCode: `page.locator("${sel}").select_option(label="선택")` });
                    count++;
                } else if (tag === 'table' || el.classList.contains('ag-root')) {
                    const isAg = el.classList.contains('ag-root');
                    const sel = isAg ? '.ag-row' : 'table tbody tr';
                    catalog.grids.push({ type: isAg ? 'AG-Grid' : 'HTML Table', id, selector: sel, playwrightCode: `page.locator("${sel}").first.dblclick()` });
                    count++;
                } else if ((tag === 'a' && text) || role === 'tab') {
                    if (text && text.length >= 2 && text.length <= 30 && !text.includes('function') && !text.includes('var ')) {
                        catalog.links.push({ text, selector: `a:has-text('${text}')`, playwrightCode: `page.locator("a:has-text('${text}')").click()` });
                        count++;
                    }
                }
            });
            return { title: document.title || '', url: window.location.href || '', totalCount: count, catalog };
        }"""

    @classmethod
    def format_catalog_to_text(cls, catalog: Dict[str, List[Dict[str, Any]]]) -> str:
        lines = []
        for cat_name, key in [
            ("입력 필드", "inputs"),
            ("버튼", "buttons"),
            ("드롭다운", "selects"),
            ("체크박스/라디오", "checks_radios"),
            ("그리드/테이블", "grids"),
            ("링크/탭", "links")
        ]:
            items = catalog.get(key, [])
            if items:
                lines.append(f"[{cat_name} - {len(items)}개]")
                for itm in items:
                    name = itm.get("label") or itm.get("text") or itm.get("type") or "요소"
                    sel = itm.get("selector") or ""
                    code = itm.get("playwrightCode") or ""
                    lines.append(f"  • {name} | 셀렉터: `{sel}` | 코드: `{code}`")
                lines.append("")
        return "\n".join(lines)
