import os
import sys
import shutil
import subprocess
import zipfile
import traceback
import json
import hashlib
import datetime
import urllib.request
import ssl
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

def get_platform_info(target_os, target_arch):
    """
    Returns platform information including triples and pip platforms.
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

def is_docker_available():
    """
    Checks if Docker command is available and the daemon is running.
    """
    if not shutil.which("docker"):
        return False
    try:
        res = subprocess.run(["docker", "info"], capture_output=True, timeout=3, text=True)
        return res.returncode == 0
    except Exception:
        return False

def get_python_asset_url(py_ver, plat, log_callback, stripped=False):
    """
    Dynamically finds the python-build-standalone download URL by querying GitHub API
    with a stable fallback map for rate-limited cases.
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

def build_package(target_os, target_arch, uv_version, python_versions, pip_packages, output_zip_path, log_callback, progress_callback, package_scope="all", ssl_bypass="standard"):
    """
    Builds the offline package zip containing uv, python standalone tarballs, and wheels.
    Implements local caching to avoid re-downloading existing files.
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
                download_file(uv_url, uv_cache_path, status_callback=log_callback)
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
                        download_file(pbp_url, pbp_cache_path, status_callback=log_callback)
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
                            download_file(pbp_url_s, pbp_cache_path_s, status_callback=log_callback)
                            shutil.copy2(pbp_cache_path_s, pbp_dest_s)
                            log_callback(f"[SUCCESS] Python {py_ver} (stripped) 다운로드 완료 및 캐싱.")
        else:
            log_callback("[INFO] 증분 패키징 모드: Python Standalone 인터프리터 패키징을 생략합니다.")
                        
        # 4. Download PIP Package wheels (with caching & new file tracking)
        progress_callback(60)
        if pip_packages:
            wheels_dir = os.path.join(payload_dir, "wheels")
            os.makedirs(wheels_dir)
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
            
            # Write packages to temporary requirements.txt
            req_file_path = os.path.join(temp_dir, "requirements.txt")
            with open(req_file_path, "w", encoding="utf-8") as rf:
                for pkg in pip_packages:
                    rf.write(f"{pkg}\n")
                    
            for py_ver in python_versions:
                log_callback(f"[INFO] Python {py_ver} 버전에 맞는 wheel 패키지 분석 및 다운로드 중 (캐시 활용)...")
                
                # Check if Docker should be used for Linux target
                use_docker = (target_os == "linux" and is_docker_available())
                
                if use_docker:
                    log_callback("[INFO] Docker 가용 상태가 감지되었습니다. 리눅스 휠 다운로드를 위해 Docker 컨테이너를 구동합니다.")
                    abs_wheels_dir = os.path.abspath(wheels_dir)
                    abs_temp_dir = os.path.abspath(temp_dir)
                    abs_pip_cache = os.path.abspath(pip_cache_dir)
                    
                    vol_wheels = abs_wheels_dir.replace("\\", "/")
                    vol_temp = abs_temp_dir.replace("\\", "/")
                    vol_cache = abs_pip_cache.replace("\\", "/")
                    
                    image_tag = f"python:{py_ver}-slim"
                    
                    container_cmd = [
                        "pip", "download",
                        "--only-binary=:all:",
                        "--dest", "/wheels",
                        "--cache-dir", "/cache",
                        "-r", "/temp/requirements.txt"
                    ]
                    
                    if ssl_bypass == "system_certs":
                        log_callback("[WARNING] Docker 내부 빌드 시 OS 신뢰 저장소 옵션이 제한되므로, 도메인 신뢰 강제(--trusted-host) 방식으로 우회 다운로드합니다.")
                        container_cmd.extend([
                            "--trusted-host", "pypi.org",
                            "--trusted-host", "files.pythonhosted.org",
                            "--trusted-host", "pypi.python.org"
                        ])
                    elif ssl_bypass == "trusted_host":
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
                        cmd.extend(["--use-feature=truststore"])
                    elif ssl_bypass == "trusted_host":
                        log_callback("[INFO] SSL 우회: PyPI 주요 도메인을 강제 신뢰(--trusted-host)합니다.")
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
                    log_callback(f"[WARNING] Python {py_ver} 용 패키지 수집 중 경고/에러가 발생했습니다 (코드: {process.returncode}).")
            
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


                    
        # 5. Copy Launchers / Install scripts
        progress_callback(85)
        log_callback("[INFO] 오프라인 설치 스크립트 및 런처 배치 중...")

        # Generate install_offline.ps1 for Windows targets (offline replacement for uv install.ps1)
        if target_os == "windows":
            from .ps1_generator import generate_install_ps1
            ps1_content = generate_install_ps1()
            ps1_dest = os.path.join(temp_dir, "install_offline.ps1")
            with open(ps1_dest, "w", encoding="utf-8-sig") as f:
                f.write(ps1_content)
            log_callback("[INFO] install_offline.ps1 생성 완료 (irm https://astral.sh/uv/install.ps1 | iex 대체품)")
        
        # Check and copy compiled installer if exists (from dist directory or embedded resource)
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # Embedded resource inside builder_gui.exe
            installer_exe_source = os.path.join(sys._MEIPASS, "installer_gui.exe")
            log_callback(f"[INFO] PyInstaller 임시 경로에서 embedded installer_gui.exe를 로드합니다: {installer_exe_source}")
        else:
            # Running as source code
            dist_dir = os.path.join(workspace_dir, "dist")
            installer_exe_source = os.path.join(dist_dir, "installer_gui.exe")
            if not os.path.exists(installer_exe_source):
                installer_exe_source = os.path.join(dist_dir, "installer_gui", "installer_gui.exe")
            
        if target_os == "windows":
            # Copy Windows scripts
            install_bat_dest = os.path.join(temp_dir, "install.bat")
            with open(install_bat_dest, "w", encoding="euc-kr") as f:
                f.write("@echo off\n")
                f.write("echo [uvtool] 오프라인 설치기를 실행하는 중...\n")
                if os.path.exists(installer_exe_source):
                    f.write("start \"\" \"%~dp0installer_gui.exe\"\n")
                else:
                    f.write("echo [WARNING] 컴파일된 installer_gui.exe를 찾을 수 없습니다. python 스크립트로 실행을 시도합니다.\n")
                    f.write("python \"%~dp0installer_gui.py\" 2>nul || python.exe \"%~dp0installer_gui.py\"\n")
                    f.write("if %errorlevel% neq 0 (\n")
                    f.write("    echo [ERROR] Python이 설치되어 있지 않거나 실행할 수 없습니다.\n")
                    f.write("    pause\n")
                    f.write(")\n")
                    
            # If installer_exe exists, copy it. Else, copy python source files.
            if os.path.exists(installer_exe_source):
                shutil.copy2(installer_exe_source, os.path.join(temp_dir, "installer_gui.exe"))
                log_callback("[INFO] 컴파일된 installer_gui.exe 파일을 패키지에 번들링했습니다.")
            else:
                log_callback("[WARNING] dist 폴더에 빌드된 installer_gui.exe를 찾을 수 없어, 파이썬 소스 코드(.py) 형태로 번들링합니다.")
                # Copy python source files and subfolder structure
                shutil.copytree(
                    os.path.join(workspace_dir, "src"),
                    os.path.join(temp_dir, "src"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
                )
                shutil.copy2(
                    os.path.join(workspace_dir, "installer_gui.py"),
                    os.path.join(temp_dir, "installer_gui.py")
                )
        else:
            # Copy Linux shell script installer
            install_sh_dest = os.path.join(temp_dir, "install.sh")
            write_linux_install_script(install_sh_dest)
            log_callback("[INFO] 리눅스용 install.sh 설치 쉘 스크립트를 생성했습니다.")
            
        # 6. Compress everything to output_zip_path
        progress_callback(90)
        log_callback(f"[INFO] 최종 오프라인 패키지 압축 파일 작성 중: {os.path.basename(output_zip_path)}")
        
        # Ensure target folder exists
        os.makedirs(os.path.dirname(os.path.abspath(output_zip_path)), exist_ok=True)
        
        with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, temp_dir)
                    zipf.write(file_path, arcname)
                    
        progress_callback(100)
        log_callback(f"[SUCCESS] 오프라인 패키지 빌드 완료: {output_zip_path}")
        
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
