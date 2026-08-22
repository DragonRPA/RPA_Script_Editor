"""
Universal RPA - Live Interactive DOM Harvester (Full Object Inventory Edition)
웹페이지 내의 모든 조작 가능한 UI 컨트롤(입력창, 버튼, 드롭다운, 체크박스, 라디오, 테이블, 링크 등)을
유형별(Category)로 전수 수집하여 구조화된 부품 카탈로그로 추출하는 범용 RPA 인스펙터
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


JS_FULL_OBJECT_CATALOG_EXTRACTOR = """() => {
    const catalog = {
        inputs: [],
        buttons: [],
        selects: [],
        checks_radios: [],
        grids: [],
        links: []
    };

    // 1. 모든 인터랙티브 요소 순회
    const elements = document.querySelectorAll('input, button, select, textarea, [role="button"], [role="textbox"], [role="tab"], [role="checkbox"], a, table, .ag-root, form');
    
    let totalCount = 0;
    elements.forEach((el) => {
        if (totalCount >= 150) return;
        const tag = el.tagName.toLowerCase();
        
        // 숨김 요소 스킵 (단 type=file/hidden 제외)
        if (el.type !== 'file' && el.type !== 'hidden') {
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return;
        }

        const id = el.id ? el.id : '';
        const name = el.name ? el.name : '';
        const type = (el.type || '').toLowerCase();
        const placeholder = el.placeholder ? el.placeholder : '';
        const ariaLabel = el.getAttribute('aria-label') || '';
        const role = el.getAttribute('role') || '';
        const dataField = el.getAttribute('data-field') || '';
        const className = typeof el.className === 'string' ? el.className.trim().split(/\\s+/).slice(0, 3).join(' ') : '';
        const text = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 35);

        // 인접 라벨(Label) 텍스트 탐색
        let label = '';
        const lbl = el.closest('label') || (id ? document.querySelector(`label[for="${id}"]`) : null) || el.parentElement.querySelector('label');
        if (lbl) {
            label = lbl.innerText.trim().replace(/\\s+/g, ' ').slice(0, 25);
        }
        if (!label && placeholder) label = placeholder;
        if (!label && ariaLabel) label = ariaLabel;

        // [A] 체크박스 / 라디오
        if (type === 'checkbox' || type === 'radio' || role === 'checkbox' || role === 'radio') {
            catalog.checks_radios.push({
                type: type || 'checkbox',
                label: label || text || id || name || '체크박스/라디오',
                id: id,
                name: name,
                selector: id ? `#${id}` : (name ? `input[name='${name}']` : '')
            });
            totalCount++;
        }
        // [B] 일반 텍스트 입력창 / 텍스트에리어
        else if (tag === 'textarea' || tag === 'input' && !['submit', 'button', 'reset', 'image', 'checkbox', 'radio'].includes(type)) {
            catalog.inputs.push({
                tag: tag,
                type: type || 'text',
                label: label || id || name || '입력창',
                id: id,
                name: name,
                placeholder: placeholder,
                selector: id ? `#${id}` : (name ? `input[name='${name}']` : (placeholder ? `input[placeholder*='${placeholder}']` : ''))
            });
            totalCount++;
        }
        // [C] 버튼 / 제출
        else if (tag === 'button' || role === 'button' || (tag === 'input' && ['submit', 'button', 'reset'].includes(type))) {
            const btnText = text || label || ariaLabel || id || '버튼';
            catalog.buttons.push({
                text: btnText,
                id: id,
                className: className,
                type: type || 'button',
                selector: id ? `#${id}` : (btnText ? `button:has-text('${btnText}')` : (className ? `.${className.replace(/\\s+/g, '.')}` : ''))
            });
            totalCount++;
        }
        // [D] 드롭다운 / 콤보박스
        else if (tag === 'select' || role === 'combobox' || role === 'listbox') {
            catalog.selects.push({
                label: label || id || name || '드롭다운',
                id: id,
                name: name,
                selector: id ? `#${id}` : (name ? `select[name='${name}']` : '')
            });
            totalCount++;
        }
        // [E] 테이블 / 데이터 그리드
        else if (tag === 'table' || el.classList.contains('ag-root')) {
            const isAgGrid = el.classList.contains('ag-root');
            catalog.grids.push({
                type: isAgGrid ? 'AG-Grid' : 'HTML Table',
                id: id,
                className: className,
                selector: isAgGrid ? '.ag-row' : 'table tbody tr'
            });
            totalCount++;
        }
        // [F] 네비게이션 링크 / 탭
        else if ((tag === 'a' && text) || role === 'tab') {
            if (text && text.length >= 2 && text.length <= 25) {
                catalog.links.push({
                    text: text,
                    role: role || 'link',
                    href: el.getAttribute('href') || '',
                    selector: `a:has-text('${text}')`
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
    """범용 실시간 UI 객체 전수 수집 및 인스펙터 매니저"""

    @classmethod
    def harvest_live_dom(cls, url: str, timeout_sec: int = 12) -> Dict[str, Any]:
        """
        대상 URL에 접속하여 페이지 내 모든 조작 가능한 UI 컨트롤을 유형별로 전수 추출
        """
        if not url:
            raise ValueError("수집할 URL이 비어 있습니다.")

        if not url.startswith("http://") and not url.startswith("https://"):
            url = "http://" + url

        start_time = time.time()

        if HAS_PLAYWRIGHT:
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        viewport={"width": 1920, "height": 1080},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    )
                    page = context.new_page()
                    page.goto(url, timeout=timeout_sec * 1000)
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_timeout(800)

                    extracted = page.evaluate(JS_FULL_OBJECT_CATALOG_EXTRACTOR)
                    browser.close()

                    elapsed = time.time() - start_time
                    formatted_catalog = cls._format_catalog_summary(extracted.get("catalog", {}))

                    return {
                        "status": "success",
                        "engine": "Playwright Universal Inspector",
                        "url": extracted.get("url", url),
                        "title": extracted.get("title", ""),
                        "count": extracted.get("totalCount", 0),
                        "catalog": extracted.get("catalog", {}),
                        "formatted_summary": formatted_catalog,
                        "elapsed_sec": round(elapsed, 2)
                    }
            except Exception as ex:
                pass

        # Fallback to BeautifulSoup
        if HAS_BS4:
            try:
                headers = {"User-Agent": "Mozilla/5.0"}
                resp = requests.get(url, headers=headers, timeout=timeout_sec)
                soup = BeautifulSoup(resp.text, "html.parser")

                catalog = {"inputs": [], "buttons": [], "selects": [], "checks_radios": [], "grids": [], "links": []}
                for inp in soup.find_all("input")[:40]:
                    t = (inp.get("type") or "text").lower()
                    i = inp.get("id") or ""
                    n = inp.get("name") or ""
                    ph = inp.get("placeholder") or ""
                    if t in ["checkbox", "radio"]:
                        catalog["checks_radios"].append({"label": ph or i or n or "체크", "id": i, "name": n, "type": t, "selector": f"#{i}" if i else f"input[name='{n}']"})
                    else:
                        catalog["inputs"].append({"label": ph or i or n or "입력창", "id": i, "name": n, "placeholder": ph, "type": t, "selector": f"#{i}" if i else f"input[name='{n}']"})

                for btn in soup.find_all(["button", "a"])[:30]:
                    bt = btn.get_text(strip=True)[:25]
                    if btn.name == "button" and bt:
                        catalog["buttons"].append({"text": bt, "id": btn.get("id", ""), "className": btn.get("class", ""), "selector": f"button:has-text('{bt}')"})
                    elif btn.name == "a" and bt and len(bt) >= 2:
                        catalog["links"].append({"text": bt, "selector": f"a:has-text('{bt}')"})

                formatted_catalog = cls._format_catalog_summary(catalog)
                elapsed = time.time() - start_time
                return {
                    "status": "success",
                    "engine": "Static HTML Universal Inspector (Fallback)",
                    "url": url,
                    "title": soup.title.string if soup.title else "",
                    "count": sum(len(v) for v in catalog.values()),
                    "catalog": catalog,
                    "formatted_summary": formatted_catalog,
                    "elapsed_sec": round(elapsed, 2)
                }
            except Exception as ex:
                raise RuntimeError(f"DOM 수집 실패: {ex}")

        raise RuntimeError("Playwright 또는 BeautifulSoup 모듈을 사용할 수 없습니다.")

    @classmethod
    def _format_catalog_summary(cls, catalog: Dict[str, List[Dict[str, Any]]]) -> str:
        """UI 및 AI가 한눈에 볼 수 있는 깔끔한 범용 조작 객체 인벤토리 포맷팅"""
        lines = []

        inputs = catalog.get("inputs", [])
        if inputs:
            lines.append(f"📝 텍스트 입력창 (Inputs: {len(inputs)}개)")
            for itm in inputs:
                lbl = itm.get("label", "")
                i = itm.get("id", "")
                ph = itm.get("placeholder", "")
                sel = itm.get("selector", "")
                lines.append(f"  • [{lbl}] {f'id=\"{i}\"' if i else ''} {f'placeholder=\"{ph}\"' if ph else ''} ➔ {sel}")

        buttons = catalog.get("buttons", [])
        if buttons:
            lines.append(f"\n🔘 버튼 및 클릭 요소 (Buttons: {len(buttons)}개)")
            for itm in buttons:
                txt = itm.get("text", "")
                i = itm.get("id", "")
                cls_n = itm.get("className", "")
                sel = itm.get("selector", "")
                lines.append(f"  • [{txt}] {f'id=\"{i}\"' if i else ''} {f'class=\"{cls_n}\"' if cls_n else ''} ➔ {sel}")

        checks = catalog.get("checks_radios", [])
        if checks:
            lines.append(f"\n☑️ 체크박스 / 라디오 (Checks & Radios: {len(checks)}개)")
            for itm in checks:
                lbl = itm.get("label", "")
                i = itm.get("id", "")
                sel = itm.get("selector", "")
                lines.append(f"  • [{lbl}] {f'id=\"{i}\"' if i else ''} ➔ {sel}")

        selects = catalog.get("selects", [])
        if selects:
            lines.append(f"\n🔽 드롭다운 / 콤보박스 (Selects: {len(selects)}개)")
            for itm in selects:
                lbl = itm.get("label", "")
                sel = itm.get("selector", "")
                lines.append(f"  • [{lbl}] ➔ {sel}")

        grids = catalog.get("grids", [])
        if grids:
            lines.append(f"\n📊 테이블 / 데이터 그리드 (Grids: {len(grids)}개)")
            for itm in grids:
                t = itm.get("type", "")
                sel = itm.get("selector", "")
                lines.append(f"  • [{t}] ➔ {sel}")

        links = catalog.get("links", [])
        if links:
            lines.append(f"\n📑 네비게이션 링크 / 탭 (Links: {len(links)}개)")
            for itm in links[:15]:
                txt = itm.get("text", "")
                lines.append(f"  • [{txt}] ➔ a:has-text('{txt}')")

        return "\n".join(lines)
