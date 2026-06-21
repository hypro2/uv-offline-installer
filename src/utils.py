import os
import ssl
import sys
import tarfile
import urllib.request
import zipfile
from typing import Callable, Optional

# Windows 전용 모듈 조건부 로드 (IDE 정적 분석 경고 방지용 대체 정의 포함)
if sys.platform == 'win32':
    import ctypes
    import winreg
else:
    ctypes = None
    winreg = None


def download_file(
    url: str,
    dest_path: str,
    progress_callback: Optional[Callable[[int], None]] = None,
    status_callback: Optional[Callable[[str], None]] = None,
    ssl_bypass: str = "standard"
) -> bool:
    """
    지정된 URL에서 파일을 다운로드하여 대상 경로(dest_path)에 저장합니다.

    Args:
        url (str): 다운로드할 대상 URL.
        dest_path (str): 다운로드 완료 후 저장할 로컬 파일 경로.
        progress_callback (Optional[Callable[[int], None]], optional): 다운로드 진행률(0~100)을 수신할 콜백 함수. Defaults to None.
        status_callback (Optional[Callable[[str], None]], optional): 상태 메시지를 수신할 콜백 함수. Defaults to None.
        ssl_bypass (str, optional): SSL 검증 우회 수준 설정 ("standard", "trusted_host", "system_certs"). Defaults to "standard".

    Returns:
        bool: 다운로드 성공 시 True 반환.

    Raises:
        Exception: 네트워크 오류 및 SSL 검증 에러 발생 시 발생.
    """
    if status_callback:
        status_callback(f"다운로드 중: {os.path.basename(dest_path)} (SSL 모드: {ssl_bypass})...")
        
    # Ensure directory exists
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    
    def try_download(ssl_context=None):
        with urllib.request.urlopen(req, context=ssl_context) as response:
            total_size = int(response.info().get('Content-Length', 0))
            block_size = 1024 * 64
            downloaded = 0
            
            with open(dest_path, 'wb') as f:
                while True:
                    buffer = response.read(block_size)
                    if not buffer:
                        break
                    downloaded += len(buffer)
                    f.write(buffer)
                    
                    if total_size > 0 and progress_callback:
                        percent = int((downloaded / total_size) * 100)
                        progress_callback(percent)
        if progress_callback:
            progress_callback(100)
        return True

    # SSL context configurations
    if ssl_bypass == "trusted_host":
        if status_callback:
            status_callback("[INFO] SSL 우회: 무검증 SSL 컨텍스트(--trusted-host)를 즉시 적용합니다.")
        insecure_context = ssl._create_unverified_context()
        return try_download(ssl_context=insecure_context)
        
    elif ssl_bypass == "system_certs":
        if status_callback:
            status_callback("[INFO] SSL 우회: OS 신뢰 저장소 인증서(--system-certs) 검증을 사용합니다.")
        # create default context (loads system certs on Python 3.10+ Windows)
        default_context = ssl.create_default_context()
        return try_download(ssl_context=default_context)
        
    else: # standard (default)
        try:
            # 1st attempt: Normal verified connection
            return try_download()
        except Exception as e:
            if status_callback:
                status_callback(f"[WARNING] SSL 또는 다운로드 시도 실패 ({e}). 보안 필터 우회를 위해 무검증 컨텍스트로 재시도합니다...")
            try:
                # 2nd attempt: Bypass SSL verification
                insecure_context = ssl._create_unverified_context()
                return try_download(ssl_context=insecure_context)
            except Exception as e2:
                if status_callback:
                    status_callback(f"[ERROR] 우회 다운로드도 실패했습니다: {e2}")
                raise e2


def extract_zip(
    zip_path: str,
    dest_dir: str,
    progress_callback: Optional[Callable[[int], None]] = None,
    status_callback: Optional[Callable[[str], None]] = None
) -> bool:
    """
    ZIP 압축 파일을 지정된 디렉토리(dest_dir)에 압축 해제합니다.

    Args:
        zip_path (str): ZIP 파일 경로.
        dest_dir (str): 압축 해제할 대상 디렉토리 경로.
        progress_callback (Optional[Callable[[int], None]], optional): 압축 해제 진행률(0~100)을 수신할 콜백 함수. Defaults to None.
        status_callback (Optional[Callable[[str], None]], optional): 상태 메시지를 수신할 콜백 함수. Defaults to None.

    Returns:
        bool: 압축 해제 성공 시 True 반환.
    """
    if status_callback:
        status_callback(f"압축 해제 중: {os.path.basename(zip_path)}...")
        
    os.makedirs(dest_dir, exist_ok=True)
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            nl = zip_ref.namelist()
            total_files = len(nl)
            
            for idx, member in enumerate(nl):
                zip_ref.extract(member, dest_dir)
                if progress_callback and total_files > 0:
                    percent = int(((idx + 1) / total_files) * 100)
                    progress_callback(percent)
                    
        if progress_callback:
            progress_callback(100)
        return True
    except Exception as e:
        if status_callback:
            status_callback(f"[ERROR] ZIP 압축 해제 실패: {e}")
        raise e

