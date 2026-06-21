import json
import os
import re
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

from src.builder import build_package, detect_project_settings

# Configure global theme styling
ctk.set_appearance_mode("System")  # Options: "System", "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue", "green", "dark-blue"

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


class BuilderApp(ctk.CTk):
    """
    uvtool 오프라인 패키지 빌더 GUI 애플리케이션 클래스입니다.
    사용자가 원하는 대상 OS, 아키텍처, 파이썬 버전 및 추가 라이브러리를 지정하여
    폐쇄망용 오프라인 압축 패키지를 빌드할 수 있는 화면을 제공합니다.
    """

    def __init__(self) -> None:
        super().__init__()
        
        self.title("uvtool - 오프라인 패키지 빌더 (Builder)")
        self.geometry("900x750")
        self.minsize(800, 650)
        
        # Color configuration (Toss Minimal / Slate Theme)
        self.accent_color = "#0064FF"  # Toss Blue
        
        # UI State variables
        self.target_os_var = tk.StringVar(value="windows")
        self.target_arch_var = tk.StringVar(value="x86_64")
        self.package_scope_var = tk.StringVar(value="all")
        self.ssl_bypass_var = tk.StringVar(value="standard")
        
        # Python Checkbox variables
        self.py_versions = ["3.9", "3.10", "3.11", "3.12", "3.13"]
        self.py_vars = {}
        self.py_checkboxes = {}
        
        for ver in self.py_versions:
            self.py_vars[ver] = tk.BooleanVar(value=(ver == "3.11"))
            
        self.setup_ui()
        
    def setup_ui(self) -> None:
        """
        메인 윈도우 UI 레이아웃(좌측 사이드바 및 우측 메인 콘텐츠 프레임)을 구성합니다.
        """
        # Configure Grid Layout (1 row, 2 columns: Sidebar & Content)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # 1. Sidebar Frame
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(5, weight=1)  # spacer
        
        # Sidebar Logo Header
        self.logo_label = ctk.CTkLabel(
            self.sidebar_frame, 
            text="uvtool Builder", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=20, weight="bold"),
            text_color=self.accent_color
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(25, 5))
        
        self.sub_logo_label = ctk.CTkLabel(
            self.sidebar_frame, 
            text="오프라인 패키지 빌더", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color="gray"
        )
        self.sub_logo_label.grid(row=1, column=0, padx=20, pady=(0, 25))
        
        # Sidebar Navigation Buttons
        self.nav_btn_project = ctk.CTkButton(
            self.sidebar_frame, text="프로젝트 동기화 설정", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            anchor="w", fg_color="transparent", text_color=("gray10", "gray90"),
            hover_color=("gray70", "gray30"), command=lambda: self.select_tab("project")
        )
        self.nav_btn_project.grid(row=2, column=0, padx=15, pady=8, sticky="ew")
        
        self.nav_btn_settings = ctk.CTkButton(
            self.sidebar_frame, text="고급 환경 설정", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            anchor="w", fg_color="transparent", text_color=("gray10", "gray90"),
            hover_color=("gray70", "gray30"), command=lambda: self.select_tab("settings")
        )
        self.nav_btn_settings.grid(row=3, column=0, padx=15, pady=8, sticky="ew")
        
        self.nav_btn_logs = ctk.CTkButton(
            self.sidebar_frame, text="빌드 및 콘솔 로그", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            anchor="w", fg_color="transparent", text_color=("gray10", "gray90"),
            hover_color=("gray70", "gray30"), command=lambda: self.select_tab("logs")
        )
        self.nav_btn_logs.grid(row=4, column=0, padx=15, pady=8, sticky="ew")
        
        # Appearance Mode Controls at Sidebar Bottom
        self.appearance_label = ctk.CTkLabel(
            self.sidebar_frame, text="테마 모드 선택:", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold")
        )
        self.appearance_label.grid(row=6, column=0, padx=20, pady=(10, 5), sticky="w")
        
        self.appearance_menu = ctk.CTkOptionMenu(
            self.sidebar_frame, values=["System", "Dark", "Light"],
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            command=self.change_appearance_mode
        )
        self.appearance_menu.grid(row=7, column=0, padx=20, pady=(0, 25), sticky="ew")
        
        # 2. Main Content Tab Views
        self.content_frame_project = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        self.content_frame_settings = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        self.content_frame_logs = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        
        # Setup specific frames
        self.setup_project_tab()
        self.setup_settings_tab()
        self.setup_logs_tab()
        
        # Default view active
        self.select_tab("project")
        
    def select_tab(self, name: str) -> None:
        """
        네비게이션 사이드바 클릭 시 해당하는 우측 서브 화면 탭으로 전환합니다.

        Args:
            name (str): 전환할 탭 이름 ("project", "settings", "logs").
        """
        # 모든 메인 콘텐츠 뷰 숨김
        self.content_frame_project.grid_forget()
        self.content_frame_settings.grid_forget()
        self.content_frame_logs.grid_forget()
        
        # 네비게이션 버튼 스타일 초기화
        self.nav_btn_project.configure(fg_color="transparent", text_color=("gray10", "gray90"))
        self.nav_btn_settings.configure(fg_color="transparent", text_color=("gray10", "gray90"))
        self.nav_btn_logs.configure(fg_color="transparent", text_color=("gray10", "gray90"))
        
        # 선택한 탭 표시 및 활성화 효과 적용
        if name == "project":
            self.content_frame_project.grid(row=0, column=1, sticky="nsew", padx=25, pady=25)
            self.nav_btn_project.configure(fg_color=self.accent_color, text_color="#FFFFFF")
        elif name == "settings":
            self.content_frame_settings.grid(row=0, column=1, sticky="nsew", padx=25, pady=25)
            self.nav_btn_settings.configure(fg_color=self.accent_color, text_color="#FFFFFF")
        elif name == "logs":
            self.content_frame_logs.grid(row=0, column=1, sticky="nsew", padx=25, pady=25)
            self.nav_btn_logs.configure(fg_color=self.accent_color, text_color="#FFFFFF")

    def change_appearance_mode(self, mode: str) -> None:
        """
        GUI 애플리케이션의 화면 테마 모드를 전환합니다.

        Args:
            mode (str): 설정할 테마 이름 ("System", "Dark", "Light").
        """
        ctk.set_appearance_mode(mode)
        
    def setup_project_tab(self) -> None:
        """
        '프로젝트 동기화 설정' 탭 화면 구성요소를 구축합니다.
        """
        # Tab Header
        tab_header = ctk.CTkLabel(
            self.content_frame_project, text="프로젝트 동기화 설정", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=22, weight="bold"),
            anchor="w"
        )
        tab_header.pack(fill="x", pady=(10, 5))
        
        tab_desc = ctk.CTkLabel(
            self.content_frame_project, 
            text="개발 프로젝트(pyproject.toml/uv.lock) 경로를 입력하면 버전을 자동 감지해 휠들을 모아줍니다.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12), text_color="gray", anchor="w"
        )
        tab_desc.pack(fill="x", pady=(0, 20))
        
        # 1. Project Selector Card
        project_card = ctk.CTkFrame(self.content_frame_project)
        project_card.pack(fill="x", pady=10)
        
        project_title = ctk.CTkLabel(
            project_card, text="프로젝트 디렉토리 경로 지정", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold")
        )
        project_title.pack(anchor="w", padx=20, pady=(15, 8))
        
        input_frame = ctk.CTkFrame(project_card, fg_color="transparent")
        input_frame.pack(fill="x", padx=20, pady=(0, 10))
        
        self.project_path_entry = ctk.CTkEntry(
            input_frame, placeholder_text="예: C:/Users/Documents/GitHub/myproject",
            font=ctk.CTkFont(size=12)
        )
        self.project_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        browse_btn = ctk.CTkButton(
            input_frame, text="찾아보기...", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            width=100, command=self.browse_project
        )
        browse_btn.pack(side="left", padx=(0, 8))
        
        self.detect_btn = ctk.CTkButton(
            input_frame, text="자동 감지", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=self.accent_color, text_color="#FFFFFF", hover_color="#0052CC",
            width=100, command=self.analyze_project
        )
        self.detect_btn.pack(side="left")
        
        self.project_status_label = ctk.CTkLabel(
            project_card, text="프로젝트를 선택하고 [자동 감지] 버튼을 눌러 설정을 분석하세요.", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=11), text_color="gray"
        )
        self.project_status_label.pack(anchor="w", padx=20, pady=(0, 15))
        
        # 2. Scope & Target Card
        scope_card = ctk.CTkFrame(self.content_frame_project)
        scope_card.pack(fill="x", pady=10)
        
        scope_title = ctk.CTkLabel(
            scope_card, text="대상 OS 및 아키텍처 설정", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold")
        )
        scope_title.pack(anchor="w", padx=20, pady=(15, 10))
        
        # Target OS Segments
        os_label = ctk.CTkLabel(scope_card, text="대상 운영체제 (OS)", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"))
        os_label.pack(anchor="w", padx=20)
        self.os_segments = ctk.CTkSegmentedButton(
            scope_card, values=["Windows", "Linux"], 
            command=self.os_segment_changed,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold")
        )
        self.os_segments.pack(fill="x", padx=20, pady=(5, 15))
        self.os_segments.set("Windows")
        
        # Target Arch Segments
        arch_label = ctk.CTkLabel(scope_card, text="대상 아키텍처 (Arch)", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"))
        arch_label.pack(anchor="w", padx=20)
        self.arch_segments = ctk.CTkSegmentedButton(
            scope_card, values=["x86_64 (Intel/AMD)", "aarch64 (ARM64)"], 
            command=self.arch_segment_changed,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold")
        )
        self.arch_segments.pack(fill="x", padx=20, pady=(5, 15))
        self.arch_segments.set("x86_64 (Intel/AMD)")
        
        # 3. Python Versions Selection Card
        py_card = ctk.CTkFrame(self.content_frame_project)
        py_card.pack(fill="x", pady=10)
        
        py_title = ctk.CTkLabel(
            py_card, text="포함할 Python 버전 선택", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold")
        )
        py_title.pack(anchor="w", padx=20, pady=(15, 10))
        
        # Grid layout for checkbox row
        self.checkbox_frame = ctk.CTkFrame(py_card, fg_color="transparent")
        self.checkbox_frame.pack(fill="x", padx=20, pady=5)
        
        for idx, ver in enumerate(self.py_versions):
            cb = ctk.CTkCheckBox(
                self.checkbox_frame, text=f"Python {ver}",
                variable=self.py_vars[ver],
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
            )
            cb.grid(row=0, column=idx, padx=10, pady=5, sticky="w")
            self.py_checkboxes[ver] = cb
            
        custom_py_frame = ctk.CTkFrame(py_card, fg_color="transparent")
        custom_py_frame.pack(fill="x", padx=20, pady=(10, 15))
        
        custom_py_label = ctk.CTkLabel(custom_py_frame, text="기타 버전 직접 추가:", font=ctk.CTkFont(family=FONT_FAMILY, size=12))
        custom_py_label.pack(side="left", padx=(0, 8))
        
        self.custom_py_entry = ctk.CTkEntry(
            custom_py_frame, placeholder_text="예: 3.12.3", width=120,
            font=ctk.CTkFont(size=12)
        )
        self.custom_py_entry.pack(side="left", padx=(0, 8))
        
        add_py_btn = ctk.CTkButton(
            custom_py_frame, text="추가", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            width=60, command=self.add_custom_python
        )
        add_py_btn.pack(side="left")

    def setup_settings_tab(self) -> None:
        """
        '고급 환경 설정' 탭 화면 구성요소를 구축합니다.
        """
        # Tab Header
        tab_header = ctk.CTkLabel(
            self.content_frame_settings, text="고급 환경 설정", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=22, weight="bold"),
            anchor="w"
        )
        tab_header.pack(fill="x", pady=(10, 5))
        
        tab_desc = ctk.CTkLabel(
            self.content_frame_settings, 
            text="빌드 범위 지정, 프록시 SSL 우회 및 세부 휠 의존성 목록을 정의합니다.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12), text_color="gray", anchor="w"
        )
        tab_desc.pack(fill="x", pady=(0, 20))
        
        # 1. Package Scope Selection Card
        scope_card = ctk.CTkFrame(self.content_frame_settings)
        scope_card.pack(fill="x", pady=10)
        
        scope_title = ctk.CTkLabel(
            scope_card, text="패키지 압축 범위 설정 (Scope)", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold")
        )
        scope_title.pack(anchor="w", padx=20, pady=(15, 8))
        
        self.scope_segments = ctk.CTkSegmentedButton(
            scope_card, values=["전체 압축 (Full)", "신규 변경 압축 (Incremental)"], 
            command=self.scope_segment_changed,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold")
        )
        self.scope_segments.pack(fill="x", padx=20, pady=(5, 12))
        self.scope_segments.set("전체 압축 (Full)")
        
        action_frame = ctk.CTkFrame(scope_card, fg_color="transparent")
        action_frame.pack(fill="x", padx=20, pady=(0, 15))
        
        scope_help = ctk.CTkLabel(
            action_frame, text="💡 증분 압축은 캐시에 등록된 이전 휠들을 빌드에서 배제해 전송 크기를 줄여줍니다.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11), text_color="gray"
        )
        scope_help.pack(side="left", fill="x", expand=True, anchor="w")
        
        self.reset_reg_btn = ctk.CTkButton(
            action_frame, text="신규패키지 기준 초기화", font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color="#F04452", hover_color="#C0392B", text_color="#FFFFFF",
            width=150, command=self.reset_wheel_registry
        )
        self.reset_reg_btn.pack(side="right")
        
        # 2. UV Version & SSL Bypass Options Card
        ssl_card = ctk.CTkFrame(self.content_frame_settings)
        ssl_card.pack(fill="x", pady=10)
        
        ssl_title = ctk.CTkLabel(
            ssl_card, text="UV 버전 및 SSL 우회 옵션", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold")
        )
        ssl_title.pack(anchor="w", padx=20, pady=(15, 10))
        
        uv_v_frame = ctk.CTkFrame(ssl_card, fg_color="transparent")
        uv_v_frame.pack(fill="x", padx=20, pady=5)
        
        uv_v_label = ctk.CTkLabel(uv_v_frame, text="uv 설치 바이너리 버전 지정:", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"))
        uv_v_label.pack(side="left", padx=(0, 10))
        
        self.uv_version_entry = ctk.CTkEntry(uv_v_frame, font=ctk.CTkFont(size=12), width=150)
        self.uv_version_entry.insert(0, "latest")
        self.uv_version_entry.pack(side="left")
        
        ssl_label = ctk.CTkLabel(ssl_card, text="사내 보안망 SSL 프록시 우회 옵션:", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"))
        ssl_label.pack(anchor="w", padx=20, pady=(10, 5))
        
        # Segmented radio button mimics
        self.ssl_segments = ctk.CTkSegmentedButton(
            ssl_card, values=["Standard (일반)", "System Certs (OS 인증서)", "Trusted Host (PyPI 신뢰)"],
            command=self.ssl_segment_changed,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold")
        )
        self.ssl_segments.pack(fill="x", padx=20, pady=(0, 15))
        self.ssl_segments.set("Standard (일반)")
        
        # 3. Custom PIP List Card
        pip_card = ctk.CTkFrame(self.content_frame_settings)
        pip_card.pack(fill="x", pady=10)
        
        pip_title = ctk.CTkLabel(
            pip_card, text="수동 추가할 PIP 라이브러리 목록 (requirements.txt 형식)", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold")
        )
        pip_title.pack(anchor="w", padx=20, pady=(15, 5))
        
        self.pip_packages_text = ctk.CTkTextbox(
            pip_card, height=120, font=ctk.CTkFont(family="Consolas", size=12)
        )
        self.pip_packages_text.pack(fill="x", padx=20, pady=(0, 15))
        self.pip_packages_text.insert("end", "# 예: numpy\n# pandas>=2.0.0\n# requests\n")
        
        # 4. Output Zip Setting Card
        out_card = ctk.CTkFrame(self.content_frame_settings)
        out_card.pack(fill="x", pady=10)
        
        out_title = ctk.CTkLabel(
            out_card, text="저장할 오프라인 패키지 ZIP 파일 경로 지정", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold")
        )
        out_title.pack(anchor="w", padx=20, pady=(15, 8))
        
        out_frame = ctk.CTkFrame(out_card, fg_color="transparent")
        out_frame.pack(fill="x", padx=20, pady=(0, 15))
        
        self.output_path_entry = ctk.CTkEntry(
            out_frame, font=ctk.CTkFont(size=12)
        )
        default_out = os.path.join(os.getcwd(), "uv-offline-package.zip")
        self.output_path_entry.insert(0, default_out)
        self.output_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        out_browse_btn = ctk.CTkButton(
            out_frame, text="변경...", font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            width=100, command=self.browse_output
        )
        out_browse_btn.pack(side="left")

    def setup_logs_tab(self) -> None:
        """
        '빌드 및 콘솔 로그' 탭 화면 구성요소를 구축합니다.
        """
        # 1. Action & Progress section at Top
        action_card = ctk.CTkFrame(self.content_frame_logs)
        action_card.pack(fill="x", padx=20, pady=(15, 10))
        
        self.build_btn = ctk.CTkButton(
            action_card, text="오프라인 설치 팩 생성 (Build)", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            fg_color=self.accent_color, text_color="#FFFFFF", hover_color="#0052CC",
            height=45, command=self.start_build
        )
        self.build_btn.pack(fill="x", padx=20, pady=15)
        
        self.status_label = ctk.CTkLabel(
            action_card, text="대기 중... 빌드 버튼을 누르시면 오프라인 빌드가 수행됩니다.", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            anchor="w"
        )
        self.status_label.pack(fill="x", padx=20, pady=(0, 5))
        
        self.progress_bar = ctk.CTkProgressBar(action_card, height=10)
        self.progress_bar.pack(fill="x", padx=20, pady=(0, 15))
        self.progress_bar.set(0.0)
        
        # 2. Console Logs card
        logs_card = ctk.CTkFrame(self.content_frame_logs)
        logs_card.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        
        logs_title = ctk.CTkLabel(
            logs_card, text="상세 진행 상태 로그 콘솔", 
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold")
        )
        logs_title.pack(anchor="w", padx=20, pady=(12, 4))
        
        # Dark black CLI style textbox
        self.log_text = ctk.CTkTextbox(
            logs_card, font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#18181B", text_color="#F4F4F5"
        )
        self.log_text.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        
    def os_segment_changed(self, value: str) -> None:
        """
        대상 OS 변경 시 상태 변수를 갱신합니다.
        """
        if value == "Windows":
            self.target_os_var.set("windows")
        else:
            self.target_os_var.set("linux")
            
    def arch_segment_changed(self, value: str) -> None:
        """
        대상 CPU 아키텍처 변경 시 상태 변수를 갱신합니다.
        """
        if "x86_64" in value:
            self.target_arch_var.set("x86_64")
        else:
            self.target_arch_var.set("aarch64")
            
    def scope_segment_changed(self, value: str) -> None:
        """
        패키지 압축 범위(Full/Incremental) 선택 시 상태 변수를 갱신합니다.
        """
        if "전체" in value:
            self.package_scope_var.set("all")
        else:
            self.package_scope_var.set("new")
            
    def ssl_segment_changed(self, value: str) -> None:
        """
        보안망 우회 SSL 옵션 선택 시 상태 변수를 갱신합니다.
        """
        if "Standard" in value:
            self.ssl_bypass_var.set("standard")
        elif "System" in value:
            self.ssl_bypass_var.set("system_certs")
        else:
            self.ssl_bypass_var.set("trusted_host")
            
    def browse_project(self) -> None:
        """
        폴더 선택 모달을 띄워 로컬 프로젝트 디렉토리를 탐색하고 지정합니다.
        """
        path = filedialog.askdirectory()
        if path:
            self.project_path_entry.delete(0, "end")
            self.project_path_entry.insert(0, path)
            self.analyze_project()
            
    def browse_output(self) -> None:
        """
        파일 저장 다이얼로그를 띄워 오프라인 패키지가 저장될 zip 파일 경로를 설정합니다.
        """
        path = filedialog.asksaveasfilename(
            defaultextension=".zip",
            filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
            initialfile="uv-offline-package.zip"
        )
        if path:
            self.output_path_entry.delete(0, "end")
            self.output_path_entry.insert(0, path)
            
    def analyze_project(self) -> None:
        """
        입력된 프로젝트 디렉토리 내의 .python-version 및 pyproject.toml 파일을 분석하여
        Python 요구 버전을 자동 판별하고, 화면 UI 체크박스를 자동 토글합니다.
        """
        path = self.project_path_entry.get().strip()
        if not path:
            messagebox.showwarning("입력 확인", "프로젝트 디렉토리 경로가 입력되지 않았습니다.")
            return
            
        if not os.path.exists(path):
            messagebox.showerror("오류", "입력한 경로가 존재하지 않습니다.")
            return
            
        settings = detect_project_settings(path)
        if not settings:
            self.project_status_label.configure(
                text="⚠️ pyproject.toml 파일을 찾을 수 없습니다.", 
                text_color="#F04452"
            )
            messagebox.showwarning("분석 실패", "해당 디렉토리에 pyproject.toml 파일이 없습니다.")
            return
            
        status_parts = []
        status_parts.append("pyproject.toml 감지됨")
        
        if settings.get("has_uv_lock"):
            status_parts.append("uv.lock 감지됨")
        else:
            status_parts.append("uv.lock 없음")
            
        detected_pys = settings.get("python_versions")
        if detected_pys:
            status_parts.append(f"요구 Python: {', '.join(detected_pys)}")
            # 탐지된 파이썬 버전을 자동 체크하고 다른 버전들은 체크 해제
            for ver in self.py_vars:
                is_needed = (ver in detected_pys)
                self.py_vars[ver].set(is_needed)
                
        self.project_status_label.configure(
            text=f"✓ {' / '.join(status_parts)}", 
            text_color="#00D4B2"
        )
        messagebox.showinfo("분석 완료", "프로젝트 설정을 정상적으로 감지하고 Python 버전을 자동 체크했습니다.")

    def add_custom_python(self) -> None:
        """
        사용자가 텍스트 창에 입력한 추가 파이썬 버전을 체크박스 목록에 생성 및 체크합니다.
        """
        ver = self.custom_py_entry.get().strip()
        if not ver:
            return
            
        if not re.match(r"^\d+\.\d+(\.\d+)?$", ver):
            messagebox.showerror("입력 오류", "올바른 파이썬 버전 형식이 아닙니다 (예: 3.12.3 또는 3.11)")
            return
            
        if ver in self.py_vars:
            messagebox.showwarning("입력 경고", "이미 존재하는 버전입니다.")
            self.custom_py_entry.delete(0, "end")
            return
            
        self.py_versions.append(ver)
        var = tk.BooleanVar(value=True)
        self.py_vars[ver] = var
        
        cb = ctk.CTkCheckBox(
            self.checkbox_frame, text=f"Python {ver}",
            variable=var,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
        )
        col = len(self.py_vars) - 1
        cb.grid(row=col // 5, column=col % 5, padx=10, pady=5, sticky="w")
        self.py_checkboxes[ver] = cb
        
        self.custom_py_entry.delete(0, "end")
        messagebox.showinfo("추가 완료", f"Python {ver} 버전이 목록에 추가되고 선택되었습니다.")
        
    def reset_wheel_registry(self) -> None:
        """
        신규 패키지 판정의 기준선 역할을 하는 다운로드 휠 레지스트리 캐시 파일을 영구 삭제하여 초기화합니다.
        """
        if getattr(sys, 'frozen', False):
            workspace_dir = os.path.dirname(sys.executable)
        else:
            workspace_dir = os.path.dirname(os.path.abspath(__file__))
            
        registry_file = os.path.join(workspace_dir, "cache", "downloaded_wheels.json")
        
        if not os.path.exists(registry_file):
            messagebox.showinfo(
                "초기화 완료",
                "신규패키지 기준 파일(downloaded_wheels.json)이 존재하지 않습니다.\n"
                "이미 초기화 상태입니다."
            )
            return
            
        try:
            with open(registry_file, "r", encoding="utf-8") as f:
                registry = json.load(f)
            count = len(registry)
        except Exception:
            count = -1
            
        count_msg = f"현재 {count}개 패키지가 기준으로 등록되어 있습니다.\n" if count >= 0 else ""
        
        confirmed = messagebox.askyesno(
            "신규패키지 기준 초기화",
            f"{count_msg}\n"
            "초기화 시 다음 빌드에서 모든 패키지가 '신규'로 인식되어\n"
            "'신규 패키지만 압축 (Incremental)' 옵션의 기준이 리셋됩니다.\n\n"
            "계속하시겠습니까?"
        )
        if not confirmed:
            return
            
        try:
            os.remove(registry_file)
            messagebox.showinfo(
                "초기화 완료",
                "신규패키지 기준(downloaded_wheels.json)이 성공적으로 초기화되었습니다.\n"
                "다음 빌드 시 모든 패키지가 신규로 분류됩니다."
            )
        except Exception as e:
            messagebox.showerror("초기화 실패", f"파일 삭제 중 오류가 발생했습니다:\n{e}")

    def append_log(self, text: str) -> None:
        """
        상세 진행 로그 텍스트 에어리어에 로그 메시지를 추가하고 스크롤을 하단으로 자동 조정합니다.
        """
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        
    def update_progress(self, percent: float) -> None:
        """
        진행률 프로그레스바 값을 갱신합니다. (CustomTkinter 프로그레스바는 0.0 ~ 1.0 범위를 가집니다)
        """
        self.progress_bar.set(percent / 100.0)
        
    def update_status_text(self, text: str) -> None:
        """
        UI 상태 레이블 텍스트를 변경합니다.
        """
        self.status_label.configure(text=text)
        
    def start_build(self) -> None:
        """
        지정된 폼 구성값들을 사용하여 백그라운드 스레드 상에서 오프라인 설치 패키지 생성 작업을 촉발합니다.
        """
        # 1. Gather form input
        target_os = self.target_os_var.get()
        target_arch = self.target_arch_var.get()
        uv_version = self.uv_version_entry.get().strip() or "latest"
        output_zip = self.output_path_entry.get().strip()
        ssl_bypass = self.ssl_bypass_var.get()
        project_path = self.project_path_entry.get().strip() or None
        
        selected_py = [ver for ver, var in self.py_vars.items() if var.get()]
        if not selected_py:
            messagebox.showerror("입력 오류", "최소 1개 이상의 Python 버전을 선택해주세요.")
            return
            
        pip_text = self.pip_packages_text.get("1.0", "end")
        pip_packages = []
        for line in pip_text.split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                pip_packages.append(line)
                
        if not pip_packages and not project_path:
            messagebox.showerror("입력 오류", "포함할 PIP 라이브러리 목록을 입력하거나 동기화 프로젝트 경로를 선택해주세요.")
            return
            
        if not output_zip:
            messagebox.showerror("입력 오류", "저장할 출력 ZIP 경로를 설정해주세요.")
            return
            
        # Switch tab view to Logs automatically when starting build
        self.select_tab("logs")
        self.build_btn.configure(state="disabled")
        self.progress_bar.set(0.0)
        self.log_text.delete("1.0", "end")
        
        # Thread Safe Callbacks
        def thread_safe_log(msg):
            self.after(0, lambda: self.append_log(msg))
            
        def thread_safe_progress(pct):
            self.after(0, lambda: self.update_progress(pct))
            
        def thread_safe_status(txt):
            self.after(0, lambda: self.update_status_text(txt))
            
        # Background thread execution
        def run():
            try:
                thread_safe_status("패키징 빌드 작업 진행 중...")
                thread_safe_log("[START] 빌드 프로세스를 준비합니다.")
                
                info = build_package(
                    target_os=target_os,
                    target_arch=target_arch,
                    uv_version=uv_version,
                    python_versions=selected_py,
                    pip_packages=pip_packages,
                    output_zip_path=output_zip,
                    log_callback=thread_safe_log,
                    progress_callback=thread_safe_progress,
                    package_scope=self.package_scope_var.get(),
                    ssl_bypass=ssl_bypass,
                    project_path=project_path
                )
                
                thread_safe_status("빌드 완료!")
                
                def show_result():
                    if info.get("size_warning"):
                        messagebox.showwarning(
                            "용량 초과 경고",
                            f"오프라인 패키지가 생성되었으나, 용량이 {info['zip_size'] / (1024*1024*1024):.2f} GB로 망연계 전송 한도(2GB)를 초과합니다!\n\n"
                            "해결을 위해 '신규 패키지만 압축 (Incremental)' 옵션을 사용하거나 파이썬 버전을 나누어 다시 빌드하는 것을 권장합니다."
                        )
                    else:
                        messagebox.showinfo(
                            "빌드 완료", 
                            f"오프라인 패키지가 성공적으로 생성되었습니다!\n\n경로: {output_zip}\n타겟 OS: {info['target_os'].upper()}\n포함된 패키지: {info['package_count']}개"
                        )
                self.after(0, show_result)
            except Exception as e:
                thread_safe_status("빌드 에러 발생")
                thread_safe_log(f"[ERROR] 빌드에 실패했습니다: {e}")
                self.after(0, lambda: messagebox.showerror("빌드 실패", f"에러가 발생하여 빌드가 취소되었습니다.\n\n상세 정보:\n{e}"))
            finally:
                self.after(0, lambda: self.build_btn.configure(state="normal"))
                
        t = threading.Thread(target=run, daemon=True)
        t.start()

if __name__ == "__main__":
    if sys.platform == 'win32':
        import ctypes
        myappid = 'google.deepmind.uvtool.builder.2.1'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        
        app = BuilderApp()
        app.mainloop()
