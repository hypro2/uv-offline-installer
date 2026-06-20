# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

**uvtool**은 폐쇄망(인터넷 차단 환경)에서 Python + uv를 설치하기 위한 2단계 GUI 툴킷입니다:

1. **Builder** (`builder_gui.py`) — 인터넷 연결된 PC에서 실행. uv, CPython standalone 바이너리, pip wheel 파일을 다운로드하여 오프라인 ZIP 패키지로 묶음.
2. **Installer** (`installer_gui.py`) — 폐쇄망 PC에서 실행. uv, Python, wheels를 설치하고 `UV_NO_INDEX` / `UV_FIND_LINKS` 환경 변수를 설정하여 `uv pip install`이 네트워크 없이 동작하도록 구성.

두 GUI 모두 PyInstaller로 독립 `.exe`로 컴파일됩니다. `builder_gui.exe`는 `installer_gui.exe`를 내부에 임베드하여 배포 파일을 단일화합니다.

## 앱 실행 (개발 환경)

```bash
# Builder GUI
uv run python builder_gui.py

# Installer GUI
uv run python installer_gui.py
```

## EXE 컴파일

`compile.bat` 실행 (PATH에 `uv`가 있어야 함):

```bat
compile.bat
```

spec 파일을 이용해 PyInstaller를 두 번 실행합니다:
1. `build/installer_gui.spec` → `dist/installer_gui.exe`
2. `build/builder_gui.spec` → `dist/builder_gui.exe` (installer_gui.exe 임베드)

`builder_gui.spec`이 installer_gui.exe를 리소스로 포함하므로 **반드시 installer_gui를 먼저 컴파일**해야 합니다.

## 아키텍처

```
builder_gui.py        # Tkinter UI — 빌드 폼, 스레딩, 진행 콜백
installer_gui.py      # Tkinter UI — 오프라인 설치 + 온라인 내보내기 모드
src/
  builder.py          # 핵심 빌드 로직: uv/Python/wheels 다운로드 → zip
  installer.py        # 핵심 설치 로직: zip 압축 해제 → PATH/환경 변수 등록
  utils.py            # 공통: download_file, extract_zip/tar_gz, Windows 레지스트리 헬퍼
  ps1_generator.py    # install_offline.ps1 스크립트 문자열 생성기 (빌드 시 zip에 포함)
```

### 핵심 설계 패턴

- **스레딩**: 장기 실행 작업은 모두 `threading.Thread(daemon=True)`에서 실행됩니다. UI 업데이트는 반드시 `root.after(0, lambda: ...)` 를 통해 메인 스레드로 전달합니다 — 워커 스레드에서 tkinter를 직접 호출하지 마십시오.
- **log_callback / progress_callback**: 핵심 함수(`build_package`, `install_offline`)는 UI에 독립적이며, 로그와 진행률(0–100 정수)을 위한 콜백 함수를 파라미터로 받습니다. GUI와 CLI 양쪽에서 동일한 로직을 재사용할 수 있습니다.
- **로컬 캐싱**: `build_package`는 반복 빌드 시 재다운로드를 방지하기 위해 워크스페이스 루트의 `cache/uv/`, `cache/python/`, `cache/pip/`에 다운로드 파일을 저장합니다. `cache/downloaded_wheels.json`은 wheel SHA-256 해시 레지스트리로, 증분("신규 패키지만") 패키징 모드에 사용됩니다.
- **PyInstaller frozen 감지**: GUI 파일 양쪽에서 `getattr(sys, 'frozen', False)`로 소스 실행 vs. 컴파일된 EXE를 구분하고, `sys._MEIPASS`로 임베드된 리소스 경로를 찾습니다.

### SSL 우회 모드

DPI 프록시 간섭 시 다운로드를 제어하는 3가지 모드:
- `standard` — 일반 urllib, SSL 검증 실패 시 무검증으로 자동 폴백
- `system_certs` — `ssl.create_default_context()` (OS 신뢰 저장소 사용)
- `trusted_host` — `ssl._create_unverified_context()` + pip `--trusted-host` 플래그

### Installer 모드 (installer_gui.py)

- **폐쇄망 모드** — 로컬 `payload/` 폴더에서 추출. 인터넷 불필요.
- **인터넷망/내보내기 모드** — GitHub에서 CPython standalone + uv를 다운로드한 후, 인스톨러 소스와 함께 USB 이동용 자체 실행 폴더로 패키징.

### 패키지 범위 (builder_gui.py)

- **전체(Full)** — uv 바이너리 + Python standalone + 모든 wheels 포함
- **증분(Incremental)** — uv/Python 제외; `downloaded_wheels.json`에 없는 신규/변경 wheels만 포함

### Linux 빌드 지원

`builder.py`의 `is_docker_available()`이 Docker 데몬 실행 여부를 확인합니다. Linux 대상 빌드 시 Docker가 있으면 컨테이너 환경에서 wheels를 다운로드하여 `manylinux` 호환성을 보장합니다.

### install_offline.ps1 생성

`src/ps1_generator.py`는 ZIP 패키지에 포함할 `install_offline.ps1` 내용을 문자열로 반환합니다. `source_dir` / `install_dir`를 파라미터 기본값으로 굽는(bake) 방식으로, 더블클릭만으로 폐쇄망 PC에서 설치가 완료됩니다.

### 지원 Python 버전

`builder.py`의 `PYTHON_VERSION_MAP`에 정의된 버전을 사용합니다 (pbp tag `20260610` 기준):

| major.minor | 실제 설치 버전 |
|-------------|--------------|
| 3.9  | 3.9.21  |
| 3.10 | 3.10.16 |
| 3.11 | 3.11.11 |
| 3.12 | 3.12.8  |
| 3.13 | 3.13.1  |
