# CustomTkinter & PyInstaller 독립 실행형(EXE) GUI 프로그램 설계 가이드라인

이 문서는 `uv-offline-installer` 및 `gitignore_zipper` 프로젝트에서 활용된 GUI 및 단일 실행 파일(EXE) 컴파일 디자인 아키텍처를 분석하여, 새로운 GUI 유틸리티를 제작할 때 AI에 주입하거나 직접 재활용할 수 있도록 정형화한 시스템 프롬프트 및 코드 템플릿 세트입니다.

---

## 1. 핵심 아키텍처 원칙 (Core Architecture)

1. **디자인 시스템 (Premium CustomTkinter UI)**
   - **레이아웃**: 좌측 네비게이션 사이드바(Sidebar) + 우측 메인 콘텐츠 프레임(Content Frame) 구조.
   - **탭 전환**: 물리적인 창 이동 대신 `CTkFrame`을 상속받은 여러 스크롤 뷰를 필요에 따라 `grid()` / `grid_forget()`하여 전환.
   - **색상 시스템**: Toss Minimal 테마 기반의 단일 포인트 Accent 컬러(예: `#0064FF`) 및 가독성 높은 그레이 톤 매핑.
   - **다국어 및 한글 폰트 지원**: 시스템 기본 폰트 대신 한글 렌더링에 적합한 프리미엄 폰트 스택(`Pretendard`, `Noto Sans KR`, `Segoe UI Variable Text`)을 탐색하여 자동 로드.
   - **테마 동적 설정**: 시스템 설정(다크/라이트)을 자동 반영하며 사용자가 앱 내에서 동적 변경할 수 있는 UI 컨트롤 제공.

2. **비동기 스레딩 & 스레드 안전 UI 업데이트 (Thread-Safe UI)**
   - **비동기 분리**: I/O, 다운로드, 파일 압축/해제, 외부 명령 실행 등 0.1초 이상 걸리는 모든 작업은 반드시 데몬 스레드(`threading.Thread(daemon=True)`)로 실행.
   - **스레드 안전성**: 워커 스레드에서 Tkinter 컴포넌트에 직접 접근하지 않고, 반드시 `root.after(0, lambda: ...)`를 통해 메인 UI 스레드로 갱신 처리 전달.
   - **UI 독립형 비즈니스 로직**: 핵심 로직 함수는 GUI 클래스에 의존하지 않고 `log_callback(str)` 및 `progress_callback(int)`을 받아 호출하는 구조로 설계(CLI/GUI 재사용 가능).

3. **엔터프라이즈 SSL 및 네트워크 우회 설계 (Enterprise Network Bypass)**
   - 다운로드 기능 구현 시, 망 연계 및 프록시 환경에서 실패하지 않도록 3단계 SSL 대응 모드를 기본 포함:
     1. `Standard`: 기본 urllib 다운로드 (에러 발생 시 즉시 무검증 SSL 컨텍스트로 자동 Fallback).
     2. `System Certs`: Windows OS의 신뢰 인증서 저장소(`ssl.create_default_context()`) 활용.
     3. `Trusted Host`: SSL 검증 전면 생략 (`ssl._create_unverified_context()`) 및 pip 다운로드 시 `--trusted-host` 인수 자동 추가.

4. **단일/임베디드 EXE 컴파일 아키텍처 (Single/Embedded EXE Bundle)**
   - **PyInstaller frozen 감지**: 실행 중인 상태가 소스 코드 실행(`__file__`)인지 컴파일된 EXE인지 감지하여 리소스 경로 변경:
     - 내부 패키징 자원: `sys._MEIPASS` 활용.
     - 사용자 실행 경로/외부 파일: `os.path.dirname(sys.executable)` 활용.
   - **이중 구조 EXE 임베딩**: 빌더(`builder_gui.exe`)가 설치기(`installer_gui.exe`)를 내장하여 단일 파일로 배포하는 경우, PyInstaller `.spec` 파일의 `datas` 목록에 대상 EXE를 리소스로 바인딩하고 런타임에 임시 경로에서 추출하여 복제/실행.
   - **uv 기반 환경 무의존 컴파일**: `uv run` 옵션을 통해 호스트 PC에 PyInstaller나 CustomTkinter를 설치하지 않고 일회성 컴파일 환경에서 독립 빌드 구현.

---

## 2. 재사용 가능한 코드 템플릿 (Reusable Code Templates)

