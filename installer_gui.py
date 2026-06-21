import os
import shutil
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any, Dict, List, Optional

try:
    import customtkinter as ctk  # type: ignore
except ImportError:
    import subprocess
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "customtkinter"])
        import customtkinter as ctk  # type: ignore
    except Exception as e:
        raise ImportError(
            "customtkinter 모듈을 가져올 수 없으며 자동 설치에 실패했습니다. "
            f"터미널에서 'pip install customtkinter'을 실행하여 설치해주십시오. (에러: {e})"
        )

from src.builder import get_platform_info, get_python_asset_url
from src.installer import get_bundled_info, install_offline
from src.utils import download_file

# Configure global theme styling
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

# Premium, commercially free modern font fallback stack
def _resolve_font() -> str:
    try:
        import tkinter as tk
        from tkinter import font
        root = tk.Tk()
        root.withdraw()
        families = font.families()
        root.destroy()
        # 선호하는 모던 폰트 리스트 순회 매핑
        for f in ["Pretendard", "Noto Sans KR", "Segoe UI Variable Text", "Segoe UI", "Malgun Gothic"]:
            if f in families:
                return f
    except Exception:
        pass
    return "Segoe UI"

FONT_FAMILY = _resolve_font()


class InstallerApp(ctk.CTk):
    """
    uvtool 오프라인 간편 설치기 GUI 애플리케이션 클래스입니다.
    로컬에 저장된 오프라인 패키지 파일을 활용하여 uv 및 Python 환경을 원클릭으로 설치하고 구성하며,
    인터넷 환경에서는 오프라인용 설치 팩을 다운로드받아 외부에 저장하는 기능을 제공합니다.
    """

    def __init__(self) -> None:
        super().__init__()
        
        self.title("uvtool - 오프라인 간편 설치기 (Installer)")
        self.geometry("850x720")
        self.minsize(750, 620)
        
        self.accent_color = "#0064FF"
        
        # State variables
        self.installer_mode_var = tk.StringVar(value="offline")
        self.ssl_bypass_var = tk.StringVar(value="standard")
        self.global_env_var = tk.BooleanVar(value=True)
        self.bypass_py_var = tk.StringVar(value="3.12")
        
        # Determine paths relative to EXE or Python script
        self.base_dir = self.get_base_path()
        self.payload_dir = os.path.join(self.base_dir, "payload")
        
        self.setup_ui()
        self.load_package_info()
        
    def get_base_path(self) -> str:
        """
        실행 파일(.exe) 혹은 파이썬 스크립트 실행 경로의 절대 상위 디렉토리를 반환합니다.
        """
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))
        
    def setup_ui(self) -> None:
        # Configure layout Grid (1 row, 2 columns)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # 1. Sidebar Frame
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1)  # Spacer
        
        # Sidebar Logo Header
        self.logo_label = ctk.CTkLabel(
            self.sidebar_frame, text="uvtool Installer", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=20, weight="bold"),
            text_color=self.accent_color
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(25, 5))
        
        self.sub_logo_label = ctk.CTkLabel(
            self.sidebar_frame, text="오프라인 간편 설치기", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color="gray"
        )
        self.sub_logo_label.grid(row=1, column=0, padx=20, pady=(0, 25))
        
        # Sidebar Navigation Buttons
        self.nav_btn_offline = ctk.CTkButton(
            self.sidebar_frame, text="🔒 폐쇄망 모드 설치", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            anchor="w", fg_color="transparent", text_color=("gray10", "gray90"),
            hover_color=("gray70", "gray30"), command=lambda: self.select_tab("offline")
        )
        self.nav_btn_offline.grid(row=2, column=0, padx=15, pady=8, sticky="ew")
        
        self.nav_btn_online = ctk.CTkButton(
            self.sidebar_frame, text="🌐 인터넷망 다운로더", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            anchor="w", fg_color="transparent", text_color=("gray10", "gray90"),
            hover_color=("gray70", "gray30"), command=lambda: self.select_tab("online")
        )
        self.nav_btn_online.grid(row=3, column=0, padx=15, pady=8, sticky="ew")
        
        # Appearance Mode Controls
        self.appearance_label = ctk.CTkLabel(
            self.sidebar_frame, text="테마 모드 선택:", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold")
        )
        self.appearance_label.grid(row=5, column=0, padx=20, pady=(10, 5), sticky="w")
        
        self.appearance_menu = ctk.CTkOptionMenu(
            self.sidebar_frame, values=["System", "Dark", "Light"],
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            command=self.change_appearance_mode
        )
        self.appearance_menu.grid(row=6, column=0, padx=20, pady=(0, 25), sticky="ew")
        
        # 2. Main Content Tab Views
        self.content_frame_offline = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        self.content_frame_online = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        
        # Setup specific frames
        self.setup_offline_tab()
        self.setup_online_tab()
        
        # Default view active
        self.select_tab("offline")
        
    def select_tab(self, name: str) -> None:
        """
        네비게이션 사이드바 클릭 시 해당하는 우측 서브 화면 탭(offline/online)으로 전환합니다.

        Args:
            name (str): 전환할 탭 이름 ("offline", "online").
        """
        self.content_frame_offline.grid_forget()
        self.content_frame_online.grid_forget()
        
        self.nav_btn_offline.configure(fg_color="transparent", text_color=("gray10", "gray90"))
        self.nav_btn_online.configure(fg_color="transparent", text_color=("gray10", "gray90"))
        
        if name == "offline":
            self.content_frame_offline.grid(row=0, column=1, sticky="nsew", padx=25, pady=25)
            self.nav_btn_offline.configure(fg_color=self.accent_color, text_color="#FFFFFF")
            self.installer_mode_var.set("offline")
        elif name == "online":
            self.content_frame_online.grid(row=0, column=1, sticky="nsew", padx=25, pady=25)
            self.nav_btn_online.configure(fg_color=self.accent_color, text_color="#FFFFFF")
            self.installer_mode_var.set("online")
            
    def change_appearance_mode(self, mode: str) -> None:
        """
        GUI 애플리케이션의 화면 테마 모드를 전환합니다.
        """
        ctk.set_appearance_mode(mode)
        
    def setup_offline_tab(self) -> None:
        """
        '폐쇄망 모드 설치' 탭 화면 구성요소를 구축합니다.
        """
        # Header
        tab_header = ctk.CTkLabel(
            self.content_frame_offline, text="🔒 폐쇄망 모드 (오프라인 설치)", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=22, weight="bold"),
            anchor="w"
        )
        tab_header.pack(fill="x", pady=(10, 5))
        
        tab_desc = ctk.CTkLabel(
            self.content_frame_offline, 
            text="동봉된 CPython Standalone, uv 바이너리 및 휠 패키지 파일들을 기반으로 PC 환경을 자동 구성합니다.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12), text_color="gray", anchor="w"
        )
        tab_desc.pack(fill="x", pady=(0, 20))
        
        # 1. Package Metadata Card
        info_card = ctk.CTkFrame(self.content_frame_offline)
        info_card.pack(fill="x", pady=10)
        
        info_title = ctk.CTkLabel(
            info_card, text="동봉된 설치 패키지 정보 분석", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold")
        )
        info_title.pack(anchor="w", padx=20, pady=(15, 10))
        
        details_frame = ctk.CTkFrame(info_card, fg_color="transparent")
        details_frame.pack(fill="x", padx=20, pady=(0, 15))
        
        # Grid layout for label mappings
        ctk.CTkLabel(details_frame, text="uv 설치 파일:", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"), text_color="gray").grid(row=0, column=0, sticky="w", pady=4)
        self.uv_val = ctk.CTkLabel(details_frame, text="확인 중...", font=ctk.CTkFont(size=12))
        self.uv_val.grid(row=0, column=1, sticky="w", padx=15, pady=4)
        
        ctk.CTkLabel(details_frame, text="Python 버전:", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"), text_color="gray").grid(row=1, column=0, sticky="w", pady=4)
        self.py_val = ctk.CTkLabel(details_frame, text="확인 중...", font=ctk.CTkFont(size=12))
        self.py_val.grid(row=1, column=1, sticky="w", padx=15, pady=4)
        
        ctk.CTkLabel(details_frame, text="포함된 라이브러리:", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"), text_color="gray").grid(row=2, column=0, sticky="w", pady=4)
        self.pkg_val = ctk.CTkLabel(details_frame, text="확인 중...", font=ctk.CTkFont(size=12), wraplength=450, justify="left")
        self.pkg_val.grid(row=2, column=1, sticky="w", padx=15, pady=4)
        
        # 2. Paths Configuration Card
        settings_card = ctk.CTkFrame(self.content_frame_offline)
        settings_card.pack(fill="x", pady=10)
        
        settings_title = ctk.CTkLabel(
            settings_card, text="오프라인 경로 및 환경 설정", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold")
        )
        settings_title.pack(anchor="w", padx=20, pady=(15, 10))
        
        # Package Source path
        src_label = ctk.CTkLabel(settings_card, text="패키지/자동팩 경로 (Source Folder)", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"))
        src_label.pack(anchor="w", padx=20)
        
        src_frame = ctk.CTkFrame(settings_card, fg_color="transparent")
        src_frame.pack(fill="x", padx=20, pady=(5, 12))
        
        self.package_path_entry = ctk.CTkEntry(src_frame, font=ctk.CTkFont(size=12))
        self.package_path_entry.insert(0, self.payload_dir)
        self.package_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.package_path_entry.bind("<KeyRelease>", lambda e: self.load_package_info())
        
        src_btn = ctk.CTkButton(
            src_frame, text="변경...", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            width=100, command=self.browse_package_dir
        )
        src_btn.pack(side="left")
        
        # Install target path
        dest_label = ctk.CTkLabel(settings_card, text="설치 경로 (Destination Folder)", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"))
        dest_label.pack(anchor="w", padx=20)
        
        dest_frame = ctk.CTkFrame(settings_card, fg_color="transparent")
        dest_frame.pack(fill="x", padx=20, pady=(5, 12))
        
        self.install_path_entry = ctk.CTkEntry(dest_frame, font=ctk.CTkFont(size=12))
        default_install_dir = os.path.join(os.environ["USERPROFILE"], ".local", "bin")
        self.install_path_entry.insert(0, default_install_dir)
        self.install_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        dest_btn = ctk.CTkButton(
            dest_frame, text="변경...", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            width=100, command=self.browse_install_dir
        )
        dest_btn.pack(side="left")
        
        # Checkbox
        self.global_env_cb = ctk.CTkCheckBox(
            settings_card, text="오프라인 설정을 사용자 전역 환경 변수로 등록 (권장)",
            variable=self.global_env_var,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12)
        )
        self.global_env_cb.pack(anchor="w", padx=20, pady=(0, 15))
        
        # 3. Actions & Console Output Section
        actions_card = ctk.CTkFrame(self.content_frame_offline)
        actions_card.pack(fill="x", pady=10)
        
        self.install_btn = ctk.CTkButton(
            actions_card, text="오프라인 설치 시작 (Install)", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            fg_color=self.accent_color, text_color="#FFFFFF", hover_color="#0052CC",
            height=40, command=self.start_install
        )
        self.install_btn.pack(fill="x", padx=20, pady=(15, 10))
        
        self.offline_status_label = ctk.CTkLabel(
            actions_card, text="대기 중... 설치 시작 버튼을 누르시면 오프라인 팩 환경구성이 실행됩니다.", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            anchor="w"
        )
        self.offline_status_label.pack(fill="x", padx=20, pady=(0, 5))
        
        self.offline_progress_bar = ctk.CTkProgressBar(actions_card, height=8)
        self.offline_progress_bar.pack(fill="x", padx=20, pady=(0, 15))
        self.offline_progress_bar.set(0.0)
        
        self.offline_console_card = ctk.CTkFrame(self.content_frame_offline)
        self.offline_console_card.pack(fill="x", pady=10)
        
        console_title = ctk.CTkLabel(
            self.offline_console_card, text="오프라인 설치 진행 로그 콘솔", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold")
        )
        console_title.pack(anchor="w", padx=20, pady=(10, 4))
        
        self.offline_log_text = ctk.CTkTextbox(
            self.offline_console_card, height=150, 
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#18181B", text_color="#F4F4F5"
        )
        self.offline_log_text.pack(fill="x", padx=20, pady=(0, 15))
        
    def setup_online_tab(self) -> None:
        """
        '인터넷망 다운로더' 탭 화면 구성요소를 구축합니다.
        """
        # Header
        tab_header = ctk.CTkLabel(
            self.content_frame_online, text="🌐 인터넷망 모드 (다운로드/내보내기)", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=22, weight="bold"),
            anchor="w"
        )
        tab_header.pack(fill="x", pady=(10, 5))
        
        tab_desc = ctk.CTkLabel(
            self.content_frame_online, 
            text="인터넷 연결 환경에서 폐쇄망용 오프라인 인스톨러 바이너리를 패키징하여 폴더로 내보냅니다.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12), text_color="gray", anchor="w"
        )
        tab_desc.pack(fill="x", pady=(0, 20))
        
        # 1. Action Bypass Config Card
        ssl_card = ctk.CTkFrame(self.content_frame_online)
        ssl_card.pack(fill="x", pady=10)
        
        ssl_title = ctk.CTkLabel(
            ssl_card, text="사내 보안망 SSL 프록시 우회 설정", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold")
        )
        ssl_title.pack(anchor="w", padx=20, pady=(15, 8))
        
        self.ssl_segments = ctk.CTkSegmentedButton(
            ssl_card, values=["Standard (일반)", "System Certs (OS 인증서)", "Trusted Host (PyPI 신뢰)"],
            command=self.ssl_segment_changed,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold")
        )
        self.ssl_segments.pack(fill="x", padx=20, pady=(5, 15))
        self.ssl_segments.set("Standard (일반)")
        
        # 2. Package Downloader Card
        pkg_card = ctk.CTkFrame(self.content_frame_online)
        pkg_card.pack(fill="x", pady=10)
        
        pkg_title = ctk.CTkLabel(
            pkg_card, text="내보낼 환경 옵션 및 타겟 경로 설정", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold")
        )
        pkg_title.pack(anchor="w", padx=20, pady=(15, 10))
        
        py_frame = ctk.CTkFrame(pkg_card, fg_color="transparent")
        py_frame.pack(fill="x", padx=20, pady=5)
        
        py_label = ctk.CTkLabel(py_frame, text="내보낼 Python 버전 선택:", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"))
        py_label.pack(side="left", padx=(0, 10))
        
        self.bypass_py_combo = ctk.CTkOptionMenu(
            py_frame, values=["3.9", "3.10", "3.11", "3.12", "3.13"],
            variable=self.bypass_py_var,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12)
        )
        self.bypass_py_combo.pack(side="left")
        
        # Export target path
        exp_label = ctk.CTkLabel(pkg_card, text="내보낼 폴더 경로 (Export Directory)", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"))
        exp_label.pack(anchor="w", padx=20, pady=(10, 0))
        
        exp_frame = ctk.CTkFrame(pkg_card, fg_color="transparent")
        exp_frame.pack(fill="x", padx=20, pady=(5, 15))
        
        self.bypass_export_entry = ctk.CTkEntry(exp_frame, font=ctk.CTkFont(size=12))
        default_export_dir = os.path.join(os.getcwd(), "uvtool-bypass-pack")
        self.bypass_export_entry.insert(0, default_export_dir)
        self.bypass_export_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        exp_btn = ctk.CTkButton(
            exp_frame, text="변경...", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            width=100, command=self.browse_bypass_export_dir
        )
        exp_btn.pack(side="left")
        
        # 3. Action / Progress
        actions_card_online = ctk.CTkFrame(self.content_frame_online)
        actions_card_online.pack(fill="x", pady=10)
        
        self.export_btn = ctk.CTkButton(
            actions_card_online, text="설치 팩 다운로드 및 내보내기 (Export)", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            fg_color=self.accent_color, text_color="#FFFFFF", hover_color="#0052CC",
            height=40, command=self.start_bypass_export
        )
        self.export_btn.pack(fill="x", padx=20, pady=(15, 10))
        
        self.online_status_label = ctk.CTkLabel(
            actions_card_online, text="대기 중... 내보내기 버튼을 누르시면 CPython 및 uv 바이너리를 취합 수집합니다.", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            anchor="w"
        )
        self.online_status_label.pack(fill="x", padx=20, pady=(0, 5))
        
        self.online_progress_bar = ctk.CTkProgressBar(actions_card_online, height=8)
        self.online_progress_bar.pack(fill="x", padx=20, pady=(0, 15))
        self.online_progress_bar.set(0.0)
        
        self.online_console_card = ctk.CTkFrame(self.content_frame_online)
        self.online_console_card.pack(fill="x", pady=10)
        
        console_title_on = ctk.CTkLabel(
            self.online_console_card, text="인터넷망 다운로드 진행 로그 콘솔", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold")
        )
        console_title_on.pack(anchor="w", padx=20, pady=(10, 4))
        
        self.online_log_text = ctk.CTkTextbox(
            self.online_console_card, height=150, 
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#18181B", text_color="#F4F4F5"
        )
        self.online_log_text.pack(fill="x", padx=20, pady=(0, 15))
        
    def ssl_segment_changed(self, value: str) -> None:
        """
        보안망 SSL 프록시 우회 방식 설정 세그먼트 버튼 선택 시 상태 변수를 갱신합니다.
        """
        if "Standard" in value:
            self.ssl_bypass_var.set("standard")
        elif "System" in value:
            self.ssl_bypass_var.set("system_certs")
        else:
            self.ssl_bypass_var.set("trusted_host")
            
    def load_package_info(self) -> None:
        """
        로컬 페이로드 경로 상의 설치 팩 파일을 감지하여 파일명 및 라이브러리 목록 정보를 로드하고 화면에 표시합니다.
        """
        try:
            scan_dir = self.payload_dir
            if hasattr(self, 'package_path_entry'):
                val = self.package_path_entry.get().strip()
                if val:
                    scan_dir = val
                    
            info = get_bundled_info(scan_dir)
            install_dir = self.install_path_entry.get().strip()
            existing_uv = False
            if install_dir:
                existing_uv = os.path.exists(os.path.join(install_dir, "uv.exe"))
            
            if not info["uv_archive"]:
                if existing_uv:
                    self.uv_val.configure(text="기존 설치된 uv 사용", text_color="#00D4B2")
                    self.install_btn.configure(state="normal")
                else:
                    self.uv_val.configure(text="없음 (기존 설치본 필요)", text_color="gray")
                    self.install_btn.configure(state="normal")
            else:
                uv_name = os.path.basename(info["uv_archive"])
                self.uv_val.configure(text=uv_name, text_color=("gray10", "gray90"))
                self.install_btn.configure(state="normal")
            
            py_names = [os.path.basename(p) for p in info["python_archives"]]
            py_versions = []
            for name in py_names:
                try:
                    ver = name.split('-')[1].split('+')[0]
                    py_versions.append(f"Python {ver}")
                except Exception:
                    py_versions.append(name)
                    
            if py_versions:
                self.py_val.configure(text=", ".join(py_versions))
            else:
                self.py_val.configure(text="없음 (uv 단독 설치)", text_color="gray")
                
            wheel_names = [os.path.basename(w).split('-')[0] for w in info["wheels"]]
            wheel_names = sorted(list(set(wheel_names)))
            if wheel_names:
                self.pkg_val.configure(text=f"{len(info['wheels'])}개 라이브러리 포함 ({', '.join(wheel_names[:8])}...)" if len(wheel_names) > 8 else f"{len(info['wheels'])}개 라이브러리 ({', '.join(wheel_names)})")
            else:
                self.pkg_val.configure(text="없음 (라이브러리 미포함)", text_color="gray")
                
        except Exception as e:
            messagebox.showerror("스캔 에러", f"설치팩 정보 스캔 중 실패: {e}")
            
    def browse_install_dir(self) -> None:
        """
        설치 대상 디렉토리 지정을 위한 폴더 탐색기 다이얼로그를 엽니다.
        """
        path = filedialog.askdirectory(initialdir=self.install_path_entry.get())
        if path:
            self.install_path_entry.delete(0, "end")
            self.install_path_entry.insert(0, os.path.normpath(path))
            self.load_package_info()
            
    def browse_package_dir(self) -> None:
        """
        오프라인 설치용 패키지가 들어있는 디렉토리 지정을 위한 폴더 탐색기 다이얼로그를 엽니다.
        """
        path = filedialog.askdirectory(initialdir=self.package_path_entry.get())
        if path:
            self.package_path_entry.delete(0, "end")
            self.package_path_entry.insert(0, os.path.normpath(path))
            self.load_package_info()
            
    def browse_bypass_export_dir(self) -> None:
        """
        인터넷망 다운로드 후 저장될 대상 디렉토리 지정을 위한 폴더 탐색기 다이얼로그를 엽니다.
        """
        path = filedialog.askdirectory(initialdir=self.bypass_export_entry.get())
        if path:
            self.bypass_export_entry.delete(0, "end")
            self.bypass_export_entry.insert(0, os.path.normpath(path))
            
    def append_log(self, text: str) -> None:
        """
        로그 콘솔 화면 위젯에 텍스트 메시지를 개행을 포함하여 추가합니다.
        """
        mode = self.installer_mode_var.get()
        log_widget = self.offline_log_text if mode == "offline" else self.online_log_text
        log_widget.insert("end", text + "\n")
        log_widget.see("end")
        
    def update_progress(self, percent: float) -> None:
        """
        진행률 프로그레스 바 수치를 변경합니다.
        """
        mode = self.installer_mode_var.get()
        bar_widget = self.offline_progress_bar if mode == "offline" else self.online_progress_bar
        bar_widget.set(percent / 100.0)
        
    def update_status_text(self, text: str) -> None:
        """
        상태 알림 텍스트의 내용을 수정합니다.
        """
        mode = self.installer_mode_var.get()
        label_widget = self.offline_status_label if mode == "offline" else self.online_status_label
        label_widget.configure(text=text)
        
    def start_install(self) -> None:
        """
        로컬 오프라인 패키지를 풀어서 PC 환경에 주입하는 스레드 기동을 촉발합니다.
        """
        install_dir = self.install_path_entry.get().strip()
        if not install_dir:
            messagebox.showerror("입력 오류", "올바른 설치 경로를 지정하십시오.")
            return
            
        offline_mode = (self.installer_mode_var.get() == "offline")
        scan_dir = self.package_path_entry.get().strip() or self.payload_dir
        
        info = get_bundled_info(scan_dir)
        existing_uv = os.path.exists(os.path.join(install_dir, "uv.exe"))
        
        if offline_mode and not info["uv_archive"] and not existing_uv:
            messagebox.showerror("설치 오류", "설치 아카이브 파일이 없으며 기존에 설치된 uv.exe도 감지되지 않았습니다. 폐쇄망 모드가 활성화되어 외부 다운로드를 실행할 수 없습니다.")
            return
            
        self.install_btn.configure(state="disabled")
        self.offline_progress_bar.set(0.0)
        self.offline_log_text.delete("1.0", "end")
        
        def thread_safe_log(msg):
            self.after(0, lambda: self.append_log(msg))
            
        def thread_safe_progress(pct):
            self.after(0, lambda: self.update_progress(pct))
            
        def thread_safe_status(txt):
            self.after(0, lambda: self.update_status_text(txt))
            
        def run():
            try:
                thread_safe_status("오프라인 간편 설치 작업 실행 중...")
                thread_safe_log("[START] 오프라인 환경 구성을 위한 압축 해제 및 레지스트리 설정을 시작합니다.")
                
                success = install_offline(
                    payload_dir=scan_dir,
                    install_dir=install_dir,
                    log_callback=thread_safe_log,
                    progress_callback=thread_safe_progress,
                    register_global_env=self.global_env_var.get(),
                    offline_mode=offline_mode,
                    ssl_bypass=self.ssl_bypass_var.get()
                )
                
                if success:
                    thread_safe_status("설치 완료!")
                    def complete_and_exit():
                        messagebox.showinfo(
                            "설치 완료",
                            "uv 오프라인 설치 환경 구성이 성공적으로 완료되었습니다!\n\n"
                            "새로운 터미널(PowerShell/CMD) 창을 열고 아래 명령어를 통해 정상 작동을 확인하십시오:\n\n"
                            "1. uv --version\n"
                            "2. python --version\n"
                            "3. uv pip install [라이브러리명]"
                        )
                        self.destroy()
                    self.after(0, complete_and_exit)
            except Exception as e:
                thread_safe_status("설치 중 에러 발생")
                thread_safe_log(f"[ERROR] 설치 실패: {e}")
                self.after(0, lambda: messagebox.showerror("설치 실패", f"설치 중 문제가 발생하였습니다:\n{e}"))
            finally:
                self.after(0, lambda: self.install_btn.configure(state="normal"))
                
        threading.Thread(target=run, daemon=True).start()
        
    def start_bypass_export(self) -> None:
        """
        인터넷을 통해 원본 uv.exe 및 Python 런타임 압축본을 내려받아
        오프라인 설치 환경 구성용 단독 폴더를 생성 및 내보내기합니다.
        """
        export_dir = self.bypass_export_entry.get().strip()
        py_ver = self.bypass_py_var.get()
        if not export_dir:
            messagebox.showerror("입력 오류", "내보낼 폴더 경로를 지정하십시오.")
            return
            
        self.export_btn.configure(state="disabled")
        self.online_progress_bar.set(0.0)
        self.online_log_text.delete("1.0", "end")
        
        def thread_safe_log(msg: str) -> None:
            self.after(0, lambda: self.append_log(msg))
        def thread_safe_progress(pct: float) -> None:
            self.after(0, lambda: self.update_progress(pct))
        def thread_safe_status(txt: str) -> None:
            self.after(0, lambda: self.update_status_text(txt))
            
        ssl_bypass = self.ssl_bypass_var.get()
        
        def run_export() -> None:
            try:
                thread_safe_status("우회 설치 팩 내보내는 중...")
                thread_safe_log(f"[START] 우회 패키징 준비 시작 (대상 경로: {export_dir}, SSL 모드: {ssl_bypass})")
                
                os.makedirs(export_dir, exist_ok=True)
                
                # 1. Download CPython Standalone Windows
                thread_safe_progress(0)
                thread_safe_log("[DOWNLOAD] 1. CPython Standalone 런타임 정보 조회 중...")
                plat = get_platform_info("windows", "x86_64")
                pbp_url, pbp_archive_name = get_python_asset_url(py_ver, plat, thread_safe_log)
                py_dest_path = os.path.join(export_dir, pbp_archive_name)
                
                thread_safe_log(f"[DOWNLOAD] CPython Standalone 다운로드 시작: {pbp_archive_name}")
                
                def py_progress(pct):
                    thread_safe_progress(int(pct * 0.6))
                    
                download_file(pbp_url, py_dest_path, progress_callback=py_progress, status_callback=thread_safe_log, ssl_bypass=ssl_bypass)
                thread_safe_log(f"[SUCCESS] CPython Standalone 다운로드 완료: {py_dest_path}")
                
                # 2. Download Windows uv binary
                thread_safe_progress(60)
                uv_archive_name = "uv-x86_64-pc-windows-msvc.zip"
                uv_url = f"https://github.com/astral-sh/uv/releases/latest/download/{uv_archive_name}"
                uv_dest_path = os.path.join(export_dir, uv_archive_name)
                
                thread_safe_log(f"[DOWNLOAD] 2. uv 윈도우 바이너리 다운로드 시작: {uv_archive_name}")
                
                def uv_progress(pct):
                    thread_safe_progress(60 + int(pct * 0.3))
                    
                download_file(uv_url, uv_dest_path, progress_callback=uv_progress, status_callback=thread_safe_log, ssl_bypass=ssl_bypass)
                thread_safe_log(f"[SUCCESS] uv 바이너리 다운로드 완료: {uv_dest_path}")
                
                # 3. Export installer EXE/Script
                thread_safe_progress(70)
                is_frozen = getattr(sys, 'frozen', False)
                
                if is_frozen:
                    thread_safe_log("[EXPORT] 3. 컴파일된 installer_gui.exe 내보내는 중...")
                    exe_src = sys.executable
                    exe_dest = os.path.join(export_dir, "installer_gui.exe")
                    shutil.copy2(exe_src, exe_dest)
                    thread_safe_log(f"[SUCCESS] installer_gui.exe 내보내기 완료: {exe_dest}")
                    
                    ps1_src = os.path.join(os.path.dirname(exe_src), "install_offline.ps1")
                    if os.path.exists(ps1_src):
                        shutil.copy2(ps1_src, os.path.join(export_dir, "install_offline.ps1"))
                        thread_safe_log("[SUCCESS] install_offline.ps1 함께 내보내기 완료.")
                else:
                    thread_safe_log("[EXPORT] 3. 인스톨러 파이썬 소스 코드(.py) 내보내는 중...")
                    base_src_dir = os.path.dirname(os.path.abspath(__file__))
                    
                    src_folder_origin = os.path.join(base_src_dir, "src")
                    src_folder_dest = os.path.join(export_dir, "src")
                    if os.path.exists(src_folder_dest):
                        shutil.rmtree(src_folder_dest)
                    if os.path.exists(src_folder_origin):
                        shutil.copytree(src_folder_origin, src_folder_dest,
                                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                                        
                    installer_py_src = os.path.join(base_src_dir, "installer_gui.py")
                    if os.path.exists(installer_py_src):
                        shutil.copy2(installer_py_src, os.path.join(export_dir, "installer_gui.py"))
                        
                    ps1_src = os.path.join(base_src_dir, "install_offline.ps1")
                    if os.path.exists(ps1_src):
                        shutil.copy2(ps1_src, os.path.join(export_dir, "install_offline.ps1"))
                        
                    thread_safe_log("[SUCCESS] 소스 코드 내보내기 완료.")
                    
                # 4. Generate Launcher Bat files
                thread_safe_progress(90)
                thread_safe_log("[GENERATE] 4. 원클릭 실행 배치 파일 생성 중...")
                
                if is_frozen:
                    bat_content = (
                        "@echo off\n"
                        "echo ==========================================================\n"
                        "echo           uvtool Offline Installer Launcher\n"
                        "echo ==========================================================\n"
                        "echo.\n"
                        "cd /d \"%~dp0\"\n\n"
                        "rem 1. Extract Python Standalone Runtime\n"
                        "if not exist \"py_runtime\\python.exe\" (\n"
                        "    echo [INFO] 파이썬 독립 실행 런타임의 압축을 해제합니다...\n"
                        "    mkdir py_runtime 2>nul\n"
                        "    for %%f in (cpython-*.tar.gz) do tar -xzf \"%%f\" -C py_runtime --strip-components=1 2>nul\n"
                        ")\n\n"
                        "rem 2. Launch installer_gui.exe directly\n"
                        "if exist \"installer_gui.exe\" (\n"
                        "    echo [SUCCESS] installer_gui.exe 를 실행합니다.\n"
                        "    start \"\" \"installer_gui.exe\"\n"
                        ") else (\n"
                        "    echo [ERROR] installer_gui.exe 를 찾을 수 없습니다.\n"
                        "    pause\n"
                        ")\n"
                    )
                else:
                    bat_content = (
                        "@echo off\n"
                        "echo ==========================================================\n"
                        "echo           uvtool Security Policy Bypass Launcher\n"
                        "echo ==========================================================\n"
                        "echo.\n"
                        "cd /d \"%~dp0\"\n\n"
                        "rem 1. Extract Python Standalone Runtime\n"
                        "if not exist \"py_runtime\\python.exe\" (\n"
                        "    echo [INFO] 파이썬 독립 실행 런타임의 압축을 해제합니다...\n"
                        "    mkdir py_runtime 2>nul\n"
                        "    for %%f in (cpython-*.tar.gz) do tar -xzf \"%%f\" -C py_runtime --strip-components=1 2>nul\n"
                        ")\n\n"
                        "rem 2. Extract uv.exe\n"
                        "if not exist \"uv.exe\" (\n"
                        "    echo [INFO] uv 바이너리 압축을 해제합니다...\n"
                        "    powershell -Command \"Expand-Archive -Path (Get-ChildItem uv-*.zip | Select -First 1).FullName -DestinationPath temp_uv -Force; Copy-Item temp_uv\\*\\uv.exe .; Remove-Item temp_uv -Recurse -Force\" 2>nul\n"
                        ")\n\n"
                        "rem 3. Execute installer_gui.py using the bundled python\n"
                        "if exist \"py_runtime\\python.exe\" (\n"
                        "    echo [SUCCESS] 인스톨러를 시작합니다.\n"
                        "    start \"\" \"py_runtime\\python.exe\" \"installer_gui.py\"\n"
                        ") else (\n"
                        "    echo [ERROR] 파이썬 독립 실행 런타임을 준비하지 못했습니다.\n"
                        "    pause\n"
                        ")\n"
                    )
                    
                bat_dest_path = os.path.join(export_dir, "run_installer.bat")
                with open(bat_dest_path, "w", encoding="euc-kr") as bf:
                    bf.write(bat_content)
                thread_safe_log("[SUCCESS] run_installer.bat 생성 완료.")
                
                thread_safe_progress(100)
                thread_safe_status("내보내기 성공!")
                self.after(0, lambda: messagebox.showinfo("내보내기 완료", f"우회 설치 팩 내보내기가 완료되었습니다!\n\n경로: {export_dir}"))
            except Exception as e:
                thread_safe_status("내보내기 실패")
                thread_safe_log(f"[ERROR] 내보내기 중 실패: {e}")
                self.after(0, lambda: messagebox.showerror("내보내기 실패", f"내보내기 중 문제가 발생하였습니다:\n{e}"))
            finally:
                self.after(0, lambda: self.export_btn.configure(state="normal"))
                
        threading.Thread(target=run_export, daemon=True).start()

if __name__ == "__main__":
    if sys.platform == 'win32':
        import ctypes
        myappid = 'google.deepmind.uvtool.installer.2.1'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        
    app = InstallerApp()
    app.mainloop()
