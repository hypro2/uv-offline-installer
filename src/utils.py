import os
import sys
import ssl
import urllib.request
import zipfile
import tarfile

def download_file(url, dest_path, progress_callback=None, status_callback=None, ssl_bypass="standard"):
    """
    Downloads a file from URL to dest_path with progress reporting.
    Supports secure or insecure connection modes based on ssl_bypass settings.
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


def extract_zip(zip_path, dest_dir, progress_callback=None, status_callback=None):
    """
    Extracts a ZIP file to dest_dir.
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

def extract_tar_gz(tar_path, dest_dir, progress_callback=None, status_callback=None):
    """
    Extracts a .tar.gz file to dest_dir.
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

def broadcast_setting_change():
    """
    Broadcasts WM_SETTINGCHANGE message to all Windows processes.
    Forces Explorer to reload environment variables without rebooting.
    """
    if sys.platform != 'win32':
        return
        
    try:
        import ctypes
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

def set_user_environment_variable(name, value):
    """
    Sets a user environment variable persistently in Windows Registry.
    """
    if sys.platform != 'win32':
        # Fallback for Linux (can write to .bashrc)
        return False
        
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        winreg.CloseKey(key)
        broadcast_setting_change()
        return True
    except Exception as e:
        print(f"Failed to set user env variable {name}: {e}")
        return False

def fetch_uv_installer_original(dest_path=None, ssl_bypass="standard"):
    """
    Downloads the original Astral uv installer PS1 (irm https://astral.sh/uv/install.ps1)
    for reference. Skips download if the file already exists.
    Returns the path to the file.
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


def add_to_user_path(new_path):
    """
    Safely adds a folder path to the User PATH environment variable.
    Checks if path already exists before appending.
    """
    if sys.platform != 'win32':
        return False
        
    try:
        import winreg
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
