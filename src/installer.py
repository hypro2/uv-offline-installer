import os
import shutil
import glob
import platform
import subprocess
import traceback
from .utils import extract_zip, extract_tar_gz, set_user_environment_variable, add_to_user_path, download_file

def get_bundled_info(payload_dir):
    """
    Scans the payload folder to list uv version, Python versions, and wheels available.
    Supports both nested installer payload structures and direct flat export folder layouts.
    """
    info = {
        "uv_archive": None,
        "python_archives": [],
        "wheels": []
    }
    
    if not os.path.exists(payload_dir):
        return info
        
    # Standardize search paths: search in payload_dir directly AND in payload_dir/payload
    search_dirs = [payload_dir]
    sub_payload = os.path.join(payload_dir, "payload")
    if os.path.exists(sub_payload):
        search_dirs.append(sub_payload)
        
    # 1. Find uv archive
    for s_dir in search_dirs:
        uv_zips = glob.glob(os.path.join(s_dir, "uv-*.zip"))
        uv_tars = glob.glob(os.path.join(s_dir, "uv-*.tar.gz"))
        if uv_zips:
            info["uv_archive"] = uv_zips[0]
            break
        elif uv_tars:
            info["uv_archive"] = uv_tars[0]
            break
            
    # 2. Find python archives
    # Search in s_dir, s_dir/python, and payload_dir/python
    py_search_dirs = search_dirs.copy()
    for s_dir in search_dirs:
        py_dir = os.path.join(s_dir, "python")
        if os.path.exists(py_dir):
            py_search_dirs.append(py_dir)
            
    for py_dir in py_search_dirs:
        py_tars = glob.glob(os.path.join(py_dir, "cpython-*.tar.gz"))
        py_zips = glob.glob(os.path.join(py_dir, "cpython-*.zip"))
        info["python_archives"].extend(py_tars)
        info["python_archives"].extend(py_zips)
        
    # Deduplicate python archives
    info["python_archives"] = list(set(info["python_archives"]))
        
    # 3. Find wheels
    # Search in s_dir, s_dir/wheels, and payload_dir/wheels
    wheel_search_dirs = search_dirs.copy()
    for s_dir in search_dirs:
        wheels_dir = os.path.join(s_dir, "wheels")
        if os.path.exists(wheels_dir):
            wheel_search_dirs.append(wheels_dir)
            
    for whl_dir in wheel_search_dirs:
        whls = glob.glob(os.path.join(whl_dir, "*.whl"))
        info["wheels"].extend(whls)
        
    # Deduplicate wheels
    info["wheels"] = list(set(info["wheels"]))
        
    return info

