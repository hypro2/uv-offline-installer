import datetime
import hashlib
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import traceback
import urllib.request
import zipfile
from typing import Any, Callable, Dict, List, Optional, Tuple

from .utils import download_file

# Mapping of major.minor to latest CPython patch version for python-build-standalone tag 20260610
PYTHON_VERSION_MAP = {
    "3.9": "3.9.21",
    "3.10": "3.10.16",
    "3.11": "3.11.11",
    "3.12": "3.12.8",
    "3.13": "3.13.1"
}

PBP_TAG = "20260610"

def detect_project_settings(project_path: str) -> Dict[str, Any]:
    """
    지정된 프로젝트 경로(project_path)의 설정을 분석합니다.
    1. 최우선 순위로 `.python-version` 파일을 확인하여 Python 버전을 추출합니다.
    2. `.python-version`이 없을 경우 `pyproject.toml` 파일의 `requires-python` 속성을 해석합니다.
    3. `uv.lock` 파일 존재 여부를 확인하여 의존성 동기화 필요 여부를 감지합니다.

    Args:
        project_path (str): 분석할 프로젝트의 루트 디렉토리 절대 경로.

    Returns:
        Dict[str, Any]: {"python_versions": Optional[List[str]], "has_uv_lock": bool} 형태의 딕셔너리.
    """
    py_ver = None
    
    # 1. Check .python-version
    python_version_file = os.path.join(project_path, ".python-version")
    if os.path.exists(python_version_file):
        try:
            with open(python_version_file, "r", encoding="utf-8") as f:
                ver_str = f.read().strip()
            # major.minor 버전만 추출 (예: "3.12.3" -> "3.12")
            m = re.match(r'^(\d+\.\d+)', ver_str)
            if m:
                py_ver = [m.group(1)]
        except Exception:
            pass
            
    # 2. Check pyproject.toml if .python-version wasn't found or was invalid
    if not py_ver:
        toml_path = os.path.join(project_path, "pyproject.toml")
        if os.path.exists(toml_path):
            try:
                with open(toml_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    
                match = re.search(r'requires-python\s*=\s*["\']([^"\']+)["\']', content)
                if match:
                    constraint = match.group(1)
                    found_vers = []
                    for v in ["3.9", "3.10", "3.11", "3.12", "3.13"]:
                        # Support multiple comma-separated constraints, e.g., ">=3.12,<3.14"
                        parts = [p.strip() for p in constraint.split(",")]
                        satisfied = True
                        for part in parts:
                            match_op = re.match(r'^([>=<~!]+)?\s*(\d+\.\d+)', part)
                            if match_op:
                                op, ver_num = match_op.groups()
                                op = op or "=="
                                try:
                                    v_num = float(v)
                                    ref_num = float(ver_num)
                                    if op == ">=":
                                        if not (v_num >= ref_num): satisfied = False
                                    elif op == ">":
                                        if not (v_num > ref_num): satisfied = False
                                    elif op == "==":
                                        if not (v_num == ref_num): satisfied = False
                                    elif op == "~=":
                                        if not (v_num >= ref_num and int(v_num) == int(ref_num)): satisfied = False
                                    elif op == "<=":
                                        if not (v_num <= ref_num): satisfied = False
                                    elif op == "<":
                                        if not (v_num < ref_num): satisfied = False
                                except ValueError:
                                    pass
                        if satisfied:
                            found_vers.append(v)
                    if found_vers:
                        py_ver = found_vers
            except Exception:
                pass
        
    return {
        "python_versions": py_ver,
        "has_uv_lock": os.path.exists(os.path.join(project_path, "uv.lock"))
    }

def get_platform_info(target_os: str, target_arch: str) -> Dict[str, str]:
    """
    지정된 대상 OS 및 아키텍처에 기반한 빌드 및 설치용 플랫폼 상세 정보를 반환합니다.

    Args:
        target_os (str): 대상 운영체제 ("windows" 또는 "linux").
        target_arch (str): 대상 아키텍처 ("x86_64" 또는 "aarch64").

    Returns:
        Dict[str, str]: uv 아카이브 확장자(uv_ext), uv 트리플(uv_triple), python 트리플(pbp_triple), pip 플랫폼(pip_platform)을 포함하는 정보 딕셔너리.
    """
    info = {}
    if target_os == "windows":
        info["uv_ext"] = "zip"
        if target_arch == "x86_64":
            info["uv_triple"] = "x86_64-pc-windows-msvc"
            info["pbp_triple"] = "x86_64-pc-windows-msvc"
            info["pip_platform"] = "win_amd64"
        else:  # aarch64
            info["uv_triple"] = "aarch64-pc-windows-msvc"
            info["pbp_triple"] = "aarch64-pc-windows-msvc"
            info["pip_platform"] = "win_arm64"
    else:  # linux
        info["uv_ext"] = "tar.gz"
        if target_arch == "x86_64":
            info["uv_triple"] = "x86_64-unknown-linux-gnu"
            info["pbp_triple"] = "x86_64-unknown-linux-gnu"
            info["pip_platform"] = "manylinux2014_x86_64"
        else:  # aarch64
            info["uv_triple"] = "aarch64-unknown-linux-gnu"
            info["pbp_triple"] = "aarch64-unknown-linux-gnu"
            info["pip_platform"] = "manylinux2014_aarch64"
    return info

def is_docker_available() -> bool:
    """
    시스템에 Docker 명령어가 설치되어 있고 데몬이 기동 중인지 확인합니다.

    Returns:
        bool: Docker 사용 가능 시 True, 불가능 시 False 반환.
    """
    if not shutil.which("docker"):
        return False
    try:
        res = subprocess.run(["docker", "info"], capture_output=True, timeout=3, text=True)
        return res.returncode == 0
    except Exception:
        return False

def get_python_asset_url(
    py_ver: str,
    plat: Dict[str, str],
    log_callback: Callable[[str], None],
    stripped: bool = False
) -> Tuple[str, str]:
    """
    python-build-standalone 리포지토리의 최신 릴리스에서 플랫폼에 최적화된 Python 배포판 다운로드 URL을 탐색합니다.
    GitHub API를 우선 호출하고, API 호출 횟수 초과(Rate Limit) 등의 실패 시 안정적인 fallback 버전을 반환합니다.

    Args:
        py_ver (str): 대상 파이썬 메이저.마이너 버전 (예: "3.11").
        plat (Dict[str, str]): get_platform_info의 결과 플랫폼 정보 딕셔너리.
        log_callback (Callable[[str], None]): 로그 출력 콜백 함수.
        stripped (bool, optional): 임베디드용 가벼운 빌드(stripped) 여부. Defaults to False.

    Returns:
        Tuple[str, str]: (다운로드 URL, 아카이브파일명) 튜플.
    """
    suffix = "install_only_stripped.tar.gz" if stripped else "install_only.tar.gz"
    
    # Try GitHub API first (latest release)
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest",
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        
        # Try normal connection, then fallback to unverified SSL context
        try:
            response = urllib.request.urlopen(req, timeout=5)
        except Exception:
            insecure_context = ssl._create_unverified_context()
            response = urllib.request.urlopen(req, timeout=5, context=insecure_context)
            
        with response:
            data = json.loads(response.read().decode('utf-8'))
            assets = data.get('assets', [])
            
            triple = plat['pbp_triple']
            for asset in assets:
                name = asset['name']
                if name.startswith(f"cpython-{py_ver}.") and triple in name and suffix in name:
                    return asset['browser_download_url'], name
    except Exception as e:
        log_callback(f"[WARNING] GitHub API를 통한 최신 standalone Python 탐색 실패 ({e}). Fallback 매핑을 사용합니다.")
        log_callback("[INFO] 하드코딩된 fallback 버전을 사용합니다.")
          
    # Fallback mapping if API fails or for Python 3.9 (which is omitted in 20260610 tag)
    fallback = {
        "3.9": ("20241016", "3.9.20"),
        "3.10": ("20260610", "3.10.20"),
        "3.11": ("20260610", "3.11.15"),
        "3.12": ("20260610", "3.12.13"),
        "3.13": ("20260610", "3.13.14")
    }
    
    if py_ver not in fallback:
        tag = "20260610"
        exact_ver = f"{py_ver}.0"
    else:
        tag, exact_ver = fallback[py_ver]
        
    archive_name = f"cpython-{exact_ver}+{tag}-{plat['pbp_triple']}-{suffix}"
    url = f"https://github.com/astral-sh/python-build-standalone/releases/download/{tag}/{archive_name}"
    return url, archive_name

def build_package(
    target_os: str,
    target_arch: str,
    uv_version: str,
    python_versions: List[str],
    pip_packages: List[str],
    output_zip_path: str,
    log_callback: Callable[[str], None],
    progress_callback: Callable[[int], None],
    package_scope: str = "all",
    ssl_bypass: str = "standard",
    project_path: Optional[str] = None
) -> bool:
    """
    uv 실행 바이너리, 독립형 Python 실행본 tarball, 지정된 라이브러리 wheel 파일들을 포함하는
    폐쇄망 오프라인 설치 패키지 압축파일(.zip)을 생성합니다.
    불필요한 다운로드를 줄이기 위해 로컬 `cache/` 디렉토리를 활용하여 다운로드 파일을 캐싱합니다.

    Args:
        target_os (str): 대상 운영체제 ("windows", "linux").
        target_arch (str): 대상 아키텍처 ("x86_64", "aarch64").
        uv_version (str): 빌드에 동봉할 uv 버전 정보.
        python_versions (List[str]): 포함할 Python 버전 목록.
        pip_packages (List[str]): 추가로 반입할 pip 패키지 목록.
        output_zip_path (str): 결과물 zip 파일의 저장 경로.
        log_callback (Callable[[str], None]): 빌드 진행 과정 로그 수신 콜백 함수.
        progress_callback (Callable[[int], None]): 진행율 퍼센트 수신 콜백 함수.
        package_scope (str, optional): 휠 수집 대상 범위 ("all", "new_only"). Defaults to "all".
        ssl_bypass (str, optional): SSL 필터 우회 수준 ("standard", "trusted_host", "system_certs"). Defaults to "standard".
        project_path (Optional[str], optional): 로컬 동기화 프로젝트 디렉토리 경로. Defaults to None.

    Returns:
        bool: 패키지 빌드 최종 성공 시 True 반환.
    """
    # Workspace and Cache Paths
    workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_dir = os.path.join(workspace_dir, "cache")
    uv_cache_dir = os.path.join(cache_dir, "uv")
    py_cache_dir = os.path.join(cache_dir, "python")
    pip_cache_dir = os.path.join(cache_dir, "pip")
    
    os.makedirs(uv_cache_dir, exist_ok=True)
    os.makedirs(py_cache_dir, exist_ok=True)
    os.makedirs(pip_cache_dir, exist_ok=True)
    
    # Create temporary build folder
    temp_dir = os.path.join(workspace_dir, "temp_pkg_build")
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    payload_dir = os.path.join(temp_dir, "payload")
    os.makedirs(payload_dir)
    
    # 1. Platform Resolution
    plat = get_platform_info(target_os, target_arch)
    log_callback(f"[INFO] 타겟 플랫폼: OS={target_os.upper()}, Arch={target_arch}")
    
    try:
        # 2. Process uv binary (with caching)
        progress_callback(10)
        uv_archive_name = f"uv-{plat['uv_triple']}.{plat['uv_ext']}"
        uv_cache_path = os.path.join(uv_cache_dir, f"{uv_version}_{uv_archive_name}")
        uv_dest = os.path.join(payload_dir, uv_archive_name)
        
        if package_scope == "all":
            if os.path.exists(uv_cache_path) and os.path.getsize(uv_cache_path) > 0:
                log_callback(f"[CACHE] 로컬 캐시에서 uv 바이너리를 발견하여 복사합니다: {uv_archive_name}")
                shutil.copy2(uv_cache_path, uv_dest)
            else:
                if uv_version == "latest":
                    uv_url = f"https://github.com/astral-sh/uv/releases/latest/download/{uv_archive_name}"
                else:
                    uv_url = f"https://github.com/astral-sh/uv/releases/download/{uv_version}/{uv_archive_name}"
                    
                log_callback(f"[DOWNLOAD] 캐시에 파일이 없어 새로 다운로드합니다. ({uv_url})")
                download_file(uv_url, uv_cache_path, status_callback=log_callback, ssl_bypass=ssl_bypass)
                shutil.copy2(uv_cache_path, uv_dest)
                log_callback(f"[SUCCESS] uv 바이너리 다운로드 완료 및 캐싱: {uv_archive_name}")
        else:
            log_callback("[INFO] 증분 패키징 모드: uv 바이너리 패키징을 생략합니다.")
            
        # 3. Process Python Standalone builds (with caching)
        progress_callback(30)
        py_dir = os.path.join(payload_dir, "python")
        os.makedirs(py_dir)
        
        if package_scope == "all":
            for idx, py_ver in enumerate(python_versions):
                # Resolve URL and Archive name dynamically
                pbp_url, pbp_archive_name = get_python_asset_url(py_ver, plat, log_callback, stripped=False)
                pbp_cache_path = os.path.join(py_cache_dir, pbp_archive_name)
                pbp_dest = os.path.join(py_dir, pbp_archive_name)
                
                if os.path.exists(pbp_cache_path) and os.path.getsize(pbp_cache_path) > 0:
                    log_callback(f"[CACHE] 로컬 캐시에서 Python {py_ver} standalone 바이너리를 발견하여 복사합니다.")
                    shutil.copy2(pbp_cache_path, pbp_dest)
                else:
                    log_callback(f"[DOWNLOAD] 캐시에 파일이 없어 새로 다운로드합니다. ({pbp_url})")
                    try:
                        download_file(pbp_url, pbp_cache_path, status_callback=log_callback, ssl_bypass=ssl_bypass)
                        shutil.copy2(pbp_cache_path, pbp_dest)
                        log_callback(f"[SUCCESS] Python {py_ver} 다운로드 완료 및 캐싱.")
                    except Exception as e:
                        log_callback(f"[WARNING] Python {py_ver} 다운로드 실패: {e}. 다른 빌드 형식(stripped)으로 재시도...")
                        
                        # Retry with stripped
                        pbp_url_s, pbp_archive_name_s = get_python_asset_url(py_ver, plat, log_callback, stripped=True)
                        pbp_cache_path_s = os.path.join(py_cache_dir, pbp_archive_name_s)
                        pbp_dest_s = os.path.join(py_dir, pbp_archive_name_s)
                        
                        if os.path.exists(pbp_cache_path_s) and os.path.getsize(pbp_cache_path_s) > 0:
                            log_callback(f"[CACHE] 로컬 캐시에서 Python {py_ver} (stripped) 바이너리를 발견하여 복사합니다.")
                            shutil.copy2(pbp_cache_path_s, pbp_dest_s)
                        else:
                            log_callback(f"[DOWNLOAD] stripped Python 다운로드 중: {pbp_url_s}")
                            download_file(pbp_url_s, pbp_cache_path_s, status_callback=log_callback, ssl_bypass=ssl_bypass)
                            shutil.copy2(pbp_cache_path_s, pbp_dest_s)
                            log_callback(f"[SUCCESS] Python {py_ver} (stripped) 다운로드 완료 및 캐싱.")
        else:
            log_callback("[INFO] 증분 패키징 모드: Python Standalone 인터프리터 패키징을 생략합니다.")
                        
        # 4. Download PIP Package wheels (with caching & new file tracking)
        progress_callback(60)
        has_project = bool(project_path and os.path.exists(os.path.join(project_path, "pyproject.toml")))
        if pip_packages or has_project:
            wheels_dir = os.path.join(payload_dir, "wheels")
            os.makedirs(wheels_dir)
            
            if has_project:
                log_callback("[INFO] 프로젝트 설정 감지: pyproject.toml 및 uv.lock(있는 경우)을 수집 소스로 사용합니다.")
            else:
                log_callback(f"[INFO] PIP 패키지 {len(pip_packages)}개 수집 및 의존성 다운로드 시작...")
            
            # Helper to calculate SHA-256 hash of a file
            def calculate_sha256(filepath):
                sha256_hash = hashlib.sha256()
                with open(filepath, "rb") as f:
                    for byte_block in iter(lambda: f.read(4096), b""):
                        sha256_hash.update(byte_block)
                return sha256_hash.hexdigest()

            # Load the global wheel download registry
            registry_file = os.path.join(cache_dir, "downloaded_wheels.json")
            wheel_registry = {}
            if os.path.exists(registry_file):
                try:
                    with open(registry_file, "r", encoding="utf-8") as f:
                        wheel_registry = json.load(f)
                except Exception as e:
                    log_callback(f"[WARNING] 휠 레지스트리 파일을 읽는 데 실패했습니다: {e}. 새로 생성합니다.")
            
            # Write packages to temporary requirements.txt or compile pyproject.toml/uv.lock
            req_file_path = os.path.join(temp_dir, "requirements.txt")
            docker_req_path = "/temp/requirements.txt"
            
            if has_project:
                has_lock = os.path.exists(os.path.join(project_path, "uv.lock"))
                if has_lock:
                    log_callback("[INFO] uv.lock 파일이 감지되어 uv export를 통해 requirements.txt를 내보냅니다.")
                    compile_cmd = ["uv", "export", "--no-hashes", "-o", req_file_path]
                else:
                    log_callback("[INFO] pyproject.toml 파일을 분석하여 requirements.txt를 컴파일 중...")
                    compile_cmd = ["uv", "pip", "compile", "pyproject.toml", "-o", req_file_path]
                
                # Apply SSL configurations to compilation environment if needed
                compile_env = os.environ.copy()
                if ssl_bypass == "system_certs":
                    compile_env["UV_SYSTEM_CERTS"] = "1"
                    compile_env["UV_NATIVE_TLS"] = "1"
                    compile_cmd.append("--system-certs")
                elif ssl_bypass == "trusted_host":
                    compile_env["UV_INSECURE"] = "1"
                    # Do not append "--insecure" since it is not a valid uv argument
                
                # Run uv pip compile / uv export
                try:
                    res = subprocess.run(compile_cmd, env=compile_env, cwd=project_path, capture_output=True, text=True, check=True)
                    log_callback("[SUCCESS] 프로젝트 의존성 컴파일 완료.")
                except subprocess.CalledProcessError as compile_err:
                    log_callback(f"[ERROR] 프로젝트 의존성 컴파일 실패: {compile_err.stderr}")
                    raise compile_err
            else:
                with open(req_file_path, "w", encoding="utf-8") as rf:
                    for pkg in pip_packages:
                        rf.write(f"{pkg}\n")
                    
            for py_ver in python_versions:
                log_callback(f"[INFO] Python {py_ver} 버전에 맞는 wheel 패키지 분석 및 다운로드 중 (캐시 활용)...")
                
                # Check if Docker should be used for Linux target
                use_docker = (target_os == "linux" and is_docker_available())
                
                if use_docker:
                    log_callback("[INFO] Docker 가용 상태가 감지되었습니다. 리눅스 휠 빌드를 위해 Docker 컨테이너를 구동합니다. (sdist 자동 컴파일)")
                    abs_wheels_dir = os.path.abspath(wheels_dir)
                    abs_temp_dir = os.path.abspath(temp_dir)
                    abs_pip_cache = os.path.abspath(pip_cache_dir)
                    
                    vol_wheels = abs_wheels_dir.replace("\\", "/")
                    vol_temp = abs_temp_dir.replace("\\", "/")
                    vol_cache = abs_pip_cache.replace("\\", "/")
                    
                    image_tag = f"python:{py_ver}-slim"
                    
                    # Use 'pip wheel' inside docker container to automatically compile sdist to whl
                    container_cmd = [
                        "pip", "wheel",
                        "--wheel-dir", "/wheels",
                        "--cache-dir", "/cache",
                        "-r", docker_req_path
                    ]
                    
                    if ssl_bypass == "system_certs" or ssl_bypass == "trusted_host":
                        log_callback("[WARNING] Docker 내부 빌드 시 OS 신뢰 저장소 옵션이 제한되므로, 도메인 신뢰 강제(--trusted-host) 방식으로 우회 다운로드합니다.")
                        container_cmd.extend([
                            "--trusted-host", "pypi.org",
                            "--trusted-host", "files.pythonhosted.org",
                            "--trusted-host", "pypi.python.org"
                        ])
                        
                    cmd = [
                        "docker", "run", "--rm",
                        "-v", f"{vol_wheels}:/wheels",
                        "-v", f"{vol_temp}:/temp",
                        "-v", f"{vol_cache}:/cache",
                        image_tag
                    ] + container_cmd
                    
                    sub_env = os.environ.copy()
                else:
                    host_os = "windows" if sys.platform == "win32" else "linux"
                    if target_os == host_os:
                        log_callback(f"[INFO] 호스트 OS와 타겟 OS가 일치하여, Python {py_ver} 환경에서 직접 휠 빌드(pip wheel)를 실행합니다. (sdist 자동 컴파일)")
                        cmd = [
                            "uv", "run", "--python", py_ver, "--with", "pip", "python", "-m", "pip", "wheel",
                            "--wheel-dir", wheels_dir,
                            "--cache-dir", pip_cache_dir,
                            "-r", req_file_path
                        ]
                        
                        sub_env = os.environ.copy()
                        
                        if ssl_bypass == "system_certs":
                            log_callback("[INFO] SSL 우회: OS 신뢰 저장소(System Certs) 인증 수단을 적용합니다.")
                            sub_env["UV_SYSTEM_CERTS"] = "1"
                            sub_env["UV_NATIVE_TLS"] = "1"
                            cmd.append("--use-feature=truststore")
                        elif ssl_bypass == "trusted_host":
                            log_callback("[INFO] SSL 우회: PyPI 주요 도메인을 강제 신뢰(--trusted-host)합니다.")
                            sub_env["UV_INSECURE"] = "1"
                            cmd.extend([
                                "--trusted-host", "pypi.org",
                                "--trusted-host", "files.pythonhosted.org",
                                "--trusted-host", "pypi.python.org"
                            ])
                        else:
                            log_callback("[INFO] SSL 우회: 표준 다운로드 모드를 사용합니다.")
                    else:
                        if target_os == "linux":
                            log_callback("[WARNING] 리눅스 타겟 빌드이나 Docker를 사용할 수 없습니다. 윈도우 호스트에서 교차 다운로드(Cross-platform)를 실행합니다.")
                        abi_tag = f"cp{py_ver.replace('.', '')}"
                        cmd = [
                            "uv", "run", "--with", "pip", "python", "-m", "pip", "download",
                            "--only-binary=:all:",
                            "--dest", wheels_dir,
                            "--cache-dir", pip_cache_dir,
                            "--platform", plat["pip_platform"],
                            "--python-version", py_ver,
                            "--implementation", "cp",
                            "--abi", abi_tag,
                            "-r", req_file_path
                        ]
                        
                        sub_env = os.environ.copy()
                        
                        if ssl_bypass == "system_certs":
                            log_callback("[INFO] SSL 우회: OS 신뢰 저장소(System Certs) 인증 수단을 적용합니다.")
                            sub_env["UV_SYSTEM_CERTS"] = "1"
                            sub_env["UV_NATIVE_TLS"] = "1"
                            cmd.append("--use-feature=truststore")
                        elif ssl_bypass == "trusted_host":
                            log_callback("[INFO] SSL 우회: PyPI 주요 도메인을 강제 신뢰(--trusted-host)합니다.")
                            sub_env["UV_INSECURE"] = "1"
                            cmd.extend([
                                "--trusted-host", "pypi.org",
                                "--trusted-host", "files.pythonhosted.org",
                                "--trusted-host", "pypi.python.org"
                            ])
                        else:
                            log_callback("[INFO] SSL 우회: 표준 다운로드 모드를 사용합니다.")
                
                log_callback(f"[CMD] {' '.join(cmd)}")
                
                # Execute and read stdout line-by-line
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    env=sub_env
                )
                
                while True:
                    line = process.stdout.readline()
                    if not line:
                        break
                    line_str = line.strip()
                    if line_str:
                        # Translate caching feedback to user-friendly logs
                        if "Using cached" in line_str:
                            log_callback(f"  [CACHE] {line_str}")
                        else:
                            log_callback(f"  [pip] {line_str}")
                        
                process.wait()
                if process.returncode == 0:
                    log_callback(f"[SUCCESS] Python {py_ver} 용 패키지 라이브러리 수집 완료.")
                else:
                    log_callback(f"[ERROR] Python {py_ver} 용 패키지 수집 중 경고/에러가 발생했습니다 (코드: {process.returncode}).")
                    raise RuntimeError(f"Python {py_ver} 용 패키지 수집에 실패했습니다. (코드: {process.returncode})")
            
            # Scan wheels_dir and compare with registry
            newly_downloaded_wheels = []
            current_wheels = {}
            
            if os.path.exists(wheels_dir):
                for file in os.listdir(wheels_dir):
                    if file.endswith('.whl'):
                        file_path = os.path.join(wheels_dir, file)
                        file_hash = calculate_sha256(file_path)
                        current_wheels[file] = file_hash
                        
                        # If this wheel is not in the registry or has a different hash, it's new/changed!
                        if file not in wheel_registry or wheel_registry[file] != file_hash:
                            newly_downloaded_wheels.append((file, file_path))
            
            # If package_scope is "new", delete wheels that were not newly downloaded
            if package_scope == "new" and os.path.exists(wheels_dir):
                newly_downloaded_set = {f[0] for f in newly_downloaded_wheels}
                for file in os.listdir(wheels_dir):
                    if file.endswith('.whl') and file not in newly_downloaded_set:
                        try:
                            os.remove(os.path.join(wheels_dir, file))
                            log_callback(f"  [CLEAN] 기존 캐시 휠 삭제 (증분 압축 제외): {file}")
                        except Exception as e:
                            log_callback(f"[WARNING] 기존 캐시 휠 삭제 실패: {file} ({e})")
            
            # Copy newly downloaded wheels to separate folder
            if newly_downloaded_wheels:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                new_pkgs_dir_name = f"new_packages_{timestamp}"
                output_parent = os.path.dirname(os.path.abspath(output_zip_path))
                new_pkgs_dir = os.path.join(output_parent, new_pkgs_dir_name)
                
                os.makedirs(new_pkgs_dir, exist_ok=True)
                log_callback(f"[INFO] 이번 실행에서 새로 추가되거나 변경된 패키지 {len(newly_downloaded_wheels)}개를 감지했습니다.")
                log_callback(f"[INFO] 신규/변경 패키지들을 별도 폴더에 복사합니다: {new_pkgs_dir_name}")
                
                for filename, src_path in newly_downloaded_wheels:
                    dest_path = os.path.join(new_pkgs_dir, filename)
                    shutil.copy2(src_path, dest_path)
                    log_callback(f"  -> 복사됨: {filename}")
                log_callback(f"[SUCCESS] 신규/변경 패키지 분리 저장 완료: {new_pkgs_dir}")
            else:
                log_callback("[INFO] 이번 실행에서 새로 추가되거나 변경된 패키지가 없습니다 (모든 패키지가 캐시 레지스트리에 존재함).")
                
            # Update and save the global registry
            if current_wheels:
                wheel_registry.update(current_wheels)
                try:
                    with open(registry_file, "w", encoding="utf-8") as f:
                        json.dump(wheel_registry, f, indent=4, ensure_ascii=False)
                    log_callback("[INFO] 다운로드 휠 레지스트리(downloaded_wheels.json)를 업데이트했습니다.")
                except Exception as e:
                    log_callback(f"[WARNING] 휠 레지스트리 저장 실패: {e}")

        # 5. Packaging Wheels Only
        progress_callback(85)
        log_callback("[INFO] 압축 팩에 포함될 최종 수집 및 컴파일된 휠(*.whl) 패키지 목록:")
        wheel_list = []
        if os.path.exists(wheels_dir):
            for file in sorted(os.listdir(wheels_dir)):
                if file.endswith('.whl'):
                    wheel_list.append(file)
                    log_callback(f"  -> [수집됨] {file}")
            
        # 6. Compress wheels directly to the root of output_zip_path
        progress_callback(90)
        log_callback(f"[INFO] 최종 오프라인 패키지 압축 파일 작성 중 (포함된 휠 개수: {len(wheel_list)}개): {os.path.basename(output_zip_path)}")
        
        # Ensure target folder exists
        os.makedirs(os.path.dirname(os.path.abspath(output_zip_path)), exist_ok=True)
        
        with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in wheel_list:
                file_path = os.path.join(wheels_dir, file)
                zipf.write(file_path, file)
                    
        progress_callback(100)
        log_callback(f"[SUCCESS] 오프라인 동기화용 패키지 빌드 완료 (저장 경로: {output_zip_path})")
        
        # Check size for 2GB corporate proxy / network transmission limits
        zip_size = os.path.getsize(output_zip_path)
        limit_2gb = 2 * 1024 * 1024 * 1024  # 2GB in bytes
        size_warning = False
        if zip_size > limit_2gb:
            size_warning = True
            log_callback(f"[WARNING] 🚨 최종 패키지 용량 ({zip_size / (1024*1024*1024):.2f} GB)이 망연계 전송 한도(2GB)를 초과합니다.")
            log_callback("[WARNING] 💡 해결 방안:")
            log_callback("  1. '신규 패키지만 압축 (Incremental)' 옵션을 사용하여 휠 파일 크기만 묶어 전송하십시오.")
            log_callback("  2. 파이썬 버전을 하나씩 나누어서 빌드하십시오.")
            
        # Calculate packaged items info
        wheel_count = 0
        if os.path.exists(os.path.join(payload_dir, "wheels")):
            wheel_count = len(os.listdir(os.path.join(payload_dir, "wheels")))
            
        build_info = {
            "filename": os.path.basename(output_zip_path),
            "target_os": target_os,
            "python_versions": python_versions,
            "package_count": wheel_count,
            "size_warning": size_warning,
            "zip_size": zip_size
        }
        return build_info
        
    except Exception as e:
        log_callback(f"[ERROR] 빌드 중 심각한 에러 발생: {e}")
        log_callback(traceback.format_exc())
        raise e
    finally:
        # Clean up temporary directory
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception:
            pass

