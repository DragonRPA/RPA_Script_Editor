"""
UBUS Contract RPA & Ollama Pipeline - EXE Packaging Script
PyInstaller를 사용하여 단일 실행 파일(.exe)로 빌드하는 자동화 스크립트
"""

import os
import sys
import subprocess
import customtkinter

def build_executable():
    print("==================================================")
    print("UBUS Contract RPA - EXE 단일 실행 파일 빌드 시작")
    print("==================================================")

    # customtkinter 패키지 경로 탐색
    ctk_dir = os.path.dirname(customtkinter.__file__)
    print(f"CustomTkinter 경로: {ctk_dir}")

    # 빌드 명령어 구성
    # Windows에서는 ';'로 add-data 구분
    ctk_data_arg = f"{ctk_dir};customtkinter/"

    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",             # 초기 빠른 실행 및 브라우저 호환성을 위해 onedir 권장 (필요시 --onefile 전환)
        "--windowed",           # GUI 전용 (콘솔 창 숨김)
        "--name=UBUS_Contract_RPA",
        f"--add-data={ctk_data_arg}",
        "--hidden-import=playwright",
        "--hidden-import=fitz",
        "--hidden-import=httpx",
        "--hidden-import=customtkinter",
        "--hidden-import=PIL",
        "main.py"
    ]

    print("실행 명령어:", " ".join(cmd))
    result = subprocess.run(cmd)

    if result.returncode == 0:
        print("\n[빌드 성공] dist/UBUS_Contract_RPA 폴더에 실행 파일이 생성되었습니다.")
    else:
        print(f"\n[빌드 실패] 에러 코드: {result.returncode}")

if __name__ == "__main__":
    build_executable()
