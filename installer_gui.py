import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from src.installer import get_bundled_info, install_offline
from src.builder import get_python_asset_url, get_platform_info
from src.utils import download_file

class InstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("uvtool - 오프라인 간편 설치기 (Installer)")
        self.root.geometry("680x710")
        self.root.minsize(600, 600)
        
        # UI Styling Colors (Modern Dark Theme matching Builder)
        self.bg_color = "#F2F4F6"      # Toss Light Background
        self.card_color = "#FFFFFF"    # Crisp White Cards
        self.fg_color = "#191F28"      # Toss Dark Grey Text
        self.fg_muted = "#6B7684"      # Toss Muted Gray Text
        self.accent_color = "#0064FF"    # Toss Vibrant Blue Accent
        self.success_color = "#00D4B2"   # Toss Teal/Green
        self.console_bg = "#191F28"     # Toss Dark Grey console background
        
        # Configure Root Background
        self.root.configure(bg=self.bg_color)
        
        # Style Mappings
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('.', background=self.bg_color, foreground=self.fg_color)
        self.style.configure('TLabel', background=self.bg_color, foreground=self.fg_color)
        self.style.configure('Card.TFrame', background=self.card_color, relief="flat")
        self.style.configure('Accent.TButton', background=self.accent_color, foreground="#FFFFFF", borderwidth=0, font=("Malgun Gothic", 10, "bold"))
        self.style.map('Accent.TButton', background=[('active', '#0052CC')])
        self.style.configure('TProgressbar', thickness=8, troughcolor=self.bg_color, background=self.accent_color, borderwidth=0)
        self.style.configure('Vertical.TScrollbar', arrowsize=0, width=8, relief='flat', borderwidth=0,
                             troughcolor=self.bg_color, background='#C5CAD2')
        self.style.map('Vertical.TScrollbar', background=[('active', '#6B7684'), ('pressed', '#4B5563')])
        
        # Determine paths relative to EXE or Python script
        self.base_dir = self.get_base_path()
        self.payload_dir = os.path.join(self.base_dir, "payload")
        
        self.setup_ui()
        self.load_package_info()
        
    def get_base_path(self):
        """
        Returns directory of the running EXE (if compiled by PyInstaller) or script.
        """
        if getattr(sys, 'frozen', False):
            # Running as compiled EXE
            return os.path.dirname(sys.executable)
        # Running as python script
        return os.path.dirname(os.path.abspath(__file__))
        
    def setup_ui(self):
        # 1. Header Section
        header_frame = tk.Frame(self.root, bg=self.bg_color, pady=15)
        header_frame.pack(fill=tk.X, padx=25)
        
        title_label = tk.Label(
            header_frame, 
            text="uv 오프라인 간편 설치기", 
            font=("Malgun Gothic", 20, "bold"), 
            bg=self.bg_color, 
            fg=self.fg_color
        )
        title_label.pack(anchor=tk.W)
        
        subtitle_label = tk.Label(
            header_frame, 
            text="인터넷이 없는 PC에 uv 및 파이썬 인터프리터, 라이브러리를 안전하게 자동 설치합니다.", 
            font=("Malgun Gothic", 10), 
            bg=self.bg_color, 
            fg=self.fg_muted
        )
        subtitle_label.pack(anchor=tk.W, pady=3)
        
        # 2. Mode Select Tab (Custom Segments)
        tab_frame = tk.Frame(self.root, bg=self.bg_color)
        tab_frame.pack(fill=tk.X, padx=25, pady=(5, 10))
        
        self.installer_mode_var = tk.StringVar(value="offline") # default 'offline'
        
        self.tab_offline_btn = tk.Button(
            tab_frame, text="🔒 폐쇄망 모드 (오프라인 설치)", command=lambda: self.switch_tab("offline"),
            font=("Malgun Gothic", 10, "bold"), relief="flat", bd=0, cursor="hand2", padx=20, pady=8,
            bg=self.accent_color, fg="#FFFFFF"
        )
        self.tab_offline_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        
        self.tab_online_btn = tk.Button(
            tab_frame, text="🌐 인터넷망 모드 (다운로드/내보내기)", command=lambda: self.switch_tab("online"),
            font=("Malgun Gothic", 10, "bold"), relief="flat", bd=0, cursor="hand2", padx=20, pady=8,
            bg="#E5E8EB", fg=self.fg_muted
        )
        self.tab_online_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        
        # Scrollable Canvas 영역 (Canvas + Scrollbar)
        scroll_container = tk.Frame(self.root, bg=self.bg_color)
        scroll_container.pack(fill=tk.BOTH, expand=True, padx=(25, 0), pady=(0, 10))

        self.main_canvas = tk.Canvas(scroll_container, bg=self.bg_color, highlightthickness=0)
        main_scrollbar = ttk.Scrollbar(scroll_container, orient="vertical", command=self.main_canvas.yview)

        # 캐닠바스 내부 담는 탈 컨테이너
        canvas_inner = tk.Frame(self.main_canvas, bg=self.bg_color)
        canvas_inner.bind(
            "<Configure>",
            lambda e: self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))
        )
        self.canvas_window = self.main_canvas.create_window((0, 0), window=canvas_inner, anchor="nw")

        # 캐닠바스 너비 동적 업데이트 (resize 시 내부 프레임이 함께 늘어나도록)
        def on_canvas_resize(e):
            self.main_canvas.itemconfig(self.canvas_window, width=e.width)
        self.main_canvas.bind("<Configure>", on_canvas_resize)

        self.main_canvas.configure(yscrollcommand=main_scrollbar.set)
        self.main_canvas.pack(side="left", fill="both", expand=True)
        main_scrollbar.pack(side="right", fill="y")

        # 마우스 휠 스크롤 바인딩
        def _on_mousewheel(event):
            self.main_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.main_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # Create Offline and Online frames inside the canvas inner frame
        self.offline_mode_frame = tk.Frame(canvas_inner, bg=self.bg_color)
        self.online_mode_frame = tk.Frame(canvas_inner, bg=self.bg_color)
        
        # --- A. Offline Mode UI Components ---
        # 1. Package Info Card (Modern Border with High Contrast Card Layout)
        info_card = tk.Frame(
            self.offline_mode_frame, bg=self.card_color, 
            highlightthickness=1, highlightbackground="#E5E8EB", bd=0
        )
        info_card.pack(fill=tk.X, pady=10, padx=5)
        
        info_card_inner = tk.Frame(info_card, bg=self.card_color)
        info_card_inner.pack(fill=tk.X, padx=20, pady=20)
        
        info_title = tk.Label(
            info_card_inner, text="동봉된 설치 패키지 정보", 
            font=("Malgun Gothic", 10, "bold"), bg=self.card_color, fg=self.fg_color
        )
        info_title.pack(anchor=tk.W, pady=(0, 10))
        
        details_frame = tk.Frame(info_card_inner, bg=self.card_color)
        details_frame.pack(fill=tk.X)
        
        # Labels for mapping values
        tk.Label(details_frame, text="uv 설치 파일:", font=("Malgun Gothic", 9, "bold"), bg=self.card_color, fg=self.fg_muted).grid(row=0, column=0, sticky=tk.W, pady=4)
        self.uv_val = tk.Label(details_frame, text="확인 중...", font=("Segoe UI", 9), bg=self.card_color, fg=self.fg_color)
        self.uv_val.grid(row=0, column=1, sticky=tk.W, padx=15, pady=4)
        
        tk.Label(details_frame, text="Python 버전:", font=("Malgun Gothic", 9, "bold"), bg=self.card_color, fg=self.fg_muted).grid(row=1, column=0, sticky=tk.W, pady=4)
        self.py_val = tk.Label(details_frame, text="확인 중...", font=("Segoe UI", 9), bg=self.card_color, fg=self.fg_color)
        self.py_val.grid(row=1, column=1, sticky=tk.W, padx=15, pady=4)
        
        tk.Label(details_frame, text="포함된 라이브러리:", font=("Malgun Gothic", 9, "bold"), bg=self.card_color, fg=self.fg_muted).grid(row=2, column=0, sticky=tk.W, pady=4)
        self.pkg_val = tk.Label(details_frame, text="확인 중...", font=("Segoe UI", 9), bg=self.card_color, fg=self.fg_color, wraplength=400, justify=tk.LEFT)
        self.pkg_val.grid(row=2, column=1, sticky=tk.W, padx=15, pady=4)
        
        # 2. Installation Settings Card
        settings_card = tk.Frame(
            self.offline_mode_frame, bg=self.card_color, 
            highlightthickness=1, highlightbackground="#E5E8EB", bd=0
        )
        settings_card.pack(fill=tk.X, pady=10, padx=5)
        
        settings_card_inner = tk.Frame(settings_card, bg=self.card_color)
        settings_card_inner.pack(fill=tk.X, padx=20, pady=20)
        
        settings_title = tk.Label(
            settings_card_inner, text="오프라인 설치 설정", 
            font=("Malgun Gothic", 10, "bold"), bg=self.card_color, fg=self.fg_color
        )
        settings_title.pack(anchor=tk.W, pady=(0, 12))
        
        # 패키지/자동팩 경로 (Source Folder)
        src_path_label = tk.Label(
            settings_card_inner, text="패키지/자동팩 경로 (Source Folder)", 
            font=("Malgun Gothic", 9, "bold"), bg=self.card_color, fg=self.fg_color
        )
        src_path_label.pack(anchor=tk.W)
        
        src_path_input_frame = tk.Frame(settings_card_inner, bg=self.card_color)
        src_path_input_frame.pack(fill=tk.X, pady=(5, 12))
        
        self.package_path_entry = tk.Entry(
            src_path_input_frame, bg="#E5E8EB", fg=self.fg_color, insertbackground=self.fg_color, 
            bd=0, relief="flat", font=("Segoe UI", 10),
            highlightthickness=1, highlightbackground="#E5E8EB", highlightcolor=self.accent_color
        )
        self.package_path_entry.insert(0, self.payload_dir)
        self.package_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10), ipady=4)
        self.package_path_entry.bind("<KeyRelease>", lambda e: self.load_package_info())
        
        src_browse_btn = tk.Button(
            src_path_input_frame, text="변경...", command=self.browse_package_dir,
            font=("Malgun Gothic", 9, "bold"), relief="flat", bd=0, bg="#E5E8EB", fg=self.fg_color,
            cursor="hand2", padx=12, pady=4
        )
        src_browse_btn.pack(side=tk.RIGHT)
        
        # 설치 경로 (Destination Folder)
        path_label = tk.Label(
            settings_card_inner, text="설치 경로 (Destination Folder)", 
            font=("Malgun Gothic", 9, "bold"), bg=self.card_color, fg=self.fg_color
        )
        path_label.pack(anchor=tk.W)
        
        path_input_frame = tk.Frame(settings_card_inner, bg=self.card_color)
        path_input_frame.pack(fill=tk.X, pady=5)
        
        self.install_path_entry = tk.Entry(
            path_input_frame, bg="#E5E8EB", fg=self.fg_color, insertbackground=self.fg_color, 
            bd=0, relief="flat", font=("Segoe UI", 10),
            highlightthickness=1, highlightbackground="#E5E8EB", highlightcolor=self.accent_color
        )
        # Default target directory identical to online ps1 installer
        default_install_dir = os.path.join(os.environ["USERPROFILE"], ".local", "bin")
        self.install_path_entry.insert(0, default_install_dir)
        self.install_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10), ipady=4)
        
        browse_btn = tk.Button(
            path_input_frame, text="변경...", command=self.browse_install_dir,
            font=("Malgun Gothic", 9, "bold"), relief="flat", bd=0, bg="#E5E8EB", fg=self.fg_color,
            cursor="hand2", padx=12, pady=4
        )
        browse_btn.pack(side=tk.RIGHT)
        
        path_help = tk.Label(
            settings_card_inner, 
            text="💡 권장: 관리자 권한이 없어도 사용 가능한 사용자 기본 경로 (.local\\bin)를 유지하십시오.", 
            font=("Malgun Gothic", 8), bg=self.card_color, fg=self.fg_muted
        )
        path_help.pack(anchor=tk.W, pady=(4, 8))
        
        self.global_env_var = tk.BooleanVar(value=True)
        self.global_env_cb = tk.Checkbutton(
            settings_card_inner, text="오프라인 설정을 사용자 전역 환경 변수로 등록 (권장: 폐쇄망 전용 PC)",
            variable=self.global_env_var, bg=self.card_color, fg=self.fg_color,
            selectcolor=self.card_color, activebackground=self.card_color, activeforeground=self.fg_color,
            font=("Malgun Gothic", 9)
        )
        self.global_env_cb.pack(anchor=tk.W, pady=(5, 5))
        
        # 3. Action Buttons Area
        all_btn_container = tk.Frame(self.offline_mode_frame, bg=self.bg_color)
        all_btn_container.pack(fill=tk.X, pady=(12, 8), padx=5)

        self.install_btn = tk.Button(
            all_btn_container, text="오프라인 설치 (Python Install)",
            command=self.start_install, font=("Malgun Gothic", 10, "bold"),
            bg=self.accent_color, fg="#FFFFFF", activebackground="#0052CC", activeforeground="#FFFFFF",
            relief="flat", bd=0, cursor="hand2", pady=12
        )
        self.install_btn.pack(fill=tk.X)
        
        # 4. Offline Progress & Console Output Card
        self.offline_progress_card = tk.Frame(
            self.offline_mode_frame, bg=self.card_color, 
            highlightthickness=1, highlightbackground="#E5E8EB", bd=0
        )
        self.offline_progress_card.pack(fill=tk.X, pady=10, padx=5)
        self.offline_progress_card.pack_forget() # Hide initially
        
        off_progress_card_inner = tk.Frame(self.offline_progress_card, bg=self.card_color)
        off_progress_card_inner.pack(fill=tk.X, padx=20, pady=20)
        
        self.offline_status_label = tk.Label(off_progress_card_inner, text="설치 준비 중...", font=("Malgun Gothic", 9, "bold"), bg=self.card_color, fg=self.fg_color)
        self.offline_status_label.pack(anchor=tk.W, pady=(0, 8))
        
        self.offline_progress_bar = ttk.Progressbar(off_progress_card_inner, orient="horizontal", mode="determinate")
        self.offline_progress_bar.pack(fill=tk.X, pady=(0, 12))
        
        offline_log_frame = tk.Frame(off_progress_card_inner, bg=self.console_bg,
                                     highlightthickness=1, highlightbackground="#E5E8EB")
        offline_log_frame.pack(fill=tk.X)
        offline_log_scroll = ttk.Scrollbar(offline_log_frame, orient="vertical")
        self.offline_log_text = tk.Text(
            offline_log_frame, height=12, bg=self.console_bg, fg="#F3F4F6",
            font=("Consolas", 9), relief="flat", state=tk.DISABLED,
            highlightthickness=0, yscrollcommand=offline_log_scroll.set
        )
        offline_log_scroll.config(command=self.offline_log_text.yview)
        self.offline_log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        offline_log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # --- B. Online Mode UI Components ---
        # 1. SSL Bypass Options Card
        ssl_bypass_card = tk.Frame(
            self.online_mode_frame, bg=self.card_color,
            highlightthickness=1, highlightbackground="#E5E8EB", bd=0
        )
        ssl_bypass_card.pack(fill=tk.X, pady=10, padx=5)
        
        ssl_bypass_card_inner = tk.Frame(ssl_bypass_card, bg=self.card_color)
        ssl_bypass_card_inner.pack(fill=tk.X, padx=20, pady=20)
        
        ssl_title = tk.Label(
            ssl_bypass_card_inner, text="보안망/SSL 우회 옵션 (인터넷망 다운로드용)", 
            font=("Malgun Gothic", 10, "bold"), bg=self.card_color, fg=self.fg_color
        )
        ssl_title.pack(anchor=tk.W, pady=(0, 10))
        
        ssl_help = tk.Label(
            ssl_bypass_card_inner,
            text="SSL 프록시/DPI 감시 장비로 인해 파일 다운로드 실패 시 아래 옵션을 적용하십시오.",
            font=("Malgun Gothic", 8), bg=self.card_color, fg=self.fg_muted
        )
        ssl_help.pack(anchor=tk.W, pady=(0, 8))
        
        self.ssl_bypass_var = tk.StringVar(value="standard")
        ssl_btn_frame = tk.Frame(ssl_bypass_card_inner, bg=self.card_color)
        ssl_btn_frame.pack(anchor=tk.W, pady=(0, 5))
        
        self.ssl_std_rb = tk.Radiobutton(
            ssl_btn_frame, text="사용 안 함 (Standard)", variable=self.ssl_bypass_var, value="standard",
            bg=self.card_color, fg=self.fg_color, activebackground=self.card_color, activeforeground=self.fg_color,
            font=("Malgun Gothic", 9), selectcolor=self.card_color
        )
        self.ssl_std_rb.pack(side=tk.LEFT, padx=(0, 15))
        
        self.ssl_certs_rb = tk.Radiobutton(
            ssl_btn_frame, text="OS 신뢰 저장소 사용 (--system-certs)", variable=self.ssl_bypass_var, value="system_certs",
            bg=self.card_color, fg=self.fg_color, activebackground=self.card_color, activeforeground=self.fg_color,
            font=("Malgun Gothic", 9), selectcolor=self.card_color
        )
        self.ssl_certs_rb.pack(side=tk.LEFT, padx=(0, 15))
        
        self.ssl_hosts_rb = tk.Radiobutton(
            ssl_btn_frame, text="도메인 신뢰 강제 (--trusted-host)", variable=self.ssl_bypass_var, value="trusted_host",
            bg=self.card_color, fg=self.fg_color, activebackground=self.card_color, activeforeground=self.fg_color,
            font=("Malgun Gothic", 9), selectcolor=self.card_color
        )
        self.ssl_hosts_rb.pack(side=tk.LEFT)
        
        # 2. Package Downloader and Exporter Card
        bypass_card = tk.Frame(
            self.online_mode_frame, bg=self.card_color,
            highlightthickness=1, highlightbackground="#E5E8EB", bd=0
        )
        bypass_card.pack(fill=tk.X, pady=10, padx=5)
        
        bypass_card_inner = tk.Frame(bypass_card, bg=self.card_color)
        bypass_card_inner.pack(fill=tk.X, padx=20, pady=20)
        
        bypass_title = tk.Label(
            bypass_card_inner, text="📦 폐쇄망용 설치 팩 자동 생성 및 내보내기",
            font=("Malgun Gothic", 10, "bold"), bg=self.card_color, fg=self.fg_color
        )
        bypass_title.pack(anchor=tk.W, pady=(0, 5))
        
        bypass_help1 = tk.Label(
            bypass_card_inner,
            text="폐쇄망 PC에서 설치에 필요한 CPython Standalone 및 uv 바이너리를 다운로드하고,\n"
                 "인스톨러 소스코드 및 run_installer.bat과 함께 하나의 폴더로 구성하여 내보냅니다.\n"
                 "생성된 폴더 전체를 폐쇄망 PC로 이동한 후 run_installer.bat를 실행해 오프라인 설치가 가능합니다.",
            font=("Malgun Gothic", 8), bg=self.card_color, fg=self.fg_muted, justify=tk.LEFT
        )
        bypass_help1.pack(anchor=tk.W, pady=(0, 10))
        
        py_sel_frame = tk.Frame(bypass_card_inner, bg=self.card_color)
        py_sel_frame.pack(fill=tk.X, pady=4)
        
        py_sel_label = tk.Label(py_sel_frame, text="내보낼 Python 버전:", font=("Malgun Gothic", 9, "bold"), bg=self.card_color, fg=self.fg_color)
        py_sel_label.pack(side=tk.LEFT, padx=(0, 10))
        
        self.bypass_py_var = tk.StringVar(value="3.12")
        self.bypass_py_combo = ttk.Combobox(py_sel_frame, textvariable=self.bypass_py_var, values=["3.9", "3.10", "3.11", "3.12", "3.13"], width=8, state="readonly")
        self.bypass_py_combo.pack(side=tk.LEFT)
        
        # Export target directory
        exp_frame = tk.Frame(bypass_card_inner, bg=self.card_color)
        exp_frame.pack(fill=tk.X, pady=8)
        
        exp_label = tk.Label(exp_frame, text="내보낼 폴더 경로 (Export Directory):", font=("Malgun Gothic", 9, "bold"), bg=self.card_color, fg=self.fg_color)
        exp_label.pack(anchor=tk.W, pady=(0, 4))
        
        exp_input_frame = tk.Frame(exp_frame, bg=self.card_color)
        exp_input_frame.pack(fill=tk.X)
        
        self.bypass_export_entry = tk.Entry(
            exp_input_frame, bg="#E5E8EB", fg=self.fg_color, insertbackground=self.fg_color,
            bd=0, relief="flat", font=("Segoe UI", 10),
            highlightthickness=1, highlightbackground="#E5E8EB", highlightcolor=self.accent_color
        )
        default_export_dir = os.path.join(os.getcwd(), "uvtool-bypass-pack")
        self.bypass_export_entry.insert(0, default_export_dir)
        self.bypass_export_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10), ipady=4)
        
        exp_browse_btn = tk.Button(
            exp_input_frame, text="찾아보기...", command=self.browse_bypass_export_dir,
            font=("Malgun Gothic", 9, "bold"), relief="flat", bd=0, bg="#E5E8EB", fg=self.fg_color,
            cursor="hand2", padx=12, pady=4
        )
        exp_browse_btn.pack(side=tk.RIGHT)
        
        # Export Action Button
        self.export_btn = tk.Button(
            bypass_card_inner, text="설치 팩 다운로드 및 내보내기 (Export)",
            command=self.start_bypass_export, font=("Malgun Gothic", 10, "bold"),
            bg=self.accent_color, fg="#FFFFFF", activebackground="#0052CC", activeforeground="#FFFFFF",
            relief="flat", bd=0, cursor="hand2", pady=10
        )
        self.export_btn.pack(fill=tk.X, pady=(10, 0))
        
        # 3. Online Progress & Console Output Card
        self.online_progress_card = tk.Frame(
            self.online_mode_frame, bg=self.card_color, 
            highlightthickness=1, highlightbackground="#E5E8EB", bd=0
        )
        self.online_progress_card.pack(fill=tk.X, pady=10, padx=5)
        self.online_progress_card.pack_forget() # Hide initially
        
        on_progress_card_inner = tk.Frame(self.online_progress_card, bg=self.card_color)
        on_progress_card_inner.pack(fill=tk.X, padx=20, pady=20)
        
        self.online_status_label = tk.Label(on_progress_card_inner, text="내보내기 준비 중...", font=("Malgun Gothic", 9, "bold"), bg=self.card_color, fg=self.fg_color)
        self.online_status_label.pack(anchor=tk.W, pady=(0, 8))
        
        self.online_progress_bar = ttk.Progressbar(on_progress_card_inner, orient="horizontal", mode="determinate")
        self.online_progress_bar.pack(fill=tk.X, pady=(0, 12))
        
        online_log_frame = tk.Frame(on_progress_card_inner, bg=self.console_bg,
                                    highlightthickness=1, highlightbackground="#E5E8EB")
        online_log_frame.pack(fill=tk.X)
        online_log_scroll = ttk.Scrollbar(online_log_frame, orient="vertical")
        self.online_log_text = tk.Text(
            online_log_frame, height=12, bg=self.console_bg, fg="#F3F4F6",
            font=("Consolas", 9), relief="flat", state=tk.DISABLED,
            highlightthickness=0, yscrollcommand=online_log_scroll.set
        )
        online_log_scroll.config(command=self.online_log_text.yview)
        self.online_log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        online_log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Set Initial Active Tab
        self.switch_tab("offline")
        
    def load_package_info(self):
        """
        Scans package source folder and displays metadata in details frame.
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
                    self.uv_val.configure(text="기존 설치된 uv 사용", fg=self.success_color)
                    self.install_btn.configure(state=tk.NORMAL)
                else:
                    self.uv_val.configure(text="없음 (기존 설치본 필요)", fg=self.fg_muted)
                    self.install_btn.configure(state=tk.NORMAL)
            else:
                uv_name = os.path.basename(info["uv_archive"])
                self.uv_val.configure(text=uv_name, fg=self.fg_color)
                self.install_btn.configure(state=tk.NORMAL)
            
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
                self.py_val.configure(text="없음 (uv 단독 설치)", fg=self.fg_muted)
                
            wheel_names = [os.path.basename(w).split('-')[0] for w in info["wheels"]]
            # deduplicate
            wheel_names = sorted(list(set(wheel_names)))
            if wheel_names:
                self.pkg_val.configure(text=f"{len(info['wheels'])}개 라이브러리 포함 ({', '.join(wheel_names[:8])}...)" if len(wheel_names) > 8 else f"{len(info['wheels'])}개 라이브러리 ({', '.join(wheel_names)})")
            else:
                self.pkg_val.configure(text="없음 (라이브러리 미포함)", fg=self.fg_muted)
                
        except Exception as e:
            messagebox.showerror("스캔 에러", f"설치팩 정보 스캔 중 실패: {e}")
            
    def switch_tab(self, value):
        self.installer_mode_var.set(value)
        if value == "offline":
            self.tab_offline_btn.configure(bg=self.accent_color, fg="#FFFFFF")
            self.tab_online_btn.configure(bg="#E5E8EB", fg=self.fg_muted)
            self.online_mode_frame.pack_forget()
            self.offline_mode_frame.pack(fill=tk.X, padx=5, pady=5)
        else:
            self.tab_offline_btn.configure(bg="#E5E8EB", fg=self.fg_muted)
            self.tab_online_btn.configure(bg=self.accent_color, fg="#FFFFFF")
            self.offline_mode_frame.pack_forget()
            self.online_mode_frame.pack(fill=tk.X, padx=5, pady=5)
        # 탭 전환 시 스크롤을 맨 위로 리셋
        self.main_canvas.yview_moveto(0)

    def browse_install_dir(self):
        path = filedialog.askdirectory(initialdir=self.install_path_entry.get())
        if path:
            self.install_path_entry.delete(0, tk.END)
            self.install_path_entry.insert(0, os.path.normpath(path))
            self.load_package_info()
            
    def browse_package_dir(self):
        path = filedialog.askdirectory(initialdir=self.package_path_entry.get())
        if path:
            self.package_path_entry.delete(0, tk.END)
            self.package_path_entry.insert(0, os.path.normpath(path))
            self.load_package_info()
            
    def append_log(self, text):
        mode = self.installer_mode_var.get()
        log_widget = self.offline_log_text if mode == "offline" else self.online_log_text
        
        log_widget.configure(state=tk.NORMAL)
        log_widget.insert(tk.END, text + "\n")
        log_widget.see(tk.END)
        log_widget.configure(state=tk.DISABLED)
        
    def update_progress(self, percent):
        mode = self.installer_mode_var.get()
        bar_widget = self.offline_progress_bar if mode == "offline" else self.online_progress_bar
        bar_widget["value"] = percent
        
    def update_status_text(self, text):
        mode = self.installer_mode_var.get()
        label_widget = self.offline_status_label if mode == "offline" else self.online_status_label
        label_widget.configure(text=text)
        
    def start_install(self):
        install_dir = self.install_path_entry.get().strip()
        if not install_dir:
            messagebox.showerror("입력 오류", "올바른 설치 경로를 지정하십시오.")
            return

        offline_mode = (self.installer_mode_var.get() == "offline")

        scan_dir = self.package_path_entry.get().strip() if hasattr(self, 'package_path_entry') else self.payload_dir
        if not scan_dir:
            scan_dir = self.payload_dir

        info = get_bundled_info(scan_dir)
        existing_uv = os.path.exists(os.path.join(install_dir, "uv.exe"))

        if offline_mode and not info["uv_archive"] and not existing_uv:
            messagebox.showerror("설치 오류", "설치 아카이브 파일이 없으며 기존에 설치된 uv.exe도 감지되지 않았습니다. 폐쇄망 모드가 활성화되어 외부 다운로드를 실행할 수 없습니다.")
            return

        self.offline_progress_card.pack(fill=tk.BOTH, expand=True, pady=5, padx=5)
        self.install_btn.configure(state=tk.DISABLED)
        self.offline_progress_bar["value"] = 0
        self.offline_log_text.configure(state=tk.NORMAL)
        self.offline_log_text.delete("1.0", tk.END)
        self.offline_log_text.configure(state=tk.DISABLED)

        def thread_safe_log(msg):
            self.root.after(0, lambda: self.append_log(msg))

        def thread_safe_progress(pct):
            self.root.after(0, lambda: self.update_progress(pct))

        def thread_safe_status(txt):
            self.root.after(0, lambda: self.update_status_text(txt))

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
                        self.root.destroy()

                    self.root.after(0, complete_and_exit)
            except Exception as e:
                thread_safe_status("설치 중 에러 발생")
                thread_safe_log(f"[ERROR] 설치 실패: {e}")
                self.root.after(0, lambda: messagebox.showerror("설치 실패", f"설치 중 문제가 발생하였습니다:\n{e}"))
            finally:
                self.root.after(0, lambda: self.install_btn.configure(state=tk.NORMAL))

        threading.Thread(target=run, daemon=True).start()

    def browse_bypass_export_dir(self):
        path = filedialog.askdirectory(initialdir=self.bypass_export_entry.get())
        if path:
            self.bypass_export_entry.delete(0, tk.END)
            self.bypass_export_entry.insert(0, os.path.normpath(path))
            
    def start_bypass_export(self):
        export_dir = self.bypass_export_entry.get().strip()
        py_ver = self.bypass_py_var.get()
        if not export_dir:
            messagebox.showerror("입력 오류", "내보낼 폴더 경로를 지정하십시오.")
            return
            
        self.online_progress_card.pack(fill=tk.X, pady=10)
        self.export_btn.configure(state=tk.DISABLED)
        self.online_progress_bar["value"] = 0
        self.online_log_text.configure(state=tk.NORMAL)
        self.online_log_text.delete("1.0", tk.END)
        self.online_log_text.configure(state=tk.DISABLED)
        
        def thread_safe_log(msg):
            self.root.after(0, lambda: self.append_log(msg))
        def thread_safe_progress(pct):
            self.root.after(0, lambda: self.update_progress(pct))
        def thread_safe_status(txt):
            self.root.after(0, lambda: self.update_status_text(txt))
            
        ssl_bypass = self.ssl_bypass_var.get()
        
        def run_export():
            try:
                thread_safe_status("우회 설치 팩 내보내는 중...")
                thread_safe_log(f"[START] 우회 패키징 준비 시작 (대상 경로: {export_dir}, SSL 모드: {ssl_bypass})")
                
                os.makedirs(export_dir, exist_ok=True)
                
                # 1. Download CPython Standalone Windows
                thread_safe_progress(0)
                thread_safe_log("[DOWNLOAD] 1. CPython Standalone 런타임 정보 조회 중...")
                plat = get_platform_info("windows", "x86_64") # Windows x86_64
                pbp_url, pbp_archive_name = get_python_asset_url(py_ver, plat, thread_safe_log)
                py_dest_path = os.path.join(export_dir, pbp_archive_name)
                
                thread_safe_log(f"[DOWNLOAD] CPython Standalone 다운로드 시작: {pbp_archive_name}")
                
                # Python standalone download occupies 0% to 60% of total export progress
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
                
                # uv download occupies 60% to 90% of total export progress
                def uv_progress(pct):
                    thread_safe_progress(60 + int(pct * 0.3))
                    
                download_file(uv_url, uv_dest_path, progress_callback=uv_progress, status_callback=thread_safe_log, ssl_bypass=ssl_bypass)
                thread_safe_log(f"[SUCCESS] uv 바이너리 다운로드 완료: {uv_dest_path}")
                
                # 3. 인스톨러 실행 파일/소스 내보내기
                import shutil
                thread_safe_progress(70)

                is_frozen = getattr(sys, 'frozen', False)

                if is_frozen:
                    # ─── EXE 모드: installer_gui.exe 자신을 복사 ───
                    thread_safe_log("[EXPORT] 3. 컴파일된 installer_gui.exe 내보내는 중...")
                    exe_src = sys.executable  # installer_gui.exe 경로
                    exe_dest = os.path.join(export_dir, "installer_gui.exe")
                    shutil.copy2(exe_src, exe_dest)
                    thread_safe_log(f"[SUCCESS] installer_gui.exe 내보내기 완료: {exe_dest}")

                    # install_offline.ps1 도 함께 복사 (exe 옆에 있으면)
                    ps1_src = os.path.join(os.path.dirname(exe_src), "install_offline.ps1")
                    if os.path.exists(ps1_src):
                        shutil.copy2(ps1_src, os.path.join(export_dir, "install_offline.ps1"))
                        thread_safe_log("[SUCCESS] install_offline.ps1 함께 내보내기 완료.")
                else:
                    # ─── 스크립트 모드: .py + src/ 복사 ───
                    thread_safe_log("[EXPORT] 3. 인스톨러 파이썬 소스 코드(.py) 내보내는 중...")
                    base_src_dir = os.path.dirname(os.path.abspath(__file__))

                    # src/ 폴더
                    src_folder_origin = os.path.join(base_src_dir, "src")
                    src_folder_dest = os.path.join(export_dir, "src")
                    if os.path.exists(src_folder_dest):
                        shutil.rmtree(src_folder_dest)
                    if os.path.exists(src_folder_origin):
                        shutil.copytree(src_folder_origin, src_folder_dest,
                                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

                    # installer_gui.py
                    installer_py_src = os.path.join(base_src_dir, "installer_gui.py")
                    if os.path.exists(installer_py_src):
                        shutil.copy2(installer_py_src, os.path.join(export_dir, "installer_gui.py"))

                    # install_offline.ps1
                    ps1_src = os.path.join(base_src_dir, "install_offline.ps1")
                    if os.path.exists(ps1_src):
                        shutil.copy2(ps1_src, os.path.join(export_dir, "install_offline.ps1"))

                    thread_safe_log("[SUCCESS] 소스 코드 내보내기 완료.")

                # 4. run_installer.bat / run_installer_exe.bat 생성
                thread_safe_progress(90)
                thread_safe_log("[GENERATE] 4. 원클릭 실행 배치 파일 생성 중...")

                if is_frozen:
                    # EXE 모드 전용 bat: Python 압축 해제 후 installer_gui.exe 바로 실행
                    bat_content = (
                        "@echo off\n"
                        "echo ==========================================================\n"
                        "echo           uvtool Offline Installer Launcher\n"
                        "echo ==========================================================\n"
                        "echo.\n"
                        "cd /d \"%~dp0\"\n\n"
                        "rem 1. Extract Python Standalone Runtime (for uv pip etc.)\n"
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
                    # 스크립트 모드 bat: Python 압축 해제 후 installer_gui.py 실행
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
                self.root.after(0, lambda: messagebox.showinfo(
                    "내보내기 완료",
                    f"보안 차단 우회용 인스톨러 구동 팩이 성공적으로 생성되었습니다!\n\n"
                    f"폴더 경로: {export_dir}\n"
                    f"동봉된 파이썬 버전: {py_ver}\n\n"
                    f"이 폴더 전체를 USB로 수동 이동한 뒤, 폐쇄망 PC에서 'run_installer.bat'을 실행하십시오."
                ))
                
            except Exception as e:
                thread_safe_status("내보내기 실패")
                thread_safe_log(f"[ERROR] 작업 실패: {e}")
                import traceback
                thread_safe_log(traceback.format_exc())
                self.root.after(0, lambda: messagebox.showerror("내보내기 실패", f"작업 중 오류가 발생하였습니다:\n{e}"))
            finally:
                self.root.after(0, lambda: self.export_btn.configure(state=tk.NORMAL))
                
        t_exp = threading.Thread(target=run_export, daemon=True)
        t_exp.start()

if __name__ == "__main__":
    if sys.platform == 'win32':
        import ctypes
        myappid = 'google.deepmind.uvtool.installer.1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        
    root = tk.Tk()
    app = InstallerApp(root)
    root.mainloop()