def write_linux_install_script(dest_path):
    """
    Generates install.sh for Linux packaging.
    """
    script_content = r"""#!/bin/bash
# install.sh for uvtool offline installer on Linux
set -e

echo "=========================================================="
echo "          uvtool Linux Offline Installer                  "
echo "=========================================================="

INSTALL_DIR="$HOME/.local"
BIN_DIR="$INSTALL_DIR/bin"
PYTHON_BASE_DIR="$INSTALL_DIR/share/uvtool/python"
WHEELS_DIR="$INSTALL_DIR/share/uvtool/wheels"

mkdir -p "$BIN_DIR"
mkdir -p "$PYTHON_BASE_DIR"
mkdir -p "$WHEELS_DIR"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PAYLOAD_DIR="$SCRIPT_DIR/payload"

if [ ! -d "$PAYLOAD_DIR" ]; then
    echo "[ERROR] payload 폴더를 찾을 수 없습니다. 패키지가 온전하지 않습니다."
    exit 1
fi

# 1. uv 설치
echo "[1/4] uv 설치 중..."
UV_ARCHIVE=$(find "$PAYLOAD_DIR" -name "uv-*.tar.gz")
if [ -z "$UV_ARCHIVE" ]; then
    echo "[ERROR] uv 아카이브 파일을 찾을 수 없습니다."
    exit 1
fi

TEMP_EXTRACT=$(mktemp -d)
tar -xzf "$UV_ARCHIVE" -C "$TEMP_EXTRACT"
UV_DIR=$(find "$TEMP_EXTRACT" -maxdepth 2 -name "uv" -type f | xargs dirname)
cp "$UV_DIR/uv" "$BIN_DIR/"
cp "$UV_DIR/uvx" "$BIN_DIR/"
chmod +x "$BIN_DIR/uv" "$BIN_DIR/uvx"
rm -rf "$TEMP_EXTRACT"
echo "✓ uv가 $BIN_DIR 에 설치되었습니다."

# 2. Python Standalone 설치
echo "[2/4] Python Standalone 인터프리터 설치 중..."
PYTHON_ARCHIVES=$(find "$PAYLOAD_DIR/python" -name "cpython-*.tar.gz" 2>/dev/null || true)
DEFAULT_PY_PATH=""

for arch in $PYTHON_ARCHIVES; do
    filename=$(basename "$arch")
    # Extract version, e.g. cpython-3.12.8+... -> 3.12
    pyver=$(echo "$filename" | cut -d'-' -f2 | cut -d'+' -f1 | cut -d'.' -f1,2)
    
    target_py_dir="$PYTHON_BASE_DIR/$pyver"
    mkdir -p "$target_py_dir"
    echo "  - Python $pyver 추출 중 ($target_py_dir)..."
    tar -xzf "$arch" -C "$target_py_dir" --strip-components=1
    
    # Check binary path
    if [ -f "$target_py_dir/bin/python3" ]; then
        DEFAULT_PY_PATH="$target_py_dir/bin/python3"
    fi
done

# 3. wheels 복사
echo "[3/4] 오프라인 wheels 패키지 복사 중..."
if [ -d "$PAYLOAD_DIR/wheels" ]; then
    cp -r "$PAYLOAD_DIR/wheels/"* "$WHEELS_DIR/" 2>/dev/null || true
    echo "✓ 오프라인 패키지가 복사되었습니다: $WHEELS_DIR"
fi

# 4. 환경 변수 등록 (.bashrc 또는 .profile)
echo "[4/4] 사용자 환경 변수 등록 중..."
SHELL_RC="$HOME/.bashrc"
if [ ! -f "$SHELL_RC" ]; then
    SHELL_RC="$HOME/.profile"
fi

# PATH 추가
if ! grep -q "export PATH=\\\$HOME/.local/bin:\\\$PATH" "$SHELL_RC"; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
    echo "✓ PATH 환경변수가 $SHELL_RC 에 추가되었습니다."
fi

# UV Offline Configuration 추가
if ! grep -q "export UV_NO_INDEX=" "$SHELL_RC"; then
    echo 'export UV_NO_INDEX=1' >> "$SHELL_RC"
    echo "export UV_FIND_LINKS=\\"$WHEELS_DIR\\"" >> "$SHELL_RC"
    echo "✓ UV 오프라인 리다이렉션 환경변수가 $SHELL_RC 에 추가되었습니다."
fi

echo "=========================================================="
echo "✓ 설치가 성공적으로 완료되었습니다!"
echo "새 터미널 창을 열거나 'source $SHELL_RC'를 실행하여 상태를 적용하십시오."
echo "확인 명령어:"
echo "  uv --version"
echo "  python3 --version"
echo "  uv pip install [패키지명]  (인터넷 없이 오프라인 설치 실행)"
echo "=========================================================="
"""
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(script_content)
