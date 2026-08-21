# RPA Script Editor — Universal RPA Platform

> **웹 브라우저 + 윈도우 앱을 동시에 제어하는 범용 RPA 파이썬 스크립트 편집기**

---

## 🚀 프로젝트 개요

Playwright 기반 웹 자동화 + `pywinauto` / `pyautogui` 기반 윈도우 앱(Desktop) 자동화를 통합한 **범용 RPA 스크립트 에디터 + PDF OCR 재생기** 플랫폼.

### 주요 기능

| 기능 | 설명 |
| :--- | :--- |
| **🐍 파이썬 스크립트 에디터** | 메모장처럼 자유롭게 코드 작성 + 원클릭 스니펫 삽입 |
| **🛠️ 스니펫 라이브러리** | 웹 조작, 윈도우 앱(UIA), 이미지 매칭, 제어문, 변수 등 원클릭 삽입 |
| **📷 PDF OCR 추출** | PyMuPDF + Ollama AI(qwen2.5:7b)로 PDF에서 키워드 추출 |
| **🔄 3단계 파이프라인** | 대기 → OCR완료 → RPA완료 / 오류격리 자동 파일 관리 |
| **▶ 즉시 실행** | 빌드 없이 에디터 코드를 인터프리터로 즉시 테스트 실행 |
| **🖥️ 윈도우 앱 자동화** | UIA_CONTROL, PIXEL_MATCH, KVM 좌표 클릭 등 Fallback 체계 |

---

## 📦 설치 필요 패키지

```bash
pip install playwright customtkinter pyautogui pywinauto pywin32 pymupdf requests
playwright install chromium
```

---

## 🏃 실행 방법

```bash
python main.py
```

---

## 📁 파일 구조

```
UBUS_contract/
├── main.py                # 실행 진입점
├── gui_app.py             # 메인 GUI (스크립트 에디터 + 대시보드)
├── snippets_library.py    # 원클릭 스니펫 라이브러리 (웹 + 윈도우)
├── pdf_extractor.py       # PDF OCR + Ollama AI 추출기
├── file_pipeline.py       # 3단계 파일 라이프사이클 관리
├── scenario_runner.py     # JSON 시나리오 재생 엔진
├── config_manager.py      # 설정 저장/복원 (config.json)
└── scenario.json          # 기본 UBUS ERP 시나리오
```

---

## 🔑 버전

`v1.0.0.Build.1` — 2026-08-21

- 최초 공개: 스니펫 지원형 파이썬 스크립트 에디터 + PDF OCR + RPA 재생기
