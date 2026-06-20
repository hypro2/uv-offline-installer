<#
.SYNOPSIS
    uv 오프라인 간편 설치 스크립트 (폐쇄망 전용)

.DESCRIPTION
    인터넷 연결 없이 로컬 패키지 파일만으로 uv 및 Python standalone을 설치합니다.
    아래 공식 명령의 폐쇄망 대체품입니다:
        powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"

    실행 방법 (인수 없이 바로 실행):
        powershell -ExecutionPolicy Bypass -File install_offline.ps1

    또는 경로를 직접 지정:
        powershell -ExecutionPolicy Bypass -File install_offline.ps1 `
            -SourceDir "D:\transfer\uvtool-pack" `
            -InstallDir "$env:USERPROFILE\.local\bin"

.PARAMETER SourceDir
    uv zip, CPython 아카이브, wheels 폴더가 있는 소스 디렉토리.
    기본값: 이 스크립트 파일이 있는 폴더.

.PARAMETER InstallDir
    uv.exe 및 Python을 설치할 경로.
    기본값: $env:USERPROFILE\.local\bin

.PARAMETER NoEnvVar
    전역 환경 변수(UV_NO_INDEX, UV_FIND_LINKS) 대신 uv.toml을 생성합니다.

.PARAMETER SkipPython
    CPython 압축 해제를 건너뜁니다.

.PARAMETER SkipWheels
    wheels 복사를 건너뜁니다.

.PARAMETER WhatIf
    실제로 실행하지 않고 수행할 작업 목록만 출력합니다.
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$SourceDir  = "",
    [string]$InstallDir = "$env:USERPROFILE\.local\bin",
    [switch]$NoEnvVar,
    [switch]$SkipPython,
    [switch]$SkipWheels,
    [switch]$WhatIf
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼 함수
# ─────────────────────────────────────────────────────────────────────────────

function Write-Step  { param([string]$Msg) Write-Host ""; Write-Host ">>> $Msg" -ForegroundColor Cyan }
function Write-Ok    { param([string]$Msg) Write-Host "  [OK] $Msg"   -ForegroundColor Green }
function Write-Info  { param([string]$Msg) Write-Host "  [INFO] $Msg" -ForegroundColor Gray }
function Write-Warn  { param([string]$Msg) Write-Host "  [WARN] $Msg" -ForegroundColor Yellow }
function Write-Fail  { param([string]$Msg) Write-Host "  [FAIL] $Msg" -ForegroundColor Red; throw $Msg }

function Add-ToUserPath {
    param([string]$NewPath)
    $cur = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    if ($null -eq $cur) { $cur = "" }
    $parts   = $cur -split ";" | Where-Object { $_ -ne "" }
    $normNew = [System.IO.Path]::GetFullPath($NewPath).ToLower()
    $already = $parts | Where-Object { [System.IO.Path]::GetFullPath($_).ToLower() -eq $normNew }
    if (-not $already) {
        [System.Environment]::SetEnvironmentVariable("PATH", ($parts + $NewPath) -join ";", "User")
        Write-Ok "PATH 추가: $NewPath"
    } else {
        Write-Info "이미 PATH에 존재: $NewPath"
    }
    $env:PATH = "$NewPath;$env:PATH"
}

function Find-FileByPattern {
    param([string[]]$SearchDirs, [string]$Pattern)
    foreach ($dir in $SearchDirs) {
        if (-not (Test-Path $dir)) { continue }
        $f = Get-ChildItem -Path $dir -Filter $Pattern -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($f) { return $f.FullName }
    }
    return $null
}

function Find-AllByPattern {
    param([string[]]$SearchDirs, [string]$Pattern)
    $results = @()
    foreach ($dir in $SearchDirs) {
        if (-not (Test-Path $dir)) { continue }
        $results += Get-ChildItem -Path $dir -Filter $Pattern -File -ErrorAction SilentlyContinue
    }
    return $results
}

# ─────────────────────────────────────────────────────────────────────────────
# 소스 디렉토리 결정
# ─────────────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "══════════════════════════════════════════════════════════════" -ForegroundColor Blue
Write-Host "  uv 오프라인 설치 스크립트 (폐쇄망 전용)"                     -ForegroundColor White
Write-Host "  대체 명령: irm https://astral.sh/uv/install.ps1 | iex"       -ForegroundColor DarkGray
Write-Host "══════════════════════════════════════════════════════════════" -ForegroundColor Blue
Write-Host ""

