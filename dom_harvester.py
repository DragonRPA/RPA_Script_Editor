"""
Universal RPA - Live Interactive DOM & Window UI Harvester
- 웹 URL이 있을 때 실제 브라우저 엔진(Playwright/CDP)으로 100% 무결점 HTML DOM 추출
- 데스크톱 네이티브 앱 창일 때 윈도우 UIA COM 트리 추출
- 3~4단계 상위 조상 텍스트 계층(Hierarchy) 및 실제 outerHTML 조각 전수 보존
- [HTML 보기] 및 계층 텍스트 상세 노출 지원
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
    """실시간 UI/DOM 객체 수집기 (HTML 조각 보존 및 3~4단계 계층 경로 매핑)"""

    _active_playwright_page = None

    @classmethod
    def set_active_page(cls, page):
        cls._active_playwright_page = page

    @classmethod
    def harvest_live_dom(cls, url: str = "", hwnd: int = 0, window_title: str = "", browser_type: str = "chrome", timeout_sec: int = 15) -> Dict[str, Any]:
        """
        1. 웹 URL이 입력되었거나 웹 브라우저 창인 경우: 실제 브라우저 엔진으로 진정한 HTML DOM 및 <select>, input-group, outerHTML 추출
        2. 데스크톱 네이티브 앱(ERP, Excel 등)인 경우: Windows UIA COM 트리로 네이티브 컨트롤 추출
        """
        start_time = time.time()
        is_web_target = bool(url) or ("[웹]" in window_title) or any(b in window_title.lower() for b in ["chrome", "edge", "whale", "firefox"])

        # ---------------------------------------------------------------------
        # [전략 1: 웹 최우선] 활성 Playwright 페이지 세션 직통 수집
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
        # [전략 2: 웹 타겟] 지정 브라우저 엔진(Chrome/Edge) 실제 DOM 추출 (Select, HTML 전수 파싱)
        # ---------------------------------------------------------------------
        if HAS_PLAYWRIGHT and url:
            target_u = url
            if not target_u.startswith("http://") and not target_u.startswith("https://"):
                target_u = "http://" + target_u
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

                    page.goto(target_u, timeout=timeout_sec * 1000)
                    page.wait_for_load_state("domcontentloaded")
                    time.sleep(2.0)  # React/Vue/AG-Grid 동적 렌더링 완료 대기

                    extracted = page.evaluate(cls._get_js_extractor())
                    browser.close()

                    elapsed = round(time.time() - start_time, 2)
                    b_name = browser_type.upper() if browser_type else "웹"
                    return {
                        "status": "success",
                        "engine": f"{b_name} DOM 수집",
                        "url": extracted.get("url", url),
                        "title": extracted.get("title", ""),
                        "count": extracted.get("totalCount", 0),
                        "catalog": extracted.get("catalog", {}),
                        "elapsed_sec": elapsed
                    }
            except Exception:
                pass

        # ---------------------------------------------------------------------
        # [전략 3: 데스크톱 앱 / Fallback] Windows UIA COM 트리 수집
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
                                "engine": "윈도우 UIA 수집",
                                "url": url or window_title,
                                "title": target_ctrl.Name or window_title,
                                "count": total_count,
                                "catalog": catalog,
                                "elapsed_sec": elapsed
                            }
            except Exception:
                pass

        # ---------------------------------------------------------------------
        # [전략 4: HTML 정적 파서 Fallback]
        # ---------------------------------------------------------------------
        if HAS_BS4 and url:
            try:
                headers = {"User-Agent": "Mozilla/5.0"}
                target_u = url if url.startswith("http") else f"http://{url}"
                resp = requests.get(target_u, headers=headers, timeout=timeout_sec)
                soup = BeautifulSoup(resp.text, "html.parser")

                catalog = {"inputs": [], "buttons": [], "selects": [], "checks_radios": [], "grids": [], "links": []}

                # 1. Inputs & Selects
                for el in soup.find_all(["input", "select", "textarea"])[:80]:
                    tag = el.name
                    t = (el.get("type") or "text").lower() if tag == "input" else tag
                    i = el.get("id") or ""
                    n = el.get("name") or ""
                    ph = el.get("placeholder") or ""
                    raw_html = str(el.parent if el.parent and el.parent.name == 'div' else el)[:300]

                    # 3~4단계 상위 조상 텍스트 계층 탐색
                    ancestor_texts = []
                    curr = el.parent
                    depth = 0
                    while curr and depth < 5 and curr.name not in ['body', 'html']:
                        lbl_node = curr.find(class_=re.compile(r"input-group-text|form-label|label|title")) or curr.find(['label', 'th', 'dt', 'legend', 'span'])
                        if lbl_node and lbl_node != el:
                            txt = lbl_node.get_text(strip=True)
                            if txt and len(txt) <= 30 and txt not in ["선택", "입력", "전체", "조회"] and txt not in ancestor_texts:
                                ancestor_texts.append(txt)
                        curr = curr.parent
                        depth += 1

                    ig_text = ancestor_texts[0] if ancestor_texts else ""
                    disp = ig_text or ph or i or n or ("드롭다운" if tag == "select" else "입력창")
                    path_str = " > ".join(ancestor_texts[:3]) if ancestor_texts else tag

                    if tag == "select":
                        sel = f"#{i}" if i else (f"select[name='{n}']" if n else (f"div.input-group:has-text('{ig_text}') select" if ig_text else "select"))
                        catalog["selects"].append({"label": disp, "id": i, "name": n, "path": path_str, "html": raw_html, "selector": sel, "playwrightCode": f'page.locator("{sel}").select_option(label="선택")'})
                    elif t in ["checkbox", "radio"]:
                        sel = f"#{i}" if i else (f"input[name='{n}']" if n else (f"div.input-group:has-text('{ig_text}') input" if ig_text else f"input[type='{t}']"))
                        catalog["checks_radios"].append({"label": disp, "id": i, "name": n, "type": t, "path": path_str, "html": raw_html, "selector": sel, "playwrightCode": f'page.locator("{sel}").check()'})
                    else:
                        sel = f"#{i}" if i else (f"input[name='{n}']" if n else (f"div.input-group:has-text('{ig_text}') input" if ig_text else (f"input[placeholder*='{ph}']" if ph else "input[type='text']")))
                        catalog["inputs"].append({"label": disp, "id": i, "name": n, "placeholder": ph, "type": t, "path": path_str, "html": raw_html, "selector": sel, "playwrightCode": f'page.locator("{sel}").fill("값")'})

                # 2. Buttons
                for btn in soup.find_all(["button", "a"])[:40]:
                    bt = btn.get_text(strip=True)[:30]
                    raw_html = str(btn)[:300]
                    if btn.name == "button" and bt:
                        catalog["buttons"].append({"text": bt, "id": btn.get("id", ""), "className": btn.get("class", ""), "path": bt, "html": raw_html, "selector": f"button:has-text('{bt}')", "playwrightCode": f'page.locator("button:has-text(\'{bt}\')").click()'})
                    elif btn.name == "a" and bt and len(bt) >= 2:
                        catalog["links"].append({"text": bt, "path": bt, "html": raw_html, "selector": f"a:has-text('{bt}')", "playwrightCode": f'page.locator("a:has-text(\'{bt}\')").click()'})

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

        raise RuntimeError("조작 가능한 컨트롤을 찾을 수 없습니다. URL을 입력하거나 대상 창을 확인하십시오.")

    @classmethod
    def _walk_uia_controls(cls, win_ctrl) -> Dict[str, List[Dict[str, Any]]]:
        """UIA COM 트리를 순회하여 화면 컨트롤 전수 분류 및 인접 텍스트 라벨 매핑"""
        catalog = {"inputs": [], "buttons": [], "selects": [], "checks_radios": [], "grids": [], "links": []}
        seen_keys = set()
        count = 0
        last_seen_texts = []

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

                if ctype == "TextControl" and name and len(name) <= 25 and not name.startswith("http"):
                    if name not in ["선택", "입력", "전체", "조회"]:
                        last_seen_texts.append(name)
                        if len(last_seen_texts) > 3:
                            last_seen_texts.pop(0)

                key = f"{ctype}_{name}_{auto_id}_{cls_name}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                recent_txt = last_seen_texts[-1] if last_seen_texts else ""
                path_str = " > ".join(last_seen_texts) if last_seen_texts else ctype

                # 1. 텍스트 입력창
                if ctype in ["EditControl", "DocumentControl"] or "edit" in cls_name.lower():
                    disp = (name if (name and name not in ["입력", "입력창"]) else "") or recent_txt or auto_id or "입력창"
                    sel = f"#{auto_id}" if auto_id else (f"input[name='{name}']" if (name and name not in ["입력", "입력창"]) else (f"div.input-group:has-text('{recent_txt}') input" if recent_txt else "input[type='text']"))
                    catalog["inputs"].append({
                        "label": disp,
                        "id": auto_id,
                        "name": name,
                        "placeholder": cur_val,
                        "path": path_str,
                        "html": f"<{ctype} Name='{name}' AutoId='{auto_id}' Class='{cls_name}'>",
                        "selector": sel,
                        "playwrightCode": f'page.locator("{sel}").fill("값입력")'
                    })
                    count += 1

                # 2. 버튼
                elif ctype in ["ButtonControl", "MenuItemControl"] or "button" in cls_name.lower() or "btn" in cls_name.lower():
                    btn_label = name or recent_txt or "버튼"
                    if btn_label and len(btn_label) <= 25:
                        sel = f"button:has-text('{btn_label}')"
                        catalog["buttons"].append({
                            "text": btn_label,
                            "id": auto_id,
                            "className": cls_name,
                            "path": path_str,
                            "html": f"<{ctype} Name='{name}' AutoId='{auto_id}' Class='{cls_name}'>",
                            "selector": sel,
                            "playwrightCode": f'page.locator("{sel}").click()'
                        })
                        count += 1

                # 3. 체크박스 / 라디오
                elif ctype in ["CheckBoxControl", "RadioButtonControl"]:
                    disp = name or recent_txt or auto_id or "체크박스"
                    sel = f"#{auto_id}" if auto_id else (f"div:has-text('{recent_txt}') input" if recent_txt else f"input[type='checkbox']")
                    catalog["checks_radios"].append({
                        "label": disp,
                        "id": auto_id,
                        "path": path_str,
                        "html": f"<{ctype} Name='{name}' AutoId='{auto_id}'>",
                        "selector": sel,
                        "playwrightCode": f'page.locator("{sel}").check()'
                    })
                    count += 1

                # 4. 드롭다운 / 콤보박스 / Select
                elif ctype in ["ComboBoxControl", "ListControl"] or "select" in cls_name.lower():
                    disp = (name if (name and name not in ["선택", "드롭다운"]) else "") or recent_txt or auto_id or "드롭다운"
                    sel = f"select[name='{name}']" if name else (f"#{auto_id}" if auto_id else (f"div.input-group:has-text('{recent_txt}') select" if recent_txt else "select"))
                    catalog["selects"].append({
                        "label": disp,
                        "id": auto_id,
                        "path": path_str,
                        "html": f"<{ctype} Name='{name}' AutoId='{auto_id}'>",
                        "selector": sel,
                        "playwrightCode": f'page.locator("{sel}").select_option(label="선택")'
                    })
                    count += 1

                # 5. 그리드 / 테이블
                elif ctype in ["DataGridControl", "TableControl"] or "grid" in cls_name.lower() or "ag-" in cls_name.lower():
                    disp = name or recent_txt or "데이터 그리드"
                    sel = ".ag-row, table tbody tr"
                    catalog["grids"].append({
                        "type": disp,
                        "path": path_str,
                        "html": f"<{ctype} Name='{name}'>",
                        "selector": sel,
                        "playwrightCode": f'page.locator("{sel}").first.dblclick()'
                    })
                    count += 1

                # 6. 하이퍼링크 / 탭
                elif ctype in ["HyperlinkControl", "TabItemControl"] and name and len(name) <= 30:
                    sel = f"a:has-text('{name}')"
                    catalog["links"].append({
                        "text": name,
                        "path": path_str,
                        "html": f"<{ctype} Name='{name}'>",
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
            const elements = document.querySelectorAll('input, button, select, textarea, [role="button"], [role="textbox"], [role="tab"], [role="checkbox"], [role="radio"], [role="combobox"], [role="listbox"], a, table, .ag-root, .ag-row, form, .form-select');
            let count = 0;

            const GENERIC_WORDS = new Set(['선택', '입력', 'select', 'input', 'form-select', 'form-control', '전체', 'default', 'custom-select', '조회']);

            function cleanText(t) {
                if (!t) return '';
                return t.trim().replace(/\\s+/g, ' ');
            }

            function getElementContext(el, id) {
                const ancestors = [];
                let primaryLabel = '';

                // 1. 바로 앞의 형제 span.input-group-text 또는 .form-label (최우선!)
                let prev = el.previousElementSibling;
                while (prev) {
                    const t = cleanText(prev.innerText || prev.textContent || '');
                    if (t && t.length <= 30 && !GENERIC_WORDS.has(t.toLowerCase()) && !t.includes('{') && !t.includes('(')) {
                        primaryLabel = t;
                        ancestors.push(t);
                        break;
                    }
                    prev = prev.previousElementSibling;
                }

                // 2. 부모 .input-group, .form-group 내부
                const inputGroup = el.closest('.input-group, .form-group, .form-floating, .form-item, .ant-form-item, .field, .col, .d-flex');
                if (inputGroup) {
                    const igText = inputGroup.querySelector('.input-group-text, .form-label, label, .ant-form-item-label, .v-label, span.title, dt, span.prefix, th, span');
                    if (igText && igText !== el && !igText.contains(el)) {
                        const t = cleanText(igText.innerText || igText.textContent || '');
                        if (t && t.length <= 30 && !GENERIC_WORDS.has(t.toLowerCase())) {
                            if (!primaryLabel) primaryLabel = t;
                            if (!ancestors.includes(t)) ancestors.push(t);
                        }
                    }
                }

                // 3. 명시적 <label for="id"> 또는 직계 <label>
                if (id) {
                    const forLbl = document.querySelector(`label[for="${id}"]`);
                    if (forLbl) {
                        const t = cleanText(forLbl.innerText);
                        if (t && !GENERIC_WORDS.has(t.toLowerCase())) {
                            if (!primaryLabel) primaryLabel = t;
                            if (!ancestors.includes(t)) ancestors.push(t);
                        }
                    }
                }
                const wrapLbl = el.closest('label');
                if (wrapLbl) {
                    const t = cleanText(wrapLbl.innerText);
                    if (t && !GENERIC_WORDS.has(t.toLowerCase())) {
                        if (!primaryLabel) primaryLabel = t;
                        if (!ancestors.includes(t)) ancestors.push(t);
                    }
                }

                // 4. 상위 조상 계층(Upward Ancestor) 3~4단계 순회
                let current = el.parentElement;
                let depth = 0;
                while (current && depth < 5 && current.tagName.toLowerCase() !== 'body' && current.tagName.toLowerCase() !== 'html') {
                    const candidate = current.querySelector('.input-group-text, .form-label, label, th, dt, legend, h5, h6, .title, strong, b');
                    if (candidate && candidate !== el && !candidate.contains(el)) {
                        const t = cleanText(candidate.innerText);
                        if (t && t.length <= 30 && !GENERIC_WORDS.has(t.toLowerCase()) && !t.includes('{') && !t.includes('(')) {
                            if (!ancestors.includes(t)) ancestors.push(t);
                        }
                    }
                    current = current.parentElement;
                    depth++;
                }

                // 5. HTML5 속성
                const ph = el.getAttribute('placeholder') || el.getAttribute('title') || el.getAttribute('data-label') || el.getAttribute('data-title');
                if (ph) {
                    const p = cleanText(ph);
                    if (p && !GENERIC_WORDS.has(p.toLowerCase())) {
                        if (!primaryLabel) primaryLabel = p;
                        if (!ancestors.includes(p)) ancestors.push(p);
                    }
                }

                // Outer HTML 조각 (input-group 부모 포함 최대 280자)
                const container = el.closest('.input-group, .form-group') || el;
                const rawHtml = container.outerHTML ? container.outerHTML.slice(0, 300) : '';

                return {
                    label: primaryLabel || (ancestors.length > 0 ? ancestors[0] : ''),
                    path: ancestors.length > 0 ? ancestors.slice(0, 3).join(' > ') : '',
                    html: rawHtml
                };
            }

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
                const className = typeof el.className === 'string' ? el.className.trim().split(/\\s+/).slice(0, 3).join(' ') : '';
                const rawText = cleanText(el.innerText || el.textContent || '');
                const text = rawText.slice(0, 35);

                const ctx = getElementContext(el, id);
                const visibleLabel = ctx.label;
                const pathStr = ctx.path || visibleLabel || tag;
                const elemHtml = ctx.html || el.outerHTML?.slice(0, 250) || '';

                const isSelect = tag === 'select' || el.classList.contains('form-select') || el.getAttribute('role') === 'combobox' || el.getAttribute('role') === 'listbox';

                if (isSelect) {
                    const disp = visibleLabel || id || name || '드롭다운';
                    let sel = id ? `#${id}` : (name ? `select[name='${name}']` : (visibleLabel ? `div.input-group:has-text('${visibleLabel}') select, select:has-text('${visibleLabel}'), select` : 'select'));
                    catalog.selects.push({ label: disp, id, name, path: pathStr, html: elemHtml, selector: sel, playwrightCode: `page.locator("${sel}").select_option(label="선택")` });
                    count++;
                } else if (type === 'checkbox' || type === 'radio' || el.getAttribute('role') === 'checkbox' || el.getAttribute('role') === 'radio') {
                    const disp = visibleLabel || text || id || name || '체크박스';
                    let sel = id ? `#${id}` : (name ? `input[name='${name}']` : (visibleLabel ? `div.input-group:has-text('${visibleLabel}') input, label:has-text('${visibleLabel}') input` : `input[type='${type}']`));
                    catalog.checks_radios.push({ label: disp, id, name, type, path: pathStr, html: elemHtml, selector: sel, playwrightCode: `page.locator("${sel}").check()` });
                    count++;
                } else if (tag === 'textarea' || (tag === 'input' && !['submit', 'button', 'reset', 'image', 'checkbox', 'radio'].includes(type))) {
                    const disp = visibleLabel || placeholder || id || name || '입력창';
                    let sel = '';
                    if (id) {
                        sel = `#${id}`;
                    } else if (name) {
                        sel = `input[name='${name}']`;
                    } else if (visibleLabel) {
                        sel = `div.input-group:has-text('${visibleLabel}') input, div:has(> .input-group-text:has-text('${visibleLabel}')) input`;
                    } else if (placeholder) {
                        sel = `input[placeholder*='${placeholder}']`;
                    } else {
                        sel = className ? `input.${className.replace(/\\s+/g, '.')}` : 'input[type="text"]';
                    }
                    catalog.inputs.push({ tag, type, label: disp, id, name, placeholder, path: pathStr, html: elemHtml, selector: sel, playwrightCode: `page.locator("${sel}").fill("값입력")` });
                    count++;
                } else if (tag === 'button' || el.getAttribute('role') === 'button' || (tag === 'input' && ['submit', 'button', 'reset'].includes(type))) {
                    const btnText = text || visibleLabel || id || '버튼';
                    let sel = (btnText && btnText.length <= 25) ? `button:has-text('${btnText}')` : (id ? `#${id}` : (className ? `.${className.replace(/\\s+/g, '.')}` : 'button'));
                    catalog.buttons.push({ text: btnText, id, className, type, path: pathStr, html: elemHtml, selector: sel, playwrightCode: `page.locator("${sel}").click()` });
                    count++;
                } else if (tag === 'table' || el.classList.contains('ag-root')) {
                    const isAg = el.classList.contains('ag-root');
                    const sel = isAg ? '.ag-row' : 'table tbody tr';
                    const disp = visibleLabel || (isAg ? 'AG-Grid 데이터 그리드' : 'HTML 테이블');
                    catalog.grids.push({ type: disp, id, path: pathStr, html: elemHtml, selector: sel, playwrightCode: `page.locator("${sel}").first.dblclick()` });
                    count++;
                } else if ((tag === 'a' && text) || el.getAttribute('role') === 'tab') {
                    if (text && text.length >= 2 && text.length <= 30 && !text.includes('function') && !text.includes('var ')) {
                        catalog.links.push({ text, path: text, html: elemHtml, selector: `a:has-text('${text}')`, playwrightCode: `page.locator("a:has-text('${text}')").click()` });
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
            ("드롭다운(Select)", "selects"),
            ("버튼", "buttons"),
            ("체크박스/라디오", "checks_radios"),
            ("그리드/테이블", "grids"),
            ("링크/탭", "links")
        ]:
            items = catalog.get(key, [])
            if items:
                lines.append(f"[{cat_name} - {len(items)}개]")
                for itm in items:
                    name = itm.get("label") or itm.get("text") or itm.get("type") or "요소"
                    path = itm.get("path") or ""
                    sel = itm.get("selector") or ""
                    code = itm.get("playwrightCode") or ""
                    path_hint = f" (경로: {path})" if path and path != name else ""
                    lines.append(f"  • {name}{path_hint} | 셀렉터: `{sel}` | 코드: `{code}`")
                lines.append("")
        return "\n".join(lines)