### 2.1 폰트 스택 확인 및 Frozen 경로 탐색 (Common Helpers)
```python
import os
import sys

# 1. 프리미엄 폰트 자동 매핑
def resolve_font() -> str:
    try:
        import tkinter as tk
        from tkinter import font
        root = tk.Tk()
        root.withdraw()
        families = font.families()
        root.destroy()
        for f in ["Pretendard", "Noto Sans KR", "Segoe UI Variable Text", "Segoe UI", "Malgun Gothic"]:
            if f in families:
                return f
    except Exception:
        pass
    return "Segoe UI"

FONT_FAMILY = resolve_font()

# 2. Frozen/Normal 실행 환경 감지 및 기본 경로 설정
def get_base_path() -> str:
    if getattr(sys, 'frozen', False):
        # exe 실행 경로 반환
        return os.path.dirname(sys.executable)
    # 소스 코드 파일 디렉토리 반환
    return os.path.dirname(os.path.abspath(__file__))

# 3. 임베디드 리소스 경로 탐색 (sys._MEIPASS)
def get_resource_path(relative_path: str) -> str:
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)
```

### 2.2 UI 비차단 & 스레드 세이프 상태 업데이트 구조
```python
import threading
import customtkinter as ctk

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        # ... UI 세팅 코드 ...
        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.pack(pady=10)
        self.log_text = ctk.CTkTextbox(self)
        self.log_text.pack(pady=10)
        self.run_btn = ctk.CTkButton(self, text="시작", command=self.start_task)
        self.run_btn.pack(pady=10)

    def start_task(self):
        self.run_btn.configure(state="disabled")
        self.progress_bar.set(0.0)
        self.log_text.delete("1.0", "end")

        # 스레드 안전 콜백 함수 정의
        def ui_log(msg: str):
            self.after(0, lambda: (self.log_text.insert("end", msg + "\n"), self.log_text.see("end")))

        def ui_progress(pct: float):
            self.after(0, lambda: self.progress_bar.set(pct / 100.0))

        # 메인 워커 스레드 기동
        def run():
            try:
                ui_log("[START] 비동기 작업을 수행합니다.")
                # 비즈니스 로직 실행 (UI 요소와 완전 격리)
                execute_business_logic(log_cb=ui_log, progress_cb=ui_progress)
                ui_log("[SUCCESS] 모든 작업을 완료했습니다.")
            except Exception as e:
                ui_log(f"[ERROR] 오류 발생: {e}")
            finally:
                self.after(0, lambda: self.run_btn.configure(state="normal"))

        threading.Thread(target=run, daemon=True).start()

def execute_business_logic(log_cb, progress_cb):
    import time
    for i in range(1, 11):
        time.sleep(0.5)  # 무거운 처리 가정
        progress_cb(i * 10)
        log_cb(f"작업 {i}/10 완료...")
```

### 2.3 3단계 SSL 우회 다운로드 헬퍼
```python
import ssl
import urllib.request

def download_file_with_ssl_fallback(url: str, dest_path: str, log_cb=None, ssl_bypass: str = "standard"):
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    
    def try_download(context=None):
        with urllib.request.urlopen(req, context=context) as response:
            with open(dest_path, 'wb') as f:
                f.write(response.read())
        return True

    if ssl_bypass == "trusted_host":
        # 무조건 SSL 무시
        return try_download(context=ssl._create_unverified_context())
    elif ssl_bypass == "system_certs":
        # OS 신뢰성 인증서 사용
        return try_download(context=ssl.create_default_context())
    else: # standard (우회 Fallback 내장)
        try:
            return try_download()  # 정식 SSL 검증 시도
        except Exception as e:
            if log_cb:
                log_cb(f"[WARNING] SSL 검증 실패 ({e}). 무인증 컨텍스트로 우회 시도합니다...")
            return try_download(context=ssl._create_unverified_context())
```

---

## 3. PyInstaller Spec & 컴파일 스크립트 설계

### 3.1 `compile.bat` 템플릿
로컬 환경에 라이브러리를 설치하지 않고 `uv run`으로 컴파일하는 명령어 구조입니다.
```bat
@echo off
echo ==========================================================
echo           standalone GUI Executable Compiler
echo ==========================================================
echo.
echo Compiling python GUI into a standalone EXE...

:: 컴파일에 필요한 모든 패키지를 --with 플래그를 사용하여 임시 주입
uv run --system-certs --with pyinstaller --with customtkinter --with pathspec --with cryptography pyinstaller --clean main_app.spec

if %errorlevel% neq 0 (
    echo [ERROR] Failed to compile main_app
    pause
    exit /b %errorlevel%
)

echo.
echo [SUCCESS] Compilation completed successfully!
echo Executable is located in the dist/ folder.
pause
```

