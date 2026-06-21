# uv-offline-installer — 폐쇄망 Python + uv 설치 툴킷

> 인터넷이 차단된 환경(망분리, 폐쇄망, 에어갭)에서  
> **uv + Python + pip 패키지**를 단 한 번의 클릭으로 설치할 수 있는 GUI 툴킷입니다.

---

## 왜 uv-offline-installer인가?

폐쇄망 PC에 Python 환경을 구축하려면 보통 이런 고통이 따릅니다.

- USB로 파일을 일일이 복사
- pip install이 인터넷 없이 안 됨
- Python 설치 경로, PATH, 환경변수를 수동으로 설정
- 버전이 바뀔 때마다 처음부터 반복

uv-offline-installer은 이 과정을 **Builder → ZIP → Installer** 3단계로 완전 자동화합니다.

---

## 구성

| 도구 | 역할 |
|------|------|
| `builder_gui.exe` | 인터넷 PC에서 실행. uv + Python + wheels를 묶어 오프라인 ZIP 패키지 생성 |
| `installer_gui.exe` | 폐쇄망 PC에서 실행. ZIP을 풀고 PATH·환경변수까지 자동 설정 |
| `install_offline.ps1` | 빌드 시 ZIP 안에 자동 생성. `irm https://astral.sh/uv/install.ps1 \| iex` 의 폐쇄망 대체 스크립트 |

> `builder_gui.exe` 하나에 `installer_gui.exe`가 내장되어 있습니다.  
> 배포 시 `builder_gui.exe` 파일 하나만 전달하면 됩니다.

---

## 사용 방법

### Step 1 — 인터넷 PC에서 패키지 빌드 (`builder_gui.exe`)

1. `builder_gui.exe` 실행
2. 설정 입력
   - **대상 OS / 아키텍처** : Windows / Linux, x86_64 / ARM64
   - **Python 버전** : 3.9 ~ 3.13 중 복수 선택 가능
   - **pip 패키지** : `requirements.txt` 형식으로 입력 (예: `numpy`, `pandas>=2.0`)
   - **패키지 범위** : 전체(Full) 또는 신규만(Incremental)
   > Linux 대상 빌드 시 Docker가 실행 중이면 컨테이너 환경을 활용하여 `manylinux` 호환 wheels를 다운로드합니다.
3. **오프라인 설치 팩 생성** 클릭
4. 생성된 `.zip` 파일을 USB 등으로 폐쇄망 PC에 이동

### Step 2 — 폐쇄망 PC에서 설치 (`installer_gui.exe` 또는 `install_offline.ps1`)

**방법 A — GUI 설치 (권장)**

1. ZIP 압축 해제 후 `installer_gui.exe` 실행
2. 패키지 경로, 설치 경로 확인 후 **오프라인 설치** 클릭
3. 완료 후 새 터미널에서 확인:
   ```powershell
   uv --version
   python --version
   uv pip install 패키지명   # 인터넷 없이 동작
   ```

**방법 B — PowerShell 스크립트**

```powershell
powershell -ExecutionPolicy Bypass -File install_offline.ps1
```

> `install_offline.ps1`은 공식 uv 설치 명령  
> `irm https://astral.sh/uv/install.ps1 | iex` 의 **완전한 오프라인 대체품**입니다.

---

## 주요 기능

### 패키지 범위 선택

| 모드 | 설명 | 용도 |
|------|------|------|
| **전체(Full)** | uv + Python + 모든 wheels 포함 | 최초 설치 |
| **증분(Incremental)** | 신규/변경 wheels만 포함 | 패키지 업데이트 |

증분 모드를 사용하면 ZIP 용량을 수십 MB 이하로 줄여 망연계 전송 한도(2GB)를 쉽게 통과할 수 있습니다.

### SSL / 보안망 우회

DPI 프록시, SSL 감시 장비가 있는 환경을 위해 3가지 다운로드 모드를 지원합니다.

