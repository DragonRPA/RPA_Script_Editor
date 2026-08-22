"""
Universal RPA - Live Interactive DOM Harvester
대상 웹 URL에 실시간 접속하여 상호작용 가능한 핵심 DOM 요소(인풋, 버튼, 테이블, 라벨 등)를
정제된 구조화된 HTML 스니펫으로 수집하는 증거 기반(Evidence-Based) DOM 분석기
"""

import os
import sys
import re
import time
from typing import Dict, Any, Optional

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


JS_INTERACTIVE_DOM_EXTRACTOR = """() => {
    const lines = [];
    const elements = document.querySelectorAll('input, button, select, textarea, [role="button"], [role="textbox"], [role="tab"], a, table, .ag-root, .ag-row, form');
    
    let count = 0;
    elements.forEach((el) => {
        if (count >= 100) return;
        const tag = el.tagName.toLowerCase();
        
        // 숨겨진 요소 스킵 (단, type=hidden/type=file 제외)
        if (el.type !== 'file' && el.type !== 'hidden') {
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return;
        }

        let attrs = '';
        if (el.id) attrs += ` id="${el.id}"`;
        if (el.name) attrs += ` name="${el.name}"`;
        if (el.type) attrs += ` type="${el.type}"`;
        if (el.placeholder) attrs += ` placeholder="${el.placeholder}"`;
        if (el.getAttribute('aria-label')) attrs += ` aria-label="${el.getAttribute('aria-label')}"`;
        if (el.getAttribute('role')) attrs += ` role="${el.getAttribute('role')}"`;
        if (el.getAttribute('data-field')) attrs += ` data-field="${el.getAttribute('data-field')}"`;
        if (el.className && typeof el.className === 'string') {
            const cleanCls = el.className.trim().split(/\\s+/).slice(0, 3).join(' ');
            if (cleanCls) attrs += ` class="${cleanCls}"`;
        }

        let text = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 35);
        if (tag === 'input' || tag === 'select') text = ''; // 인풋 내부 텍스트 제외

        // 인접 라벨 텍스트 탐색
        let labelHint = '';
        if (tag === 'input' || tag === 'select' || tag === 'textarea') {
            const lbl = el.closest('label') || document.querySelector(`label[for="${el.id}"]`) || el.parentElement.querySelector('label');
            if (lbl) {
                const lt = lbl.innerText.trim().replace(/\\s+/g, ' ').slice(0, 25);
                if (lt) labelHint = ` <!-- Label: ${lt} -->`;
            }
        }

        if (tag === 'table' || el.classList.contains('ag-root') || el.classList.contains('ag-row')) {
            lines.push(`<${tag}${attrs}>[그리드/테이블 컴포넌트]</${tag}>`);
        } else if (text) {
            lines.push(`<${tag}${attrs}>${text}</${tag}>${labelHint}`);
        } else {
            lines.push(`<${tag}${attrs} />${labelHint}`);
        }
        count++;
    });

    return {
        title: document.title || '',
        url: window.location.href || '',
        elementsCount: count,
        domSnippet: lines.join('\\n')
    };
}"""


class DOMHarvester:
    """실시간 웹 DOM 수집 및 정제 매니저"""

    @classmethod
    def harvest_live_dom(cls, url: str, timeout_sec: int = 12) -> Dict[str, Any]:
        """
        Playwright 헤드리스 브라우저로 URL에 접속하여 실제 렌더링된 핵심 DOM 스니펫 추출
        """
        if not url:
            raise ValueError("수집할 URL이 비어 있습니다.")

        if not url.startswith("http://") and not url.startswith("https://"):
            url = "http://" + url

        start_time = time.time()

        # 1. Playwright 기반 동적 DOM 렌더링 수집 (1순위)
        if HAS_PLAYWRIGHT:
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        viewport={"width": 1920, "height": 1080},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    )
                    page = context.new_page()
                    page.goto(url, timeout=timeout_sec * 1000)
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_timeout(800)  # React/Vue 동적 렌더링 대기

                    extracted = page.evaluate(JS_INTERACTIVE_DOM_EXTRACTOR)
                    browser.close()

                    elapsed = time.time() - start_time
                    return {
                        "status": "success",
                        "engine": "Playwright Dynamic Harvester",
                        "url": extracted.get("url", url),
                        "title": extracted.get("title", ""),
                        "count": extracted.get("elementsCount", 0),
                        "dom_snippet": extracted.get("domSnippet", ""),
                        "elapsed_sec": round(elapsed, 2)
                    }
            except Exception as ex:
                # Playwright 실패 시 2순위 Fallback 진행
                pass

        # 2. requests + BeautifulSoup 정적 DOM 수집 Fallback (2순위)
        if HAS_BS4:
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                resp = requests.get(url, headers=headers, timeout=timeout_sec)
                soup = BeautifulSoup(resp.text, "html.parser")

                lines = []
                for el in soup.find_all(["input", "button", "select", "textarea", "a", "table", "form"])[:70]:
                    tag = el.name
                    attrs = ""
                    for attr_name in ["id", "name", "type", "placeholder", "class", "role", "aria-label"]:
                        val = el.get(attr_name)
                        if val:
                            if isinstance(val, list):
                                val = " ".join(val[:3])
                            attrs += f' {attr_name}="{val}"'

                    text = el.get_text(strip=True)[:30]
                    if text:
                        lines.append(f"<{tag}{attrs}>{text}</{tag}>")
                    else:
                        lines.append(f"<{tag}{attrs} />")

                elapsed = time.time() - start_time
                return {
                    "status": "success",
                    "engine": "Static HTML Parser (Fallback)",
                    "url": url,
                    "title": soup.title.string if soup.title else "",
                    "count": len(lines),
                    "dom_snippet": "\n".join(lines),
                    "elapsed_sec": round(elapsed, 2)
                }
            except Exception as ex:
                raise RuntimeError(f"DOM 수집 실패: {ex}")

        raise RuntimeError("Playwright 또는 BeautifulSoup 모듈을 사용할 수 없습니다.")
