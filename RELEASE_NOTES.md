# RELEASE_NOTES.md

## [v2.1.2.Build.11] - 2026-08-21 16:44

### ⚡ [초고속 반응성] Windows UIA Spy 전역 키 리스너 100% 비동기 독립 스레드 분리

1. **UIA 탐색과 키 리스너의 완전한 스레드 분리**:
   - 무거운 COM UIA 트리 탐색(`ControlFromCursor`)과 키 입력을 완전히 분리
   - **`10ms(100Hz)` 초고속 독립 워커 스레드**로 `F2` 키의 물리적 누름(Edge Trigger)을 0ms 레이턴시로 100% 즉시 감지
2. **청각적 비프음 피드백 탑재 (`MessageBeep`)**:
   - 외부 프로그램 위에서 `F2`를 누르는 즉시 시스템 삡(Beep) 사운드를 출력하여 캡처 동결/해제 여부를 직관적으로 인지
3. **무결점 즉시 반응 보장**:
   - UIA 조회가 진행 중이어도 키 입력이 절대로 씹히거나 무시되지 않고 100% 즉시 동결 처리

---



### 🐛 [버그 수정 & 강화] Windows UIA Spy COM 스레드 초기화 및 전역 F2 캡처 완성

1. **백그라운드 스레드 COM 초기화 버그 수정**:
   - `uia.ControlFromCursor()` 호출 시 백그라운드 스레드의 `CoInitialize` 누락으로 인한 무음 실패(Silent Exception) 완전 해결
   - `uia.UIAutomationInitializerInThread()` 컨텍스트 적용으로 마우스 이동 시 실시간 속성 탐색 100% 정상 가동
2. **OS 전역 `F2` 키 감지 탑재 (`GetAsyncKeyState`)**:
   - 스파이 창을 클릭하지 않고 다른 외부 윈도우(사내 ERP 등) 위에 마우스가 있는 상태에서도 키보드 **`F2`**를 누르면 즉시 동결 캡처(Freeze) 작동
3. **스파이 창 자체 검사 방지 필터**:
   - 스파이 창 내부 UI를 마우스로 가리킬 때 이전 캡처 타겟이 유지되도록 자기 자신(Self Window) 스캔 방지 필터 적용

---



### 🔍 [신기능 탑재] Microsoft Windows UI Automation (UIA) Spy & 코드 생성기 내장