def extract_tar_gz(
    tar_path: str,
    dest_dir: str,
    progress_callback: Optional[Callable[[int], None]] = None,
    status_callback: Optional[Callable[[str], None]] = None
) -> bool:
    """
    tar.gz 압축 파일을 지정된 디렉토리(dest_dir)에 압축 해제합니다.
    디렉토리 상위 경로 탐색 공격(Path Traversal) 방어 로직이 적용되어 있습니다.

    Args:
        tar_path (str): tar.gz 파일 경로.
        dest_dir (str): 압축 해제할 대상 디렉토리 경로.
        progress_callback (Optional[Callable[[int], None]], optional): 압축 해제 진행률(0~100)을 수신할 콜백 함수. Defaults to None.
        status_callback (Optional[Callable[[str], None]], optional): 상태 메시지를 수신할 콜백 함수. Defaults to None.

    Returns:
        bool: 압축 해제 성공 시 True 반환.
    """
    if status_callback:
        status_callback(f"압축 해제 중: {os.path.basename(tar_path)}...")
        
    os.makedirs(dest_dir, exist_ok=True)
    
    try:
        with tarfile.open(tar_path, 'r:gz') as tar_ref:
            members = tar_ref.getmembers()
            total_files = len(members)

            abs_dest = os.path.realpath(dest_dir)
            for idx, member in enumerate(members):
                # Path traversal guard: reject members that escape dest_dir
                member_path = os.path.realpath(os.path.join(abs_dest, member.name))
                if not member_path.startswith(abs_dest + os.sep) and member_path != abs_dest:
                    if status_callback:
                        status_callback(f"[WARNING] 경로 순회 시도 차단: {member.name}")
                    continue
                tar_ref.extract(member, dest_dir)
                if progress_callback and total_files > 0:
                    percent = int(((idx + 1) / total_files) * 100)
                    progress_callback(percent)

        if progress_callback:
            progress_callback(100)
        return True
    except Exception as e:
        if status_callback:
            status_callback(f"[ERROR] TAR.GZ 압축 해제 실패: {e}")
        raise e

def broadcast_setting_change() -> None:
    """
    Windows 시스템의 모든 활성 프로세스에 WM_SETTINGCHANGE 메시지를 전송합니다.
    이를 통해 재부팅 없이 환경 변수 설정(PATH 등)이 윈도우 탐색기에 즉시 반영됩니다.
    """
    if sys.platform != 'win32':
        return
        
    try:
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002

        result = ctypes.c_long()
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment",
            SMTO_ABORTIFHUNG, 3000, ctypes.byref(result)
        )
    except Exception as e:
        print(f"Warning: Failed to broadcast system change message: {e}")

def set_user_environment_variable(name: str, value: str) -> bool:
    """
    사용자 환경 변수를 Windows 레지스트리(HKEY_CURRENT_USER\\Environment)에 영구적으로 등록합니다.

    Args:
        name (str): 환경 변수 이름.
        value (str): 환경 변수 값.

    Returns:
        bool: 설정 성공 시 True, 실패 시 False 반환.
    """
    if sys.platform != 'win32':
        # Fallback for Linux (can write to .bashrc)
        return False
        
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        winreg.CloseKey(key)
        broadcast_setting_change()
        return True
    except Exception as e:
        print(f"Failed to set user env variable {name}: {e}")
        return False

def fetch_uv_installer_original(
    dest_path: Optional[str] = None,
    ssl_bypass: str = "standard"
) -> str:
    """
    인터넷망 모드에서 최신 Astral uv 공식 설치용 PowerShell 스크립트를 참조용으로 가져옵니다.
    파일이 이미 있으면 다운로드를 건너뜁니다.

    Args:
        dest_path (Optional[str], optional): 다운로드받을 로컬 대상 파일 경로. Defaults to None.
        ssl_bypass (str, optional): SSL 우회 방식 설정. Defaults to "standard".

    Returns:
        str: 다운로드 또는 확인된 파일의 절대 경로.
    """
    if dest_path is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dest_path = os.path.join(base, "uv-installer-original.ps1")

    if os.path.exists(dest_path):
        return dest_path

    url = "https://releases.astral.sh/installers/uv/latest/uv-installer.ps1"
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})

    def _fetch(ctx=None):
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            content = resp.read()
        with open(dest_path, 'wb') as f:
            f.write(content)

    if ssl_bypass == "trusted_host":
        _fetch(ssl._create_unverified_context())
    else:
        try:
            _fetch()
        except Exception:
            _fetch(ssl._create_unverified_context())

    return dest_path


def add_to_user_path(new_path: str) -> bool:
    """
    사용자의 PATH 환경 변수에 지정된 폴더 경로를 안전하게 추가합니다.
    중복 등록을 방지하기 위해 중복 검사를 거친 후 레지스트리를 갱신합니다.

    Args:
        new_path (str): PATH에 추가할 신규 폴더 경로.

    Returns:
        bool: 추가 성공(혹은 이미 있는 경우) 시 True, 실패 시 False 반환.
    """
    if sys.platform != 'win32':
        return False
        
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS)
        try:
            current_path, data_type = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current_path = ""
            data_type = winreg.REG_EXPAND_SZ

        norm_new_path = os.path.normpath(new_path).lower()
        paths = [p.strip() for p in current_path.split(";") if p.strip()]
        norm_paths = [os.path.normpath(p).lower() for p in paths]

        if norm_new_path not in norm_paths:
            paths.append(new_path)
            winreg.SetValueEx(key, "Path", 0, data_type, ";".join(paths))

        winreg.CloseKey(key)
        broadcast_setting_change()
        return True
    except Exception as e:
        print(f"Failed to add path {new_path} to User PATH: {e}")
        return False
