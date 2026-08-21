"""
UBUS Contract RPA & Ollama Pipeline - File Pipeline Manager
3단계 폴더 라이프사이클(대기 ➔ OCR완료/파일명변경 ➔ RPA등록완료 / 오류격리) 관리 모듈
"""

import os
import shutil
import time
from typing import List, Dict, Tuple, Optional


class FilePipeline:
    """PDF 파일의 3단계 수명 주기 및 폴더 이동을 안전하게 관리하는 클래스"""

    def __init__(self, input_dir: str, ocr_done_dir: str, rpa_done_dir: str, error_dir: str):
        self.input_dir = os.path.abspath(input_dir)
        self.ocr_done_dir = os.path.abspath(ocr_done_dir)
        self.rpa_done_dir = os.path.abspath(rpa_done_dir)
        self.error_dir = os.path.abspath(error_dir)
        self.ensure_directories()

    def ensure_directories(self):
        """필요한 모든 작업 폴더를 사전에 자동 생성"""
        for d in [self.input_dir, self.ocr_done_dir, self.rpa_done_dir, self.error_dir]:
            os.makedirs(d, exist_ok=True)

    def update_directories(self, input_dir: str, ocr_done_dir: str, rpa_done_dir: str, error_dir: str):
        """디렉토리 경로 변경 시 업데이트"""
        self.input_dir = os.path.abspath(input_dir)
        self.ocr_done_dir = os.path.abspath(ocr_done_dir)
        self.rpa_done_dir = os.path.abspath(rpa_done_dir)
        self.error_dir = os.path.abspath(error_dir)
        self.ensure_directories()

    def get_input_files(self) -> List[str]:
        """1단계 대기 폴더 내의 모든 PDF 파일 목록 반환"""
        if not os.path.exists(self.input_dir):
            return []
        files = [
            os.path.join(self.input_dir, f)
            for f in os.listdir(self.input_dir)
            if f.lower().endswith(".pdf") and not f.startswith("~$")
        ]
        return sorted(files)

    def generate_new_filename(self, extracted_data: Dict[str, str], template: str = "{계약번호}.pdf", fallback_orig_name: str = "") -> str:
        """
        추출된 키워드 딕셔너리와 템플릿을 조합하여 새 파일명 생성.
        키워드 치환이 불가능하거나 빈 값일 경우 원본 파일명 보존.
        """
        new_name = template
        has_replaced = False
        for k, v in extracted_data.items():
            token = f"{{{k}}}"
            if token in new_name and v:
                # 윈도우 파일명 금지 특수문자 치환: \ / : * ? " < > |
                safe_v = re_clean_filename(v)
                new_name = new_name.replace(token, safe_v)
                has_replaced = True

        if not has_replaced or "{" in new_name:
            # 주 키워드가 없거나 템플릿 치환이 온전히 완료되지 않은 경우
            main_key_val = extracted_data.get("계약번호", "").strip()
            if main_key_val:
                new_name = f"{re_clean_filename(main_key_val)}.pdf"
            else:
                new_name = fallback_orig_name or f"미추출_{int(time.time())}.pdf"

        if not new_name.lower().endswith(".pdf"):
            new_name += ".pdf"
        return new_name

    def move_to_ocr_done(
        self,
        src_path: str,
        extracted_data: Dict[str, str],
        template: str = "{계약번호}.pdf"
    ) -> Tuple[bool, str, str]:
        """
        [1단계 대기 ➔ 2단계 OCR완료]
        추출된 키워드로 파일명을 변경하면서 2단계 OCR 완료 폴더로 이동.
        Returns: (성공여부, 이동된_새_경로, 새_파일명)
        """
        orig_filename = os.path.basename(src_path)
        new_filename = self.generate_new_filename(extracted_data, template, orig_filename)
        dest_path = os.path.join(self.ocr_done_dir, new_filename)

        # 파일명 충돌 방지 (_1, _2 ...)
        dest_path = self._get_unique_path(dest_path)

        success = self._safe_move(src_path, dest_path)
        if success:
            return True, dest_path, os.path.basename(dest_path)
        else:
            return False, src_path, orig_filename

    def move_to_rpa_done(self, src_path: str) -> Tuple[bool, str]:
        """
        [2단계 OCR완료 ➔ 3단계 RPA완료]
        ERP 등록 및 저장 성공 후 최종 보관 폴더로 이동.
        """
        filename = os.path.basename(src_path)
        dest_path = os.path.join(self.rpa_done_dir, filename)
        dest_path = self._get_unique_path(dest_path)

        success = self._safe_move(src_path, dest_path)
        return success, dest_path if success else src_path

    def move_to_error(self, src_path: str, error_reason: str) -> Tuple[bool, str]:
        """
        [오류 발생 시 ➔ 4단계 오류격리]
        실패한 파일을 격리 폴더로 이동하고 사유 텍스트 파일 동반 생성.
        """
        filename = os.path.basename(src_path)
        dest_path = os.path.join(self.error_dir, filename)
        dest_path = self._get_unique_path(dest_path)

        success = self._safe_move(src_path, dest_path)
        if success:
            # 에러 사유 기록
            log_path = f"{dest_path}.error.txt"
            try:
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(f"오류 발생 시간: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"원본 파일명: {filename}\n")
                    f.write(f"오류 사유:\n{error_reason}\n")
            except Exception as e:
                print(f"[FilePipeline] 에러 로그 기록 실패: {e}")
        return success, dest_path if success else src_path

    def _get_unique_path(self, target_path: str) -> str:
        """동일한 이름의 파일이 존재할 경우 _1, _2를 붙여 고유한 경로 생성"""
        if not os.path.exists(target_path):
            return target_path

        base_dir, file_name = os.path.split(target_path)
        name, ext = os.path.splitext(file_name)
        counter = 1

        while True:
            candidate = os.path.join(base_dir, f"{name}_{counter}{ext}")
            if not os.path.exists(candidate):
                return candidate
            counter += 1

    def _safe_move(self, src: str, dst: str, retries: int = 3, delay: float = 0.5) -> bool:
        """파일 잠금(Lock) 해제를 대기하며 안전하게 이동"""
        for attempt in range(retries):
            try:
                shutil.move(src, dst)
                return True
            except (PermissionError, OSError) as e:
                time.sleep(delay)
        print(f"[FilePipeline] 파일 이동 최종 실패 ({src} ➔ {dst})")
        return False


def re_clean_filename(text: str) -> str:
    """윈도우 파일명에 사용 불가능한 특수문자 정제"""
    invalid_chars = r'[\/:*?"<>|]'
    import re
    cleaned = re.sub(invalid_chars, '_', text)
    return cleaned.strip()
