@echo off
echo ==========================================================
echo           uvtool Single Executable Compiler
echo ==========================================================
echo.
echo Compiling GUI scripts to standalone Windows programs...
echo.

echo [1/2] Compiling installer_gui.py (Installer)...
uv run --system-certs --with pyinstaller --with customtkinter pyinstaller --clean specs/installer_gui.spec
if %errorlevel% neq 0 (
    echo [ERROR] Failed to compile installer_gui.py
    pause
    exit /b %errorlevel%
)
echo Success.
echo.

echo [2/2] Compiling builder_gui.py (Builder with embedded Installer)...
uv run --system-certs --with pyinstaller --with customtkinter pyinstaller --clean specs/builder_gui.spec
if %errorlevel% neq 0 (
    echo [ERROR] Failed to compile builder_gui.py
    pause
    exit /b %errorlevel%
)
echo Success.
echo.

echo ==========================================================
echo [SUCCESS] Compilation completed successfully!
echo Executables are located in the dist/ folder.
echo.
echo builder_gui.exe now contains installer_gui.exe inside it!
echo You only need builder_gui.exe to distribute the builder.
echo ==========================================================
pause