if ($SourceDir -eq "") {
    $SourceDir = if ($PSScriptRoot) { $PSScriptRoot } else { $PWD.Path }
    Write-Info "소스 디렉토리 자동 감지: $SourceDir"
}

if (-not (Test-Path $SourceDir)) {
    Write-Fail "소스 디렉토리를 찾을 수 없습니다: $SourceDir"
}

$searchRoots = @($SourceDir)
$payloadSub  = Join-Path $SourceDir "payload"
if (Test-Path $payloadSub) { $searchRoots += $payloadSub }
Write-Info "설치 파일 탐색 경로: $($searchRoots -join ', ')"

# ─────────────────────────────────────────────────────────────────────────────
# Step 0: 설치 파일 탐색 및 검증
# ─────────────────────────────────────────────────────────────────────────────
Write-Step "설치 파일 탐색 중..."

$uvArchivePath = Find-FileByPattern -SearchDirs $searchRoots -Pattern "uv-*.zip"
if (-not $uvArchivePath) {
    $uvArchivePath = Find-FileByPattern -SearchDirs $searchRoots -Pattern "uv-*.tar.gz"
}

$pySearchDirs = $searchRoots.Clone()
foreach ($r in $searchRoots) {
    $sub = Join-Path $r "python"
    if (Test-Path $sub) { $pySearchDirs += $sub }
}
$pyArchives  = @(Find-AllByPattern -SearchDirs $pySearchDirs -Pattern "cpython-*.tar.gz")
$pyArchives += @(Find-AllByPattern -SearchDirs $pySearchDirs -Pattern "cpython-*.zip")
$pyArchives  = $pyArchives | Sort-Object Name -Unique

$wheelsDir = $null
foreach ($r in $searchRoots) {
    $c = Join-Path $r "wheels"
    if (Test-Path $c) { $wheelsDir = $c; break }
}

Write-Host ""
Write-Host "  발견된 설치 파일:" -ForegroundColor White

if ($uvArchivePath) {
    Write-Ok "uv 아카이브: $(Split-Path $uvArchivePath -Leaf)"
} else {
    $existingUvExe = Join-Path $InstallDir "uv.exe"
    if ((Get-Command uv -ErrorAction SilentlyContinue) -or (Test-Path $existingUvExe)) {
        Write-Warn "uv 아카이브 없음 — 기존 설치된 uv 사용"
    } else {
        Write-Fail "uv 아카이브 파일을 찾을 수 없습니다. 소스 디렉토리를 확인하십시오:`n  $SourceDir"
    }
}

if ($pyArchives.Count -gt 0) {
    foreach ($a in $pyArchives) { Write-Ok "Python 아카이브: $($a.Name)" }
} else {
    Write-Warn "Python 아카이브 없음 — Python 설치를 건너뜁니다."
    $SkipPython = $true
}

if ($wheelsDir) {
    $whlCount = (Get-ChildItem $wheelsDir -Filter "*.whl" -ErrorAction SilentlyContinue).Count
    Write-Ok "Wheels 폴더: $wheelsDir ($whlCount 개)"
} else {
    Write-Warn "Wheels 폴더 없음 — wheels 복사를 건너뜁니다."
    $SkipWheels = $true
}

