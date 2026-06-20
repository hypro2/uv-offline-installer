import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from src.builder import build_package

class BuilderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("uvtool - 오프라인 패키지 빌더 (Builder)")
        self.root.geometry("750x700")
        self.root.minsize(680, 600)
        
        # UI Styling Colors (Toss White/Blue Minimal Style)
        self.bg_color = "#F2F4F6"      # Toss Light Background
        self.card_color = "#FFFFFF"    # Crisp White Cards
        self.fg_color = "#191F28"      # Toss Dark Grey Text
        self.fg_muted = "#6B7684"      # Toss Muted Gray Text
        self.accent_color = "#0064FF"    # Toss Vibrant Blue Accent
        self.error_color = "#F04452"     # Toss Red
        self.success_color = "#00D4B2"   # Toss Teal/Green
        self.console_bg = "#191F28"     # Toss Dark Grey console background
        
        # Configure Root Styles
        self.root.configure(bg=self.bg_color)
        
        # Create ttk style mapping
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
        
        self.setup_ui()
        
    def setup_ui(self):
        # 1. Header Frame
        header_frame = tk.Frame(self.root, bg=self.bg_color, pady=15)
        header_frame.pack(fill=tk.X, padx=25)
        
        title_label = tk.Label(
            header_frame, 
            text="uv 오프라인 패키지 빌더", 
            font=("Malgun Gothic", 20, "bold"), 
            bg=self.bg_color, 
            fg=self.fg_color
        )
        title_label.pack(anchor=tk.W)
        
        subtitle_label = tk.Label(
            header_frame, 
            text="인터넷 환경에서 uv, Python Standalone, PIP 패키지를 수집하여 오프라인 설치 팩을 빌드합니다.", 
            font=("Malgun Gothic", 10), 
            bg=self.bg_color, 
            fg=self.fg_muted
        )
        subtitle_label.pack(anchor=tk.W, pady=3)
        
        # Scrollable Main Canvas/Frame for contents
        main_canvas = tk.Canvas(self.root, bg=self.bg_color, highlightthickness=0)
        main_scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=main_canvas.yview)
        scrollable_frame = tk.Frame(main_canvas, bg=self.bg_color)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all"))
        )
        
        canvas_window_id = main_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        main_canvas.configure(yscrollcommand=main_scrollbar.set)

        def on_canvas_resize(e):
            main_canvas.itemconfig(canvas_window_id, width=e.width)
        main_canvas.bind("<Configure>", on_canvas_resize)

        def _on_mousewheel(event):
            main_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        main_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        main_canvas.pack(side="left", fill="both", expand=True, padx=(25, 0))
        main_scrollbar.pack(side="right", fill="y")
        
        # 2. Main Form Card (Modern Border with High Contrast Card Layout)
        form_card = tk.Frame(
            scrollable_frame, bg=self.card_color, 
            highlightthickness=1, highlightbackground="#E5E8EB", bd=0
        )
        form_card.pack(fill=tk.X, pady=10, padx=5)
        
        # Inner Padding Wrapper
        form_card_inner = tk.Frame(form_card, bg=self.card_color)
        form_card_inner.pack(fill=tk.X, padx=24, pady=24)
        
        # Target OS & Arch Selector (Segmented Flat Buttons)
        target_frame = tk.Frame(form_card_inner, bg=self.card_color)
        target_frame.pack(fill=tk.X, pady=5)
        
        os_label = tk.Label(target_frame, text="대상 운영체제 (Target OS)", font=("Malgun Gothic", 10, "bold"), bg=self.card_color, fg=self.fg_color)
        os_label.pack(anchor=tk.W, pady=(0, 5))
        
        os_btn_frame = tk.Frame(target_frame, bg=self.card_color)
        os_btn_frame.pack(anchor=tk.W, pady=5)
        
        self.target_os_var = tk.StringVar(value="windows")
        self.os_win_btn = tk.Button(
            os_btn_frame, text="Windows", command=lambda: self.toggle_os("windows"),
            font=("Malgun Gothic", 9, "bold"), relief="flat", bd=0, cursor="hand2", padx=18, pady=6,
            bg=self.accent_color, fg="#FFFFFF"
        )
        self.os_win_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        self.os_lin_btn = tk.Button(
            os_btn_frame, text="Linux", command=lambda: self.toggle_os("linux"),
            font=("Malgun Gothic", 9, "bold"), relief="flat", bd=0, cursor="hand2", padx=18, pady=6,
            bg="#E5E8EB", fg=self.fg_muted
        )
        self.os_lin_btn.pack(side=tk.LEFT)
        
        # Arch
        arch_label = tk.Label(target_frame, text="대상 아키텍처 (Arch)", font=("Malgun Gothic", 10, "bold"), bg=self.card_color, fg=self.fg_color)
        arch_label.pack(anchor=tk.W, pady=(12, 5))
        
        arch_btn_frame = tk.Frame(target_frame, bg=self.card_color)
        arch_btn_frame.pack(anchor=tk.W, pady=5)
        
        self.target_arch_var = tk.StringVar(value="x86_64")
        self.arch_64_btn = tk.Button(
            arch_btn_frame, text="x86_64 (Intel/AMD)", command=lambda: self.toggle_arch("x86_64"),
            font=("Malgun Gothic", 9, "bold"), relief="flat", bd=0, cursor="hand2", padx=18, pady=6,
            bg=self.accent_color, fg="#FFFFFF"
        )
        self.arch_64_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        self.arch_arm_btn = tk.Button(
            arch_btn_frame, text="aarch64 (ARM64)", command=lambda: self.toggle_arch("aarch64"),
            font=("Malgun Gothic", 9, "bold"), relief="flat", bd=0, cursor="hand2", padx=18, pady=6,
            bg="#E5E8EB", fg=self.fg_muted
        )
        self.arch_arm_btn.pack(side=tk.LEFT)
        
        # Divider line
        tk.Frame(form_card_inner, height=1, bg=self.bg_color).pack(fill=tk.X, pady=18)
        
        # Packaging Scope Selection (Toss Segmented Button UI)
        scope_frame = tk.Frame(form_card_inner, bg=self.card_color)
        scope_frame.pack(fill=tk.X, pady=5)
        
        scope_label = tk.Label(scope_frame, text="압축 패키지 범위 (Package Scope)", font=("Malgun Gothic", 10, "bold"), bg=self.card_color, fg=self.fg_color)
        scope_label.pack(anchor=tk.W, pady=(0, 5))
        
        scope_btn_frame = tk.Frame(scope_frame, bg=self.card_color)
        scope_btn_frame.pack(anchor=tk.W, pady=5)
        
        self.package_scope_var = tk.StringVar(value="all")
        self.scope_all_btn = tk.Button(
            scope_btn_frame, text="전체 패키지 압축 (Full)", command=lambda: self.toggle_scope("all"),
            font=("Malgun Gothic", 9, "bold"), relief="flat", bd=0, cursor="hand2", padx=18, pady=6,
            bg=self.accent_color, fg="#FFFFFF"
        )
        self.scope_all_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        self.scope_new_btn = tk.Button(
            scope_btn_frame, text="신규 패키지만 압축 (Incremental)", command=lambda: self.toggle_scope("new"),
            font=("Malgun Gothic", 9, "bold"), relief="flat", bd=0, cursor="hand2", padx=18, pady=6,
            bg="#E5E8EB", fg=self.fg_muted
        )
        self.scope_new_btn.pack(side=tk.LEFT)

        # 신규패키지 기준 초기화 버튼
        self.reset_registry_btn = tk.Button(
            scope_btn_frame, text="🔄 신규패키지 기준 초기화",
            command=self.reset_wheel_registry,
            font=("Malgun Gothic", 9, "bold"), relief="flat", bd=0, cursor="hand2", padx=14, pady=6,
            bg="#F04452", fg="#FFFFFF", activebackground="#C0392B", activeforeground="#FFFFFF"
        )
        self.reset_registry_btn.pack(side=tk.LEFT, padx=(16, 0))
        
        scope_help = tk.Label(scope_frame, text="증분 압축 시 uv 바이너리와 Python standalone은 제외되고 처음/변경 다운로드된 휠만 포함되어 압축 파일 용량이 아주 작아집니다.", font=("Malgun Gothic", 8), bg=self.card_color, fg=self.fg_muted)
        scope_help.pack(anchor=tk.W, pady=(2, 0))
        
        # Divider line
        tk.Frame(form_card_inner, height=1, bg=self.bg_color).pack(fill=tk.X, pady=18)
        
        # UV Version Input
        uv_frame = tk.Frame(form_card_inner, bg=self.card_color)
        uv_frame.pack(fill=tk.X, pady=5)
        uv_label = tk.Label(uv_frame, text="uv 버전 지정", font=("Malgun Gothic", 10, "bold"), bg=self.card_color, fg=self.fg_color)
        uv_label.pack(anchor=tk.W, pady=(0, 5))
        
        self.uv_version_entry = tk.Entry(
            uv_frame, bg="#E5E8EB", fg=self.fg_color, insertbackground=self.fg_color, 
            bd=0, relief="flat", font=("Segoe UI", 10),
            highlightthickness=1, highlightbackground="#E5E8EB", highlightcolor=self.accent_color
        )
        self.uv_version_entry.insert(0, "latest")
        self.uv_version_entry.pack(fill=tk.X, pady=5, ipady=4)
        uv_help = tk.Label(uv_frame, text="'latest' 또는 특정 버전(예: 0.11.16)을 입력하세요.", font=("Malgun Gothic", 8), bg=self.card_color, fg=self.fg_muted)
        uv_help.pack(anchor=tk.W)
        
        # Divider line
        tk.Frame(form_card_inner, height=1, bg=self.bg_color).pack(fill=tk.X, pady=18)
        
        # Python Versions Checkboxes (Toggle Buttons Tags)
        py_frame = tk.Frame(form_card_inner, bg=self.card_color)
        py_frame.pack(fill=tk.X, pady=5)
        py_label = tk.Label(py_frame, text="포함할 Python 버전 선택", font=("Malgun Gothic", 10, "bold"), bg=self.card_color, fg=self.fg_color)
        py_label.pack(anchor=tk.W, pady=(0, 5))
        
        self.py_versions = ["3.9", "3.10", "3.11", "3.12", "3.13"]
        self.py_vars = {}
        self.py_buttons = {}
        
        self.checkbox_frame = tk.Frame(py_frame, bg=self.card_color)
        self.checkbox_frame.pack(fill=tk.X, pady=5)
        
        for idx, ver in enumerate(self.py_versions):
            is_checked = (ver == "3.11")
            var = tk.BooleanVar(value=is_checked)
            self.py_vars[ver] = var
            
            btn = tk.Button(
                self.checkbox_frame, text=f"Python {ver}", 
                command=lambda v=ver: self.toggle_py_version(v),
                font=("Malgun Gothic", 9, "bold"), relief="flat", bd=0, cursor="hand2", padx=15, pady=6
            )
            btn.grid(row=0, column=idx, padx=4, pady=5)
            self.py_buttons[ver] = btn
            
            if is_checked:
                btn.configure(bg=self.accent_color, fg="#FFFFFF")
            else:
                btn.configure(bg="#E5E8EB", fg=self.fg_muted)
            
        # Custom python version input
        custom_py_frame = tk.Frame(py_frame, bg=self.card_color)
        custom_py_frame.pack(fill=tk.X, pady=8)
        custom_label = tk.Label(custom_py_frame, text="기타 버전 직접 입력:", font=("Malgun Gothic", 9), bg=self.card_color, fg=self.fg_muted)
        custom_label.pack(side=tk.LEFT, padx=(0, 8))
        self.custom_py_entry = tk.Entry(
            custom_py_frame, bg="#E5E8EB", fg=self.fg_color, insertbackground=self.fg_color, 
            bd=0, relief="flat", width=15,
            highlightthickness=1, highlightbackground="#E5E8EB", highlightcolor=self.accent_color
        )
        self.custom_py_entry.pack(side=tk.LEFT, padx=5, ipady=2)
        
        custom_add_btn = tk.Button(
            custom_py_frame, text="추가", command=self.add_custom_python, 
            font=("Malgun Gothic", 9, "bold"), relief="flat", bd=0, bg="#E5E8EB", fg=self.fg_color,
            cursor="hand2", padx=12, pady=2
        )
        custom_add_btn.pack(side=tk.LEFT, padx=5)
        
        # Divider line
        tk.Frame(form_card_inner, height=1, bg=self.bg_color).pack(fill=tk.X, pady=18)
        
        # PIP Packages Text Area
        pip_frame = tk.Frame(form_card_inner, bg=self.card_color)
        pip_frame.pack(fill=tk.X, pady=5)
        pip_label = tk.Label(pip_frame, text="포함할 PIP 라이브러리 목록 (requirements.txt 형식)", font=("Malgun Gothic", 10, "bold"), bg=self.card_color, fg=self.fg_color)
        pip_label.pack(anchor=tk.W, pady=(0, 5))
        
        pip_text_frame = tk.Frame(pip_frame, bg="#E5E8EB",
                                  highlightthickness=1, highlightbackground="#E5E8EB")
        pip_text_frame.pack(fill=tk.X, pady=5)
        pip_scroll = ttk.Scrollbar(pip_text_frame, orient="vertical")
        self.pip_packages_text = tk.Text(
            pip_text_frame, height=5, bg="#E5E8EB", fg=self.fg_color, insertbackground=self.fg_color,
            bd=0, relief="flat", font=("Consolas", 10), wrap=tk.WORD,
            highlightthickness=0, yscrollcommand=pip_scroll.set
        )
        pip_scroll.config(command=self.pip_packages_text.yview)
        self.pip_packages_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        pip_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.pip_packages_text.insert(tk.END, "# 예: numpy\n# pandas>=2.0.0\n# requests")
        
        # Divider line
        tk.Frame(form_card_inner, height=1, bg=self.bg_color).pack(fill=tk.X, pady=18)
        
        # Network/SSL Bypass Option (Radiobuttons)
        ssl_frame = tk.Frame(form_card_inner, bg=self.card_color)
        ssl_frame.pack(fill=tk.X, pady=5)
        ssl_label = tk.Label(ssl_frame, text="보안망/SSL 우회 옵션 지정", font=("Malgun Gothic", 10, "bold"), bg=self.card_color, fg=self.fg_color)
        ssl_label.pack(anchor=tk.W, pady=(0, 5))
        
        self.ssl_bypass_var = tk.StringVar(value="standard")
        
        ssl_btn_frame = tk.Frame(ssl_frame, bg=self.card_color)
        ssl_btn_frame.pack(anchor=tk.W, pady=5)
        
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
        
        ssl_help = tk.Label(ssl_frame, text="DPI 프록시나 보안망의 SSL 인증서 차단으로 인해 다운로드 실패 시 유용합니다.", font=("Malgun Gothic", 8), bg=self.card_color, fg=self.fg_muted)
        ssl_help.pack(anchor=tk.W, pady=(2, 0))
        
        # Divider line
        tk.Frame(form_card_inner, height=1, bg=self.bg_color).pack(fill=tk.X, pady=18)
        
        # Output Zip Path
        out_frame = tk.Frame(form_card_inner, bg=self.card_color)
        out_frame.pack(fill=tk.X, pady=5)
        out_label = tk.Label(out_frame, text="저장할 패키지 압축파일 경로 (Output ZIP)", font=("Malgun Gothic", 10, "bold"), bg=self.card_color, fg=self.fg_color)
        out_label.pack(anchor=tk.W, pady=(0, 5))
        
        path_input_frame = tk.Frame(out_frame, bg=self.card_color)
        path_input_frame.pack(fill=tk.X, pady=5)
        
        self.output_path_entry = tk.Entry(
            path_input_frame, bg="#E5E8EB", fg=self.fg_color, insertbackground=self.fg_color, 
            bd=0, relief="flat", font=("Segoe UI", 10),
            highlightthickness=1, highlightbackground="#E5E8EB", highlightcolor=self.accent_color
        )
        default_out = os.path.join(os.getcwd(), "uv-offline-package.zip")
        self.output_path_entry.insert(0, default_out)
        self.output_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10), ipady=4)
        
        browse_btn = tk.Button(
            path_input_frame, text="찾아보기...", command=self.browse_output,
            font=("Malgun Gothic", 9, "bold"), relief="flat", bd=0, bg="#E5E8EB", fg=self.fg_color,
            cursor="hand2", padx=12, pady=4
        )
        browse_btn.pack(side=tk.RIGHT)
        
        # 3. Action Section (Large Flat Toss Blue Button)
        self.build_btn = tk.Button(
            scrollable_frame, text="오프라인 설치 팩 생성 (Build)", 
            command=self.start_build, font=("Malgun Gothic", 12, "bold"), 
            bg=self.accent_color, fg="#FFFFFF", activebackground="#0052CC", activeforeground="#FFFFFF",
            relief="flat", bd=0, cursor="hand2", pady=14
        )
        self.build_btn.pack(fill=tk.X, pady=20, padx=5)
        
        # 4. Progress and Log Card (Modern Border with High Contrast Card Layout)
        self.progress_card = tk.Frame(
            scrollable_frame, bg=self.card_color, 
            highlightthickness=1, highlightbackground="#E5E8EB", bd=0
        )
        self.progress_card.pack(fill=tk.X, pady=10, padx=5)
        self.progress_card.pack_forget() # Hide initially
        
        progress_card_inner = tk.Frame(self.progress_card, bg=self.card_color)
        progress_card_inner.pack(fill=tk.X, padx=20, pady=20)
        
        self.status_label = tk.Label(progress_card_inner, text="작업 대기 중...", font=("Malgun Gothic", 10, "bold"), bg=self.card_color, fg=self.fg_color)
        self.status_label.pack(anchor=tk.W, pady=(0, 8))
        
        self.progress_bar = ttk.Progressbar(progress_card_inner, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=(0, 12))
        
        log_label = tk.Label(progress_card_inner, text="상세 진행 상태 로그:", font=("Malgun Gothic", 9, "bold"), bg=self.card_color, fg=self.fg_muted)
        log_label.pack(anchor=tk.W, pady=(5, 4))
        
        log_text_frame = tk.Frame(progress_card_inner, bg=self.console_bg,
                                   highlightthickness=1, highlightbackground="#E5E8EB")
        log_text_frame.pack(fill=tk.X, pady=5)
        log_scroll = ttk.Scrollbar(log_text_frame, orient="vertical")
        self.log_text = tk.Text(
            log_text_frame, height=12, bg=self.console_bg, fg="#F3F4F6",
            font=("Consolas", 9), relief="flat", state=tk.DISABLED,
            highlightthickness=0, yscrollcommand=log_scroll.set
        )
        log_scroll.config(command=self.log_text.yview)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
    def toggle_os(self, value):
        self.target_os_var.set(value)
        if value == "windows":
            self.os_win_btn.configure(bg=self.accent_color, fg="#FFFFFF")
            self.os_lin_btn.configure(bg="#E5E8EB", fg=self.fg_muted)
        else:
            self.os_win_btn.configure(bg="#E5E8EB", fg=self.fg_muted)
            self.os_lin_btn.configure(bg=self.accent_color, fg="#FFFFFF")

    def toggle_arch(self, value):
        self.target_arch_var.set(value)
        if value == "x86_64":
            self.arch_64_btn.configure(bg=self.accent_color, fg="#FFFFFF")
            self.arch_arm_btn.configure(bg="#E5E8EB", fg=self.fg_muted)
        else:
            self.arch_64_btn.configure(bg="#E5E8EB", fg=self.fg_muted)
            self.arch_arm_btn.configure(bg=self.accent_color, fg="#FFFFFF")

    def toggle_scope(self, value):
        self.package_scope_var.set(value)
        if value == "all":
            self.scope_all_btn.configure(bg=self.accent_color, fg="#FFFFFF")
            self.scope_new_btn.configure(bg="#E5E8EB", fg=self.fg_muted)
        else:
            self.scope_all_btn.configure(bg="#E5E8EB", fg=self.fg_muted)
            self.scope_new_btn.configure(bg=self.accent_color, fg="#FFFFFF")

    def reset_wheel_registry(self):
        """downloaded_wheels.json 을 삭제하여 신규패키지 기준을 초기화합니다."""
        # workspace_dir: builder.py 와 동일한 로직으로 결정
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

        # 현재 등록 건수 표시
        try:
            import json
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

    def toggle_py_version(self, ver):
        current = self.py_vars[ver].get()
        new_state = not current
        self.py_vars[ver].set(new_state)
        
        btn = self.py_buttons[ver]
        if new_state:
            btn.configure(bg=self.accent_color, fg="#FFFFFF")
        else:
            btn.configure(bg="#E5E8EB", fg=self.fg_muted)

    def add_custom_python(self):
        ver = self.custom_py_entry.get().strip()
        if not ver:
            return
        
        # Simple ver format validate
        import re
        if not re.match(r"^\d+\.\d+(\.\d+)?$", ver):
            messagebox.showerror("입력 오류", "올바른 파이썬 버전 형식이 아닙니다 (예: 3.12.3 또는 3.11)")
            return
            
        if ver in self.py_vars:
            messagebox.showwarning("입력 경고", "이미 존재하는 버전입니다.")
            self.custom_py_entry.delete(0, tk.END)
            return
            
        self.py_versions.append(ver)
        var = tk.BooleanVar(value=True)
        self.py_vars[ver] = var
        
        btn = tk.Button(
            self.checkbox_frame, text=f"Python {ver}", 
            command=lambda v=ver: self.toggle_py_version(v),
            font=("Malgun Gothic", 9, "bold"), relief="flat", bd=0, cursor="hand2", padx=15, pady=6,
            bg=self.accent_color, fg="#FFFFFF"
        )
        col = len(self.py_vars) - 1
        btn.grid(row=col // 5, column=col % 5, padx=4, pady=5)
        self.py_buttons[ver] = btn
        
        self.custom_py_entry.delete(0, tk.END)
        messagebox.showinfo("추가 완료", f"Python {ver} 버전이 목록에 추가되고 선택되었습니다.")
        
    def browse_output(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".zip",
            filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
            initialfile="uv-offline-package.zip"
        )
        if path:
            self.output_path_entry.delete(0, tk.END)
            self.output_path_entry.insert(0, path)
            
    def append_log(self, text):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)
        
    def update_progress(self, percent):
        self.progress_bar["value"] = percent
        
    def update_status_text(self, text):
        self.status_label.configure(text=text)
        
    def start_build(self):
        # 1. Gather form input
        target_os = self.target_os_var.get()
        target_arch = self.target_arch_var.get()
        uv_version = self.uv_version_entry.get().strip() or "latest"
        output_zip = self.output_path_entry.get().strip()
        ssl_bypass = self.ssl_bypass_var.get()
        
        selected_py = [ver for ver, var in self.py_vars.items() if var.get()]
        if not selected_py:
            messagebox.showerror("입력 오류", "최소 1개 이상의 Python 버전을 선택해주세요.")
            return
            
        pip_text = self.pip_packages_text.get("1.0", tk.END)
        pip_packages = []
        for line in pip_text.split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                pip_packages.append(line)
                
        if not output_zip:
            messagebox.showerror("입력 오류", "저장할 출력 ZIP 경로를 설정해주세요.")
            return
            
        # 2. Setup progress panel
        self.progress_card.pack(fill=tk.X, pady=10)
        self.build_btn.configure(state=tk.DISABLED)
        self.progress_bar["value"] = 0
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)
        
        # 3. Thread Safe Callbacks
        def thread_safe_log(msg):
            self.root.after(0, lambda: self.append_log(msg))
            
        def thread_safe_progress(pct):
            self.root.after(0, lambda: self.update_progress(pct))
            
        def thread_safe_status(txt):
            self.root.after(0, lambda: self.update_status_text(txt))
            
        # 4. Background thread execution
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
                    ssl_bypass=ssl_bypass
                )
                
                thread_safe_status("빌드 완료!")
                
                # Show popup
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
                self.root.after(0, show_result)
            except Exception as e:
                thread_safe_status("빌드 에러 발생")
                thread_safe_log(f"[ERROR] 빌드에 실패했습니다: {e}")
                self.root.after(0, lambda: messagebox.showerror("빌드 실패", f"에러가 발생하여 빌드가 취소되었습니다.\n\n상세 정보:\n{e}"))
            finally:
                self.root.after(0, lambda: self.build_btn.configure(state=tk.NORMAL))
                
        t = threading.Thread(target=run, daemon=True)
        t.start()

if __name__ == "__main__":
    # Prevent Windows from grouping it incorrectly under Python
    if sys.platform == 'win32':
        import ctypes
        myappid = 'google.deepmind.uvtool.builder.1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        
    root = tk.Tk()
    app = BuilderApp(root)
    root.mainloop()
