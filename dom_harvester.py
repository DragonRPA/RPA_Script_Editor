"""
Universal RPA - Live Interactive DOM Harvester (Active Browser & Visual Discovery)
- 열려있는 활성 브라우저(Active Browser) 우선 탐색 및 로그인 세션 100% 보존
- 일치하는 브라우저가 없을 때만 눈에 보이는 브라우저(headless=False)로 안전 기동
- 모든 UI 객체(입력창, 버튼, 드롭다운, 체크박스, 라디오, 그리드, 링크)를 유형별 구조화된 JSON 데이터로 추출
"""

import os
import sys
import re
import time
from typing import Dict, Any, List, Optional

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


JS_STRUCTURED_OBJECT_EXTRACTOR = """() => {
    const catalog = {
        inputs: [],
        buttons: [],
        selects: [],
        checks_radios: [],
        grids: [],
        links: []
    };

    const elements = document.querySelectorAll('input, button, select, textarea, [role="button"], [role="textbox"], [role="tab"], [role="checkbox"], [role="radio"], a, table, .ag-root, .ag-row, form');
    
    let totalCount = 0;
    elements.forEach((el) => {
        if (totalCount >= 200) return;
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
        const dataField = el.getAttribute('data-field') ? el.getAttribute('data-field').trim() : '';
        const className = typeof el.className === 'string' ? el.className.trim().split(/\\s+/).slice(0, 3).join(' ') : '';
        const rawText = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
        const text = rawText.slice(0, 35);

        // 인접 라벨(Label) 탐색
        let label = '';
        const lbl = el.closest('label') || (id ? document.querySelector(`label[for="${id}"]`) : null) || el.parentElement?.querySelector('label');
        if (lbl) {
            label = lbl.innerText.trim().replace(/\\s+/g, ' ').slice(0, 30);
        }
        if (!label && placeholder) label = placeholder;
        if (!label && ariaLabel) label = ariaLabel;

        // [1] 체크박스 / 라디오
        if (type === 'checkbox' || type === 'radio' || role === 'checkbox' || role === 'radio') {
            const dispName = label || text || id || name || '체크박스';
            const sel = id ? `#${id}` : (name ? `input[name='${name}']` : `input[type='${type}']`);
            catalog.checks_radios.push({
                type: type || 'checkbox',
                label: dispName,
                id: id,
                name: name,
                selector: sel,
                playwrightCode: `page.locator("${sel}").check()`
            });
            totalCount++;
        }
        // [2] 텍스트 입력창 / 텍스트에리어
        else if (tag === 'textarea' || (tag === 'input' && !['submit', 'button', 'reset', 'image', 'checkbox', 'radio'].includes(type))) {
            const dispName = label || placeholder || id || name || '입력창';
            let sel = '';
            if (id) sel = `#${id}`;
            else if (name) sel = `input[name='${name}']`;
            else if (placeholder) sel = `input[placeholder*='${placeholder}']`;
            else if (label) sel = `div:has(> label:has-text('${label}')) input, label:has-text('${label}') + input`;
            else sel = 'input[type="text"]';

            catalog.inputs.push({
                tag: tag,
                type: type || 'text',
                label: dispName,
                id: id,
                name: name,
                placeholder: placeholder,
                selector: sel,
                playwrightCode: `page.locator("${sel}").fill("값입력")`
            });
            totalCount++;
        }
        // [3] 버튼 / 클릭 요소
        else if (tag === 'button' || role === 'button' || (tag === 'input' && ['submit', 'button', 'reset'].includes(type))) {
            const btnText = text || label || ariaLabel || id || '버튼';
            let sel = '';
            if (btnText && btnText.length <= 25) sel = `button:has-text('${btnText}')`;
            else if (id) sel = `#${id}`;
            else if (className) sel = `.${className.replace(/\\s+/g, '.')}`;
            else sel = 'button';

            catalog.buttons.push({
                text: btnText,
                id: id,
                className: className,
                type: type || 'button',
                selector: sel,
                playwrightCode: `page.locator("${sel}").click()`
            });
            totalCount++;
        }
        // [4] 드롭다운 / 콤보박스
        else if (tag === 'select' || role === 'combobox' || role === 'listbox') {
            const dispName = label || id || name || '드롭다운';
            const sel = id ? `#${id}` : (name ? `select[name='${name}']` : 'select');
            catalog.selects.push({
                label: dispName,
                id: id,
                name: name,
                selector: sel,
                playwrightCode: `page.locator("${sel}").select_option(label="선택항목")`
            });
            totalCount++;
        }
        // [5] 테이블 / 데이터 그리드
        else if (tag === 'table' || el.classList.contains('ag-root')) {
            const isAgGrid = el.classList.contains('ag-root');
            const sel = isAgGrid ? '.ag-row' : 'table tbody tr';
            catalog.grids.push({
                type: isAgGrid ? 'AG-Grid (엔터프라이즈 그리드)' : 'HTML Table',
                id: id,
                className: className,
                selector: sel,
                playwrightCode: `page.locator("${sel}").first.dblclick()`
            });
            totalCount++;
        }
        // [6] 네비게이션 링크 / 탭
        else if ((tag === 'a' && text) || role === 'tab') {
            if (text && text.length >= 2 && text.length <= 30 && !text.includes('function') && !text.includes('var ')) {
                catalog.links.push({
                    text: text,
                    role: role || 'link',
                    href: el.getAttribute('href') || '',
                    selector: `a:has-text('${text}')`,
                    playwrightCode: `page.locator("a:has-text('${text}')").click()`
                });
                totalCount++;
            }
        }
    });

    return {
        title: document.title || '',
        url: window.location.href || '',
        totalCount: totalCount,
        catalog: catalog
    };
}"""