1. **실시간 데스크톱 엘리먼트 스파이 (`windows_spy.py`) 탑재**:
   - 윈도우 OS 프로그램(사내 ERP, WinForms, WPF, C#, VB, Delphi 등) 화면 위 마우스 호버 시 실시간 UIA 객체 분석
   - 6대 핵심 속성 실시간 감지: `AutomationId`, `Name`, `ControlTypeName`, `ClassName`, `BoundingRectangle`, `ProcessName`
   - **`F2` 키** 또는 `[🎯 캡처/동결]` 버튼으로 원하는 컨트롤의 속성을 즉시 동결 캡처
2. **파이썬 UIA 및 4단계 Fallback 자동화 코드 생성기**:
   - 동작 모드(클릭, 더블클릭, 텍스트 입력, 창 활성화) 선택 시 파이썬 UIA 제어 코드 자동 생성
   - UIA 실패 시 2순위 윈도우 상대좌표 Fallback 코드 자동 포함
3. **스튜디오 & 봇 에디터 원클릭 연동**:
   - `[📋 에디터 커서에 코드 삽입]`: 파이썬 스크립트 에디터에 즉시 코드 주입
   - `[🤖 봇 에디터에 모듈로 즉시 추가]`: 캡처한 윈도우 컨트롤을 봇 파이프라인의 신규 모듈 카드로 즉시 등록
   - 상단 툴바에 보라색 **`[🔍 Windows UIA Spy]`** 원클릭 실행 버튼 배치

---



### 🤖 [메이저 개편] 모듈 기반 2분할 봇 에디터 (Bot Builder) & 완성 봇 DB 저장소 구축

1. **봇 에디터 (Bot Builder) 2분할 레이아웃 전면 개편**:
   - **좌측 [🤖 봇 조립 파이프라인]**:
     - 1개 카드를 마이크로 액션이 아닌 **'완성된 파이썬 스크립트 모듈'** 단위로 재정의
     - 각 모듈 카드별 **인라인 파이썬 코드 에디터** 내장 (직접 코드 수정 및 실시간 반영)
     - `[▲]`, `[▼]` 모듈 순서 이동, `[▶ 단독실행]`, `[💾 DB저장]`, `[🗑️ 삭제]` 지원
     - `[▶ 봇 전체 실행]` 클릭 시 조립된 모듈들을 위에서 아래로 순차 병합하여 일괄 자동 실행
   - **우측 [🗄️ Neon DB 모듈 라이브러리]**:
     - 카테고리 필터(로그인, 웹조작, 윈도우앱, OCR, DB, 스니펫, 유틸, 사용자정의) 및 실시간 검색 지원
     - **`[➕ 봇에 모듈 삽입 ➔]`** 원클릭으로 우측 모듈을 좌측 봇 파이프라인에 즉시 카드로 추가
2. **완성 봇(Bot) Neon DB 영구 저장소(`rpa_bots`) 구축**:
   - Neon PostgreSQL에 `rpa_bots` 테이블 신규 DDL 가동
   - 조립된 모듈 목록(순서, 개별 코드)과 전체 결합 파이썬 코드를 통째로 저장(`[💾 봇 DB 저장]`) 및 원클릭 복원(`[📂 봇 DB 불러오기]`)
3. **불필요한 실시간 녹화 코드 전면 제거**:
   - Playwright Inspector(`codegen`)가 완벽한 녹화를 지원하므로, 커스텀 마우스 후킹/실시간 녹화 위젯을 전면 제거하여 시스템 경량화 및 가독성 극대화

---



### 🐛 [버그 수정 & 완성] 파이썬 스크립트 ➔ 스텝 카드 변환 엔진 연결 및 렌더링 수정

1. **위젯 참조 오류 수정**:
   - `recorder_gui.py` 내부 텍스트 에디터 위젯명(`self.txt_code`) 불일치로 인한 빈 코드 참조 문제 완전 해결
   - `@property def txt_script_editor` 양방향 별칭 지원으로 호환성 100% 확보
2. **지능형 파서(`playwright_parser.py`) 변수 할당 패턴 인식 강화**:
   - `contract_input = page.locator(...)` 및 `contract_input.fill(...)` 등 변수 기반 로케이터 체이닝 구문 완벽 파싱
   - 주석 기반 단계 구분(`# [1단계: 1회 실행]`, `# [2단계: 반복 루프]`) 자동 인식
3. **카드 렌더링 UI 확장**:
   - `GOTO`, `FILL`, `SET_FILES`, `CLICK`, `DBLCLICK`, `WAIT_TIME`, `PRESS_KEY`, `EXEC_CODE` 등 모든 액션에 대해 입력값/변수 주입 필드 완벽 렌더링

---



### 🧩 [지능형 파서] 파이썬 스크립트 ➔ 비주얼 스텝 카드 즉시 변환 엔진 탑재

1. **에디터 툴바 `[🧩 스크립트 ➔ 스텝 카드로 변환]` 직통 원클릭 버튼 추가**:
   - 파이썬 스크립트 에디터에서 작성 중인 코드를 클릭 한 번으로 파싱
   - 1회 실행(Setup)과 반복 루프(Loop) 영역으로 지능적 자동 분류
   - 변환 즉시 `[🧩 비주얼 스텝 카드 에디터]` 탭으로 화면 자동 전환 및 카드 렌더링
2. **지능형 파서 엔진(`playwright_parser.py`) 대폭 강화**:
   - `goto`, `fill`, `click`, `dblclick`, `set_input_files`, `check`, `select_option`, `wait_for_timeout`, `wait_for_selector`, `press` 지원
   - `find_and_focus_window`, `pyautogui.click` 좌표 클릭, `PIXEL_MATCH` 지원
   - `item['계약번호']` ➔ `{{계약번호}}`, `item['file_path']` ➔ `{{첨부파일_경로}}` 자동 변수 매핑
   - 기타 커스텀 파이썬 구문은 `EXEC_CODE` 카드로 안전 보존
3. **전사 Neon DB 모듈(`neon_db.py`) 동기화**:
   - `Universal_RPA_Recorder` 및 `UBUS_contract` 양방향 100% 동기화 유지

---



### ☁️ [모듈형 RPA] Neon DB 기반 `rpa_scripts` 라이브러리 및 에디터 관리 모달 구축 완료

1. **`rpa_scripts` 단일 테이블 스키마 정식 가동**:
   - Neon PostgreSQL 콘솔에서 DDL 생성 완료 (`name`, `title`, `category`, `description`, `code`, `target_type`, `is_active`, `created_at`, `updated_at`)
   - 카테고리/식별자 복합 인덱스 가동
2. **초기 핵심 모듈 4종 Neon DB 시드 등록**:
   - `ubus_login`: UBUS ERP 로그인
   - `contract_search_and_upload`: 계약번호 조회 및 PDF 첨부
   - `find_and_focus_window`: 윈도우 앱 창 찾기 및 포커스 이동
   - `robust_click_fallback`: 4단계 Fallback 자동 강등 클릭
3. **에디터 UI `[☁️ DB 모듈 라이브러리]` 관리 모달 탑재**:
   - `gui_app.py` & `recorder_gui.py` 공통 탑재
   - 좌측 카테고리 필터별 DB 저장 모듈 목록 표시
   - 원클릭 코드 에디터 삽입 (`[📋 에디터에 삽입]`)
   - 현재 작성 중인 코드 즉시 DB 모듈로 등록/수정 (`[💾 Neon DB에 저장/수정]`)
   - DB 모듈 단건 삭제 (`[🗑️ DB에서 삭제]`)

---



### 🗄️ [클라우드 DB] Neon Serverless PostgreSQL 정식 연동 & 스키마 자동 구축 완료

1. **Neon PostgreSQL 실시간 라이브 연동**:
   - 싱가포르 리전(`ap-southeast-1`) PostgreSQL 18.6 실시간 연결 확인 (지연시간 ~700ms)
   - `psycopg2-binary` 패키지 설치 및 `neon_db.py` 매니저 모듈 신규 탑재
2. **RPA 2대 핵심 테이블 자동 초기화**:
   - `rpa_contract_logs`: 계약번호, 파일명, 처리상태, OCR JSON 데이터, 소요시간, 인덱스 자동 생성
   - `rpa_batch_runs`: 배치 ID, 총 파일수, 성공수, 실패수, 완료시각
3. **스니펫 라이브러리 `🗄️ 데이터베이스 (Neon PostgreSQL)` 카테고리 추가**:
   - Neon DB 매니저로 단일 계약서 로그 기록
   - 직접 SQL 쿼리 실행 (psycopg2)
   - RPA 배치 실행 요약 통계 저장

---



### 🖥️ [ImageScan 프로젝트 이식] 윈도우 앱 자동화 4단계 Fallback 아키텍처 완전 탑재

#### 신규 기능

1. **스니펫 라이브러리 전면 확장 (8개 카테고리)**:
   - `🖥️ 윈도우 앱 자동화` 카테고리 신규 추가
   - `FIND_WINDOW`: 창 제목 키워드로 윈도우 앱 창 찾기 및 포커스 이동 (`pywin32`)
   - `UIA_CONTROL`: `pywinauto` AutomationId 기반 컨트롤 클릭/입력/값 읽기
   - `PIXEL_MATCH`: `pyautogui.locateOnScreen` 이미지 매칭 클릭 (confidence 설정)
   - `KVM_INPUT`: 절대 좌표 클릭, 단축키, 키보드 타이핑 OS 레벨 직접 제어
   - `4단계 Fallback 완전 보호 체계`: CSS→UIA→PIXEL_MATCH→KVM 자동 강등 로직
   - `JS DOM 강제 주입`: React/Vue 가상DOM 필드 강제 값 주입 (onChange 이벤트 포함)
   - `중첩 루프 (LOOP_ROWS)`: 부모 루프 안에 서브 루프 계층형 중첩
   - `창 Alias 딕셔너리`: 팝업창 핸들 Alias 관리로 다중 창 완벽 제어
   - `iframe 전환`: iframe 내부 요소 직접 접근
   - `엑셀 파일 읽기 (pandas)`, `JSON 파일 입출력`, `파일 이동`, `날짜/시간 변수` 추가

2. **GUI 탭 신규 추가: `🖥️ 윈도우 앱 자동화 (Desktop)`**:
   - FIND_WINDOW 도구: 창 제목 키워드 입력 → 창 찾기 및 포커스 이동
   - UIA_CONTROL 도구: AutomationId 기반 Click / SetValue / GetValue 실행
   - PIXEL_MATCH 도구: 이미지 파일 선택 → 화면 매칭 클릭 (confidence 슬라이더)
   - KVM_INPUT 도구: 좌표 클릭 / 단축키 입력 / 텍스트 타이핑 버튼 3종
   - UIA Live Inspector: 현재 마우스 위치의 윈도우 컨트롤 정보 실시간 스캔

3. **requirements.txt 업데이트**:
   - `pywinauto>=0.6.8`, `pyautogui>=0.9.54`, `pywin32>=306`, `pyperclip>=1.8.2`
   - `pandas>=2.0.0`, `openpyxl>=3.1.0` 추가

---



### 🚀 최초 공개 릴리즈 — 범용 RPA 스크립트 에디터 플랫폼

#### 핵심 기능 탑재

1. **스니펫 지원형 파이썬 스크립트 IDE**
   - 메모장처럼 자유롭게 파이썬 코드를 작성하고, 좌측 스니펫 라이브러리 버튼을 누르면 커서 위치에 즉시 코드 삽입
   - 빌드 없이 인터프리터로 즉시 테스트 실행, 실시간 콘솔 출력

2. **원클릭 스니펫 라이브러리 6대 카테고리**
   - 📁 템플릿: PDF 반복 루프 뼈대, 단일 건 처리 함수
   - 🖱️ 웹 조작: 클릭, 입력, 더블클릭, 파일 첨부, 체크박스, 드롭다운, 키보드, 마우스 오버
   - ⏳ 대기 및 검증: 시간 대기, 요소 대기, 네트워크 대기, API 응답 대기
   - 📑 다중 창 및 팝업: 팝업창 캡처 제어, 새 탭, 알림창 자동 수락
   - 🛡️ 제어문 및 방어 로직: try-except, 무음 닫기, while 재시도, match-case, if-elif-else
   - 🔤 동적 변수: item 및 env 변수 일괄 제공

3. **PDF OCR + Ollama AI 키워드 추출**
   - PyMuPDF 고속 텍스트 추출 + qwen2.5:7b JSON Schema 구조화 추출

4. **3단계 폴더 파이프라인**
   - 1_대기 → 2_OCR완료(파일명 변경) → 3_RPA완료 / 4_오류격리

5. **JSON 시나리오 재생 엔진**
   - setup_steps(1회 로그인) + loop_steps(건별 반복) 이중 구조
   - 변수 바인딩: {{계약번호}}, {{첨부파일_경로}} 실시간 치환
