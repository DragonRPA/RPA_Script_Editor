"""
UBUS Contract RPA & Ollama Pipeline - PDF Extractor
PyMuPDF 고속 텍스트 추출 + Ollama JSON Schema 기반 키워드(계약번호 등) 구조화 추출 모듈
"""

import json
import re
import os
from typing import Dict, List, Any, Optional
import pymupdf as fitz
import httpx


class PDFExtractor:
    """PDF 파일 파싱 및 로컬 Ollama AI 기반 키워드 추출 클래스"""

    def __init__(self, ollama_url: str = "http://localhost:11434", model: str = "qwen2.5:7b"):
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model

    def extract_text_from_pdf(self, pdf_path: str, max_pages: int = 3) -> str:
        """
        PyMuPDF를 사용하여 PDF의 상위 N개 페이지 텍스트를 고속 추출.
        계약번호 및 핵심 정보는 대부분 1~2페이지에 위치하므로 기본 3페이지까지 읽음.
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")

        extracted_text = []
        try:
            with fitz.open(pdf_path) as doc:
                total_pages = min(len(doc), max_pages)
                for page_num in range(total_pages):
                    page = doc[page_num]
                    text = page.get_text("text")
                    if text.strip():
                        extracted_text.append(f"--- [페이지 {page_num + 1}] ---\n{text}")
        except Exception as e:
            raise RuntimeError(f"PDF 파싱 실패 ({pdf_path}): {e}")

        return "\n\n".join(extracted_text)

    def extract_keywords_with_ollama(
        self,
        pdf_text: str,
        keywords: List[str],
        timeout_sec: float = 20.0
    ) -> Dict[str, str]:
        """
        Ollama REST API(/api/chat)를 호출하여 텍스트에서 지정된 키워드 값들을 JSON 형태로 추출
        """
        if not keywords:
            keywords = ["계약번호"]

        # JSON Schema 프로퍼티 동적 구성
        properties = {}
        for kw in keywords:
            properties[kw] = {
                "type": "string",
                "description": f"문서 내에 기재된 {kw} 값"
            }

        schema = {
            "type": "object",
            "properties": properties,
            "required": keywords
        }

        system_prompt = (
            "너는 전문 계약서 분석기다. 사용자가 제공하는 계약서 문서 텍스트에서 "
            "요청된 키워드에 해당하는 값을 정확히 찾아내어 지정된 JSON 형식으로만 응답하라.\n"
            "규칙:\n"
            "1. 절대 추측하거나 지어내지 말고, 문서 본문에 명시된 정확한 문자열만 추출하라.\n"
            "2. 키워드에 해당하는 값을 찾지 못했을 경우 빈 문자열(\"\")로 채워라.\n"
            "3. 계약번호는 대개 '2D...', '2C...', '250...', 숫자와 영문이 혼합된 번호 형식이다.\n"
            "4. 부가적인 설명이나 마크다운 백틱 없이 순수 JSON 객체만 반환하라."
        )

        user_content = f"추출 대상 키워드: {', '.join(keywords)}\n\n[문서 내용]:\n{pdf_text[:4000]}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "format": schema,
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_predict": 256
            }
        }

        url = f"{self.ollama_url}/api/chat"
        try:
            with httpx.Client(timeout=timeout_sec) as client:
                response = client.post(url, json=payload)
                if response.status_code == 200:
                    res_json = response.json()
                    raw_content = res_json.get("message", {}).get("content", "{}")
                    parsed = json.loads(raw_content)
                    return {k: str(parsed.get(k, "")).strip() for k in keywords}
                else:
                    print(f"[PDFExtractor] Ollama API 응답 오류 (Status {response.status_code}): {response.text}")
        except Exception as e:
            print(f"[PDFExtractor] Ollama 호출 예외 발생: {e}")

        # Ollama 실패 시 정규식 Fallback 시도
        return self._fallback_regex_extract(pdf_text, keywords)

    def _fallback_regex_extract(self, text: str, keywords: List[str]) -> Dict[str, str]:
        """Ollama 호출 실패 시 정규식을 이용한 긴급 Fallback 추출"""
        result = {kw: "" for kw in keywords}
        
        # 계약번호 정규식 패턴 탐색 (예: 2D2607007, 2D2504013 등)
        contract_patterns = [
            r'계약\s*번호\s*[:：]?\s*([0-9A-Za-z\-]{6,15})',
            r'\b([0-9]{1,2}[A-Z][0-9]{6,8})\b',
            r'\b([0-9]{7,10})\b'
        ]
        
        for pat in contract_patterns:
            match = re.search(pat, text)
            if match:
                val = match.group(1).strip()
                if "계약번호" in result:
                    result["계약번호"] = val
                    break

        return result

    def process_file(self, pdf_path: str, keywords: List[str]) -> Dict[str, str]:
        """PDF 파일 하나를 읽어 키워드 추출을 완료하는 통합 인터페이스"""
        text = self.extract_text_from_pdf(pdf_path)
        if not text.strip():
            return {kw: "" for kw in keywords}
        return self.extract_keywords_with_ollama(text, keywords)