class DOMHarvester:
    """범용 실시간 UI 객체 전수 수집 매니저"""

    _active_playwright_page = None  # 활성 브라우저 페이지 레퍼런스 공유 가능

    @classmethod
    def set_active_page(cls, page):
        """스튜디오가 현재 띄워둔 브라우저 활성 페이지 등록"""
        cls._active_playwright_page = page

    @classmethod
    def harvest_live_dom(cls, url: str, timeout_sec: int = 15) -> Dict[str, Any]:
        """
        1. 이미 열려있는 활성 브라우저가 동일 URL인지 우선 확인 ➔ 0.01초 만에 로그인 세션 그대로 추출!
        2. 없을 경우 사용자가 직접 눈으로 확인할 수 있는 가시 브라우저(headless=False)로 띄워 안전하게 추출!
        """
        if not url:
            raise ValueError("수집할 URL이 비어 있습니다.")

        if not url.startswith("http://") and not url.startswith("https://"):
            url = "http://" + url

        start_time = time.time()
        clean_target_url = url.split("?")[0].rstrip("/")

        # ---------------------------------------------------------------------
        # [전략 1] 현재 열려있는 스튜디오 브라우저 세션 직접 연결 (로그인 세션 100% 보존)
        # ---------------------------------------------------------------------
        if cls._active_playwright_page is not None:
            try:
                cur_page = cls._active_playwright_page
                cur_url = (cur_page.url or "").split("?")[0].rstrip("/")
                if cur_url == clean_target_url or clean_target_url in cur_url:
                    # 동일한 URL을 보고 있는 열려진 탭 발견!
                    extracted = cur_page.evaluate(JS_STRUCTURED_OBJECT_EXTRACTOR)
                    elapsed = time.time() - start_time
                    return {
                        "status": "success",
                        "engine": "⚡ 활성 브라우저 직접 연결 (로그인 세션 유지)",
                        "url": extracted.get("url", url),
                        "title": extracted.get("title", ""),
                        "count": extracted.get("totalCount", 0),
                        "catalog": extracted.get("catalog", {}),
                        "elapsed_sec": round(elapsed, 2)
                    }
            except Exception:
                pass

        # ---------------------------------------------------------------------
        # [전략 2] 없으면 가시 브라우저(headless=False)를 띄워 투명하게 추출
        # ---------------------------------------------------------------------
        if HAS_PLAYWRIGHT:
            try:
                with sync_playwright() as p:
                    # 백그라운드가 아닌 눈에 보이는 브라우저로 띄워 신뢰성 보장
                    browser = p.chromium.launch(headless=False, args=["--start-maximized"])
                    context = browser.new_context(no_viewport=True)
                    page = context.new_page()

                    page.goto(url, timeout=timeout_sec * 1000)
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_timeout(1000)  # React/Vue SPA 렌더링 대기

                    extracted = page.evaluate(JS_STRUCTURED_OBJECT_EXTRACTOR)
                    browser.close()

                    elapsed = time.time() - start_time
                    return {
                        "status": "success",
                        "engine": "🌐 가시 브라우저 실시간 렌더링 추출",
                        "url": extracted.get("url", url),
                        "title": extracted.get("title", ""),
                        "count": extracted.get("totalCount", 0),
                        "catalog": extracted.get("catalog", {}),
                        "elapsed_sec": round(elapsed, 2)
                    }
            except Exception as ex:
                pass

        # ---------------------------------------------------------------------
        # [전략 3] Fallback (Static HTML Parser)
        # ---------------------------------------------------------------------
        if HAS_BS4:
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

                elapsed = time.time() - start_time
                return {
                    "status": "success",
                    "engine": "Static HTML Parser (Fallback)",
                    "url": url,
                    "title": soup.title.string if soup.title else "",
                    "count": sum(len(v) for v in catalog.values()),
                    "catalog": catalog,
                    "elapsed_sec": round(elapsed, 2)
                }
            except Exception as ex:
                raise RuntimeError(f"DOM 수집 실패: {ex}")

        raise RuntimeError("브라우저 자동화 모듈을 사용할 수 없습니다.")

    @classmethod
    def format_catalog_to_text(cls, catalog: Dict[str, List[Dict[str, Any]]]) -> str:
        """AI에게 전달할 전체 객체 인벤토리 텍스트 변환"""
        lines = []
        for cat_name, key in [
            ("📝 입력 필드 (Inputs)", "inputs"),
            ("🔘 버튼 및 클릭 요소 (Buttons)", "buttons"),
            ("🔽 드롭다운 / 콤보박스 (Selects)", "selects"),
            ("☑️ 체크박스 / 라디오 (Checks & Radios)", "checks_radios"),
            ("📊 테이블 / 데이터 그리드 (Grids)", "grids"),
            ("📑 네비게이션 링크 / 탭 (Links)", "links")
        ]:
            items = catalog.get(key, [])
            if items:
                lines.append(f"[{cat_name} - {len(items)}개]")
                for itm in items:
                    name = itm.get("label") or itm.get("text") or itm.get("type") or "요소"
                    sel = itm.get("selector") or ""
                    code = itm.get("playwrightCode") or ""
                    lines.append(f"  • {name} ➔ 셀렉터: `{sel}` | 코드: `{code}`")
                lines.append("")
        return "\n".join(lines)