| 모드 | 설명 |
|------|------|
| Standard | 기본 HTTPS, 실패 시 자동 무검증 재시도 |
| System Certs | OS 신뢰 저장소 인증서 사용 |
| Trusted Host | SSL 검증 없이 강제 신뢰 (최후 수단) |

### 인터넷망 내보내기 모드

인터넷망 PC에서 `installer_gui.exe`의 **인터넷망 모드** 탭을 사용하면,  
CPython Standalone + uv 바이너리를 다운로드하여 USB 이동용 폴더를 자동 생성합니다.  
`run_installer.bat` 한 번으로 폐쇄망 PC에서 실행 가능합니다.

### 폐쇄망에서 pyproject.toml 및 uv.lock 기반 동기화 (uv sync)

빌더 단계에서 프로젝트 디렉토리(`pyproject.toml` 및 `uv.lock`이 위치한 경로)를 지정하고 빌드하면, 해당 프로젝트에서 요구하는 Python standalone 바이너리와 필요한 모든 오프라인 wheels 패키지가 압축 팩에 번들링됩니다.

폐쇄망 PC에서 해당 프로젝트의 가상환경을 구축하고 동일하게 싱크하려면 다음 명령을 수동으로 수행합니다.

1. **CPython standalone 인터프리터를 사용하여 가상환경(venv) 생성**:
   ```powershell
   # 설치된 CPython standalone 절대 경로를 지정하여 가상환경을 생성합니다.
   # (예: C:\Users\<사용자명>\.local\python\3.11\python.exe)
   uv venv --python <설치경로>/python/<버전>/python.exe
   ```

2. **오프라인 휠 라이브러리를 참조하여 프로젝트 패키지 동기화**:
   ```powershell
   # 가상환경이 생성된 프로젝트 폴더 내에서 실행합니다.
   # --offline: 네트워크 통신 완전 차단
   # --no-index: PyPI 인덱스 조회 배제
   # --find-links: 반입된 wheels 폴더 경로를 패키지 소스로 사용
   uv sync --offline --no-index --find-links <설치경로>/wheels
   ```

---

## 설치 후 환경 구성

설치 완료 시 아래 설정이 자동 적용됩니다.

```
사용자 PATH   ← uv.exe 경로, python.exe 경로 추가
UV_NO_INDEX=1         ← PyPI 인터넷 조회 차단
UV_FIND_LINKS=<경로>  ← 로컬 wheels 폴더를 패키지 소스로 등록
```

환경변수 등록을 원하지 않는 경우, 프로젝트별 `uv.toml` 파일을 대신 생성합니다.

```toml
[pip]
no-index = true
find-links = ["C:/Users/.local/bin/wheels"]
```

---

## 개발 환경 실행

```bash
# Builder
uv run python builder_gui.py

# Installer
uv run python installer_gui.py
```

## EXE 컴파일

```bat
compile.bat
```

컴파일 순서: `build/installer_gui.spec` → `build/builder_gui.spec` (installer 내장)

---

## 지원 플랫폼

| 빌더 실행 환경 | 설치 대상 |
|---------------|----------|
| Windows 10/11 | Windows x86_64, Windows ARM64 |
| Windows 10/11 | Linux x86_64, Linux ARM64 (Docker 또는 교차 다운로드) |

## 지원 Python 버전

Python 3.9 ~ 3.13을 지원합니다 ([python-build-standalone](https://github.com/astral-sh/python-build-standalone) 기반).

| 버전 | 설치되는 릴리스 |
|------|----------------|
| 3.9  | 3.9.21  |
| 3.10 | 3.10.16 |
| 3.11 | 3.11.11 |
| 3.12 | 3.12.8  |
| 3.13 | 3.13.1  |

---

## 라이선스

MIT License

본 프로젝트는 [astral-sh/uv](https://github.com/astral-sh/uv) 및 [astral-sh/python-build-standalone](https://github.com/astral-sh/python-build-standalone)을 활용합니다. (Apache 2.0 / MIT)