### 3.2 `main_app.spec` 템플릿 (다른 EXE나 폴더 포함 구조)
```python
# -*- mode: python ; coding: utf-8 -*-
import os
import customtkinter

root = SPECPATH
ctk_path = os.path.dirname(customtkinter.__file__)

a = Analysis(
    [os.path.join(root, 'main_gui.py')], # 메인 실행 파일 경로
    pathex=[root],
    binaries=[],
    datas=[
        # (로컬 소스 경로, EXE 내부 압축 목적지)
        (os.path.join(root, 'dist/sub_helper.exe'), '.'), # 다른 컴파일된 EXE 내장 시 기재
        (os.path.join(root, 'src/*.py'), 'src'),
        (os.path.join(ctk_path, 'assets'), 'customtkinter/assets'), # CTK 에셋 강제 포함
    ],
    hiddenimports=[
        'customtkinter',
        'src',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='my_standalone_tool', # 최종 EXE 이름
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False, # GUI 전용일 때 Black 콘솔 숨김
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
)
```

---

## 4. 인공지능 프롬프트 지시어 (AI Prompt Instructions)

새로운 GUI 프로그램이나 폐쇄망 도구를 만들 때, 아래 프롬프트를 다른 AI 모델에 즉시 복사하여 주입할 수 있습니다.

```markdown
[Role & Context]
너는 파이썬(Python)과 CustomTkinter를 활용해 세련되고 모던한 디자인의 Windows 독립 실행형 GUI 프로그램(.exe)을 설계하고 구현하는 시니어 소프트웨어 아키텍트이자 개발자이다.

[Core UI Constraints]
1. UI 프레임워크는 오직 `customtkinter`를 사용하며, 기본 색상 테마 및 폰트 세팅은 가독성이 뛰어난 모던 Pretendard/Segoe UI 스택을 감지하여 활용하도록 구성해라.
2. 화면 레이아웃은 왼쪽에 토스(Toss) 스타일의 세련된 다크/그레이 네비게이션 사이드바가 존재하고, 오른쪽에 선택된 메뉴에 따라 콘텐츠 창(CTkScrollableFrame)이 격리 및 동적 전환되도록 설계해라.
3. 테마(System, Dark, Light)를 전환할 수 있는 직관적인 OptionMenu를 제공해라.

[Core Execution Constraints]
1. 네트워크 다운로드, 파일 가공, 압축/해제 등 메인 스레드를 멈추게 할 수 있는 무거운 연산은 반드시 `threading.Thread(daemon=True)`로 구동해라.
2. GUI 구성요소의 상태 변경이나 로그 추가는 스레드 안정성(Thread-Safety)을 보장하기 위해 무조건 `widget.after(0, lambda: ...)`를 통해 메인 이벤트 루프로 주입해야 한다.
3. 로직과 UI 인터페이스를 철저하게 격리(Decoupled)하기 위해, 핵심 기능은 GUI 컴포넌트 변수에 직접 손대지 않고 `log_callback(msg: str)`과 `progress_callback(percent: float)`을 인자로 받아 구동되도록 작성해라.

[Network Resilience Constraints]
1. 파일 다운로드 로직은 사내 프록시나 방화벽 보안 장비의 차단 정책에 유연하게 대응할 수 있도록 [Standard, System Certs, Trusted Host]의 3단계 SSL 우회 제어 구조를 적용해라.

[PyInstaller & Standalone Bundle Constraints]
1. 배포가 극도로 용이한 standalone .exe 단일 파일을 만들기 위해, 코드 내부에서 정적 자원이나 외부 리소스를 가리킬 때 `getattr(sys, 'frozen', False)`를 판단하여 `sys._MEIPASS` 혹은 `sys.executable` 디렉토리를 구동하도록 처리해라.
2. 컴파일러에 종속되지 않고 배포 효율성을 극대화할 수 있도록 `uv run` 일회성 가상 실행 명령을 기반으로 빌드하는 `compile.bat` 스크립트와 PyInstaller `.spec` 구조를 함께 제시해라.
```