if ($WhatIf) {
    Write-Host ""
    Write-Host "  [WhatIf] '$InstallDir' 에 설치 예정. -WhatIf 없이 실행하면 실제 설치됩니다." -ForegroundColor Magenta
    exit 0
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 1/5: 설치 디렉토리 준비
# ─────────────────────────────────────────────────────────────────────────────
Write-Step "1/5  설치 디렉토리 준비: $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir "wheels") | Out-Null
Write-Ok "디렉토리 준비 완료"

# ─────────────────────────────────────────────────────────────────────────────
# Step 2/5: uv 바이너리 압축 해제
# ─────────────────────────────────────────────────────────────────────────────
if ($uvArchivePath) {
    Write-Step "2/5  uv 바이너리 압축 해제..."
    $tempUvDir = Join-Path $InstallDir "_temp_uv"
    try {
        if (Test-Path $tempUvDir) { Remove-Item $tempUvDir -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $tempUvDir | Out-Null

        if ($uvArchivePath.EndsWith(".zip")) {
            Expand-Archive -Path $uvArchivePath -DestinationPath $tempUvDir -Force
        } elseif ($uvArchivePath.EndsWith(".tar.gz")) {
            tar -xzf $uvArchivePath -C $tempUvDir 2>&1 | Out-Null
        }

        $uvExe  = Get-ChildItem -Path $tempUvDir -Filter "uv.exe"  -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        $uvxExe = Get-ChildItem -Path $tempUvDir -Filter "uvx.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1

        if ($uvExe) {
            Copy-Item $uvExe.FullName  (Join-Path $InstallDir "uv.exe")  -Force
            Write-Ok "uv.exe 설치 완료"
        } else {
            Write-Warn "아카이브에서 uv.exe를 찾지 못했습니다."
        }
        if ($uvxExe) {
            Copy-Item $uvxExe.FullName (Join-Path $InstallDir "uvx.exe") -Force
            Write-Ok "uvx.exe 설치 완료"
        }
    } finally {
        if (Test-Path $tempUvDir) { Remove-Item $tempUvDir -Recurse -Force -ErrorAction SilentlyContinue }
    }
} else {
    Write-Step "2/5  uv 바이너리 — 기존 설치 사용 (건너뜀)"
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 3/5: Python Standalone 압축 해제
# installer.py 와 동일한 로직: 임시 폴더 → 서브폴더("install","python") 감지 → 이동
# ─────────────────────────────────────────────────────────────────────────────
$installedPyDirs = @()
if (-not $SkipPython -and $pyArchives.Count -gt 0) {
    Write-Step "3/5  Python Standalone 압축 해제..."
    foreach ($pyArch in $pyArchives) {
        $archName = $pyArch.Name
        if ($archName -match "cpython-(\d+\.\d+)[\.\+]") {
            $pyMajorMinor = $Matches[1]
        } else {
            $pyMajorMinor = "unknown"
        }

        $pyDestDir  = Join-Path $InstallDir "python\$pyMajorMinor"
        $tempPyDir  = Join-Path $InstallDir "_temp_py_$pyMajorMinor"
        if (Test-Path $pyDestDir) { Remove-Item $pyDestDir -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $pyDestDir | Out-Null
        New-Item -ItemType Directory -Force -Path $tempPyDir | Out-Null

        Write-Info "Python $pyMajorMinor 압축 해제 중: $archName"
        try {
            if ($pyArch.FullName.EndsWith(".tar.gz")) {
                tar -xzf $pyArch.FullName -C $tempPyDir 2>&1
                if ($LASTEXITCODE -ne 0) { Write-Fail "Python $pyMajorMinor 압축 해제 실패 (exit: $LASTEXITCODE)" }
            } elseif ($pyArch.FullName.EndsWith(".zip")) {
                Expand-Archive -Path $pyArch.FullName -DestinationPath $tempPyDir -Force
            }

            # installer.py 와 동일: "install" 또는 "python" 서브폴더 감지
            $srcDir = $tempPyDir
            foreach ($sub in @("install", "python")) {
                $cand = Join-Path $tempPyDir $sub
                if ((Test-Path $cand) -and (Test-Path (Join-Path $cand "python.exe"))) {
                    $srcDir = $cand
                    Write-Info "$sub 서브폴더 감지 → 내용물을 상위로 이동합니다"
                    break
                }
            }

            Get-ChildItem -Path $srcDir | ForEach-Object {
                $dest = Join-Path $pyDestDir $_.Name
                if (Test-Path $dest) {
                    if ($_.PSIsContainer) { Remove-Item $dest -Recurse -Force }
                    else                  { Remove-Item $dest -Force }
                }
                Move-Item $_.FullName $dest -Force
            }

            $pythonExe = Get-ChildItem -Path $pyDestDir -Filter "python.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($pythonExe) {
                Write-Ok "Python $pyMajorMinor 설치 완료: $($pythonExe.FullName)"
                $installedPyDirs += $pyDestDir
            } else {
                Write-Warn "python.exe를 해제된 폴더에서 찾지 못했습니다: $pyDestDir"
            }
        } finally {
            if (Test-Path $tempPyDir) { Remove-Item $tempPyDir -Recurse -Force -ErrorAction SilentlyContinue }
        }
    }
} else {
    Write-Step "3/5  Python 설치 — 건너뜀"
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 4/5: Wheels 복사
# ─────────────────────────────────────────────────────────────────────────────
if (-not $SkipWheels -and $wheelsDir) {
    Write-Step "4/5  오프라인 라이브러리(wheels) 복사..."
    $destWheels = Join-Path $InstallDir "wheels"
    $whlFiles   = Get-ChildItem -Path $wheelsDir -Filter "*.whl" -ErrorAction SilentlyContinue
    if ($whlFiles.Count -gt 0) {
        Copy-Item -Path "$wheelsDir\*.whl" -Destination $destWheels -Force -ErrorAction SilentlyContinue
        Write-Ok "$($whlFiles.Count) 개 wheel 파일 복사 완료 → $destWheels"
    } else {
        Write-Warn "wheels 폴더에 .whl 파일이 없습니다."
    }
} else {
    Write-Step "4/5  Wheels 복사 — 건너뜀"
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 5/5: 환경 변수 및 PATH 등록
# ─────────────────────────────────────────────────────────────────────────────
Write-Step "5/5  환경 변수 및 PATH 등록..."

Add-ToUserPath -NewPath $InstallDir

# Python PATH: python.exe 실제 위치 재탐색 후 등록
foreach ($pyDir in $installedPyDirs) {
    $pyExe = Get-ChildItem -Path $pyDir -Filter "python.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pyExe) {
        Add-ToUserPath -NewPath $pyExe.DirectoryName
    }
}

$wheelsForConfig = (Join-Path $InstallDir "wheels").Replace("\", "/")

if (-not $NoEnvVar) {
    [System.Environment]::SetEnvironmentVariable("UV_NO_INDEX",    "1",                          "User")
    [System.Environment]::SetEnvironmentVariable("UV_FIND_LINKS",  (Join-Path $InstallDir "wheels"), "User")
    $env:UV_NO_INDEX   = "1"
    $env:UV_FIND_LINKS = Join-Path $InstallDir "wheels"
    Write-Ok "환경 변수 등록: UV_NO_INDEX=1"
    Write-Ok "환경 변수 등록: UV_FIND_LINKS=$(Join-Path $InstallDir 'wheels')"
    Write-Info "※ 새 터미널을 열어야 완전히 적용됩니다."
} else {
    $tomlPath = Join-Path $InstallDir "uv.toml"
    $tomlContent = @"
[pip]
no-index = true
find-links = ["$wheelsForConfig"]

[install]
no-index = true
"@
    [System.IO.File]::WriteAllText($tomlPath, $tomlContent, [System.Text.Encoding]::UTF8)
    Write-Ok "uv.toml 생성: $tomlPath"
    Write-Info "[팁] 프로젝트 폴더에 이 uv.toml을 복사하면 전역 환경 오염 없이 오프라인 설치가 동작합니다."
}

# ─────────────────────────────────────────────────────────────────────────────
# 완료 출력
# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "══════════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  uv 오프라인 설치 완료!" -ForegroundColor White
Write-Host "══════════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""

$uvExePath = Join-Path $InstallDir "uv.exe"
if (Test-Path $uvExePath) {
    try {
        $uvVer = & $uvExePath --version 2>&1
        Write-Host "  설치된 uv 버전: $uvVer" -ForegroundColor Cyan
    } catch {
        Write-Host "  uv.exe 위치: $uvExePath" -ForegroundColor Cyan
    }
}

if ($installedPyDirs.Count -gt 0) {
    $pyVerNames = $installedPyDirs | ForEach-Object { Split-Path $_ -Leaf }
    Write-Host "  설치된 Python: $($pyVerNames -join ', ')" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "  새 터미널(PowerShell/CMD)을 열고 아래 명령어로 확인하십시오:" -ForegroundColor Yellow
Write-Host "    uv --version"    -ForegroundColor White
Write-Host "    python --version" -ForegroundColor White
Write-Host "    uv pip install [라이브러리명]" -ForegroundColor White
Write-Host ""

# PATH 브로드캐스트 (탐색기 등 즉시 반영)
# Add-Type 중복 등록 방지: 이미 WinAPI 타입이 있으면 건너뜀
try {
    if (-not ([System.Management.Automation.PSTypeName]'WinAPI').Type) {
        Add-Type -TypeDefinition @"
        using System;
        using System.Runtime.InteropServices;
        public class WinAPI {
            [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
            public static extern IntPtr SendMessageTimeout(
                IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam,
                uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);
        }
"@ -ErrorAction SilentlyContinue
    }
    $result = [UIntPtr]::Zero
    [WinAPI]::SendMessageTimeout([IntPtr]0xFFFF, 0x001A, [UIntPtr]::Zero, "Environment", 2, 3000, [ref]$result) | Out-Null
} catch { <# 브로드캐스트 실패는 무시 #> }