def install_offline(payload_dir, install_dir, log_callback, progress_callback, register_global_env=True, offline_mode=True, ssl_bypass="standard"):
    """
    Performs the local offline installation.
    """
    log_callback(f"[INFO] 설치 시작... 대상 경로: {install_dir} (폐쇄망 모드: {'활성화' if offline_mode else '비활성화'}, SSL 모드: {ssl_bypass})")
    
    try:
        # Create directories
        os.makedirs(install_dir, exist_ok=True)
        wheels_dest_dir = os.path.join(install_dir, "wheels")
        os.makedirs(wheels_dest_dir, exist_ok=True)
        
        info = get_bundled_info(payload_dir)
        
        uv_archive_path = info["uv_archive"]
        temp_download_path = None
        
        # Check if uv is already installed in target install_dir
        existing_uv_exe = os.path.join(install_dir, "uv.exe")
        is_uv_already_installed = os.path.exists(existing_uv_exe)
        
        if not uv_archive_path and not is_uv_already_installed:
            if offline_mode:
                log_callback("[ERROR] 패키지 내에 uv 설치 파일이 존재하지 않고, 기존 설치본도 없으나 폐쇄망 모드(Strict Offline)이므로 설치를 중단합니다.")
                raise FileNotFoundError("패키지 내에 uv 설치 파일이 존재하지 않으며, 폐쇄망 모드가 활성화되어 외부 인터넷 다운로드를 실행할 수 없습니다.")
                
            log_callback("[WARNING] 패키지 내에서 uv 설치 파일을 찾을 수 없고, 기존 설치된 uv.exe도 발견되지 않았습니다. 인터넷 다운로드를 시도합니다...")
            arch = platform.machine().lower()
            if arch in ['amd64', 'x86_64']:
                uv_archive_name = "uv-x86_64-pc-windows-msvc.zip"
            elif arch in ['arm64', 'aarch64']:
                uv_archive_name = "uv-aarch64-pc-windows-msvc.zip"
            else:
                uv_archive_name = "uv-x86_64-pc-windows-msvc.zip"
                
            uv_url = f"https://github.com/astral-sh/uv/releases/latest/download/{uv_archive_name}"
            temp_download_path = os.path.join(install_dir, uv_archive_name)
            
            try:
                download_file(uv_url, temp_download_path, status_callback=log_callback, ssl_bypass=ssl_bypass)
                uv_archive_path = temp_download_path
                log_callback(f"[SUCCESS] uv 설치 파일을 인터넷에서 다운로드했습니다: {uv_archive_name}")
            except Exception as dl_err:
                log_callback(f"[ERROR] uv 설치 파일 실시간 다운로드 실패: {dl_err}")
                raise FileNotFoundError("패키지 내에 uv 설치 파일이 존재하지 않고, 인터넷 실시간 다운로드도 실패했습니다.")

            
        # 1. Extract uv
        progress_callback(15)
        if uv_archive_path:
            log_callback("[INFO] 1. uv 설치 파일 압축 해제 중...")
            temp_extract_dir = os.path.join(install_dir, "temp_uv_extract")
            if os.path.exists(temp_extract_dir):
                shutil.rmtree(temp_extract_dir)
                
            if uv_archive_path.endswith(".zip"):
                extract_zip(uv_archive_path, temp_extract_dir, status_callback=log_callback)
            else:
                extract_tar_gz(uv_archive_path, temp_extract_dir, status_callback=log_callback)
                
            # Find uv.exe and uvx.exe inside temp_extract_dir recursively
            uv_exe_path = None
            uvx_exe_path = None
            for root, dirs, files in os.walk(temp_extract_dir):
                for file in files:
                    if file.lower() == "uv.exe":
                        uv_exe_path = os.path.join(root, file)
                    elif file.lower() == "uvx.exe":
                        uvx_exe_path = os.path.join(root, file)
                        
            if not uv_exe_path:
                raise FileNotFoundError("압축 해제된 폴더에서 uv.exe를 찾을 수 없습니다.")
                
            # Copy to install_dir
            shutil.copy2(uv_exe_path, os.path.join(install_dir, "uv.exe"))
            if uvx_exe_path:
                shutil.copy2(uvx_exe_path, os.path.join(install_dir, "uvx.exe"))
                
            log_callback(f"[SUCCESS] uv 바이너리 설치 완료: {install_dir}")
            shutil.rmtree(temp_extract_dir)
            
            # Clean up temp downloaded file if any
            if temp_download_path and os.path.exists(temp_download_path):
                try:
                    os.remove(temp_download_path)
                    log_callback(f"[INFO] 임시 다운로드된 uv 아카이브 파일을 정리했습니다.")
                except Exception:
                    pass
        else:
            log_callback("[INFO] 1. uv 설치 아카이브가 없고 기존에 설치된 uv.exe가 감지되어 uv 설치 단계를 건너뜁니다.")
        
        # 2. Extract Python Standalone versions
        progress_callback(40)
        log_callback("[INFO] 2. Python Standalone 인터프리터 설치 중...")
        
        python_subdirs = []
        
        for idx, py_archive in enumerate(info["python_archives"]):
            filename = os.path.basename(py_archive)
            # Parse version from name, e.g. cpython-3.12.8+... -> 3.12
            try:
                py_ver_part = filename.split('-')[1].split('+')[0] # "3.12.8"
                py_major_minor = '.'.join(py_ver_part.split('.')[:2]) # "3.12"
            except Exception:
                py_major_minor = f"custom_{idx}"
                
            py_target_dir = os.path.join(install_dir, "python", py_major_minor)
            if os.path.exists(py_target_dir):
                shutil.rmtree(py_target_dir)
            os.makedirs(py_target_dir)
            
            log_callback(f"[INFO] Python {py_major_minor} 압축 해제 중: {filename}")
            extract_tar_gz(py_archive, py_target_dir, status_callback=log_callback)
            
            # python-build-standalone Windows contains 'python.exe' inside a subfolder (like 'install' or 'python')
            # Let's detect any such folder and pull its contents up to the py_target_dir
            for sub_name in ["install", "python"]:
                sub_dir_path = os.path.join(py_target_dir, sub_name)
                if os.path.exists(sub_dir_path) and os.path.isdir(sub_dir_path):
                    if os.path.exists(os.path.join(sub_dir_path, "python.exe")):
                        log_callback(f"[INFO] {sub_name} 내부 폴더 파일을 {py_target_dir} 상위 폴더로 이동 중...")
                        for item in os.listdir(sub_dir_path):
                            s_path = os.path.join(sub_dir_path, item)
                            d_path = os.path.join(py_target_dir, item)
                            if os.path.exists(d_path):
                                if os.path.isdir(d_path):
                                    shutil.rmtree(d_path)
                                else:
                                    os.remove(d_path)
                            shutil.move(s_path, d_path)
                        shutil.rmtree(sub_dir_path)
                        break
                
            python_subdirs.append(py_target_dir)
            log_callback(f"[SUCCESS] Python {py_major_minor} 설치 완료: {py_target_dir}")
            
        # If no Python versions are newly installed, scan for pre-existing Python installations in target dir
        if not python_subdirs:
            py_base_dir = os.path.join(install_dir, "python")
            if os.path.exists(py_base_dir):
                for d in os.listdir(py_base_dir):
                    d_path = os.path.join(py_base_dir, d)
                    if os.path.isdir(d_path):
                        if os.path.exists(os.path.join(d_path, "python.exe")):
                            python_subdirs.append(d_path)
                            log_callback(f"[INFO] 기존 설치된 Python 버전 감지: {d}")
                            
        # 3. Copy Wheels
        progress_callback(70)
        log_callback("[INFO] 3. 오프라인 PIP wheels 라이브러리 파일 복사 중...")
        for wheel in info["wheels"]:
            shutil.copy2(wheel, os.path.join(wheels_dest_dir, os.path.basename(wheel)))
        log_callback(f"[SUCCESS] {len(info['wheels'])}개의 wheel 파일 복사 완료: {wheels_dest_dir}")
        
        # 4. Register environment variables / Config files
        progress_callback(85)
        log_callback("[INFO] 4. 환경 변수 및 설정 파일 구성 중...")
        
        # PATH registration (adds install_dir containing uv.exe)
        log_callback(f"  - PATH에 uv 설치 경로 추가: {install_dir}")
        add_to_user_path(install_dir)
        
        # If we have Python versions, add the default (highest) Python directory to PATH
        if python_subdirs:
            # Sort to get the highest version
            python_subdirs.sort()
            default_py_dir = python_subdirs[-1]
            log_callback(f"  - PATH에 기본 Python 경로 추가: {default_py_dir}")
            add_to_user_path(default_py_dir)
            
        # Check global environment variables preference
        if register_global_env:
            log_callback("  - [전역 설정] UV_NO_INDEX=1 사용자 환경 변수 등록")
            set_user_environment_variable("UV_NO_INDEX", "1")
            
            log_callback(f"  - [전역 설정] UV_FIND_LINKS={wheels_dest_dir} 사용자 환경 변수 등록")
            set_user_environment_variable("UV_FIND_LINKS", wheels_dest_dir)
        else:
            # Write a local uv.toml template in the install directory
            uv_toml_path = os.path.join(install_dir, "uv.toml")
            wheels_dest_dir_sl = wheels_dest_dir.replace("\\", "/")
            
            log_callback("  - [로컬 설정] 전역 환경 변수를 등록하지 않습니다. 프로젝트별 로컬용 uv.toml 템플릿을 생성합니다.")
            with open(uv_toml_path, "w", encoding="utf-8") as tf:
                tf.write("[pip]\n")
                tf.write("no-index = true\n")
                tf.write(f'find-links = ["{wheels_dest_dir_sl}"]\n')
            log_callback(f"  - 로컬 설정 파일 생성 완료: {uv_toml_path}")
            log_callback("  [팁] 프로젝트 폴더에 이 uv.toml을 복사해 넣으면 전역 환경 오염 없이 오프라인 설치가 구동됩니다.")
            
        log_callback("[SUCCESS] 환경 변수 및 설정 파일 구성 완료.")
        
        # 5. Verify installation
        progress_callback(95)
        log_callback("[INFO] 5. 설치 무결성 검사 및 버전 확인 중...")
        
        uv_final_exe = os.path.join(install_dir, "uv.exe")
        uv_ver_res = subprocess.run([uv_final_exe, "--version"], capture_output=True, text=True)
        if uv_ver_res.returncode == 0:
            log_callback(f"[SUCCESS] [검증] uv 정상 작동 확인: {uv_ver_res.stdout.strip()}")
        else:
            log_callback(f"[WARNING] [검증] uv 실행에 실패했습니다. (코드: {uv_ver_res.returncode})")
            
        if python_subdirs:
            py_final_exe = os.path.join(default_py_dir, "python.exe")
            py_ver_res = subprocess.run([py_final_exe, "--version"], capture_output=True, text=True)
            if py_ver_res.returncode == 0:
                log_callback(f"[SUCCESS] [검증] Python 정상 작동 확인: {py_ver_res.stdout.strip()}")
            else:
                log_callback(f"[WARNING] [검증] Python 실행에 실패했습니다.")
                
        progress_callback(100)
        log_callback("[SUCCESS] 오프라인 간편 설치 작업이 성공적으로 완료되었습니다!")
        return True
        
    except Exception as e:
        log_callback(f"[ERROR] 설치 중 치명적인 오류 발생: {e}")
        log_callback(traceback.format_exc())
        raise e
