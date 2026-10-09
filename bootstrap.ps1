<#
  bootstrap.ps1 -- one-shot setup of the development environment.

  Automates what can be automated:
    1. Python + pipeline dependencies (requirements.txt)
    2. git submodules (tools/vendor/...)
    3. clone the upstream recomp into extract/f2/recomp and apply mod/recomp/local-changes.patch
  and checks the external tools that cannot be installed silently (7-Zip, Tesseract,
  CMake/Ninja/Clang/MSBuild), printing what to install.

  It does NOT download game assets: you must provide your own legal discs in roms/.

  Usage:  powershell -ExecutionPolicy Bypass -File bootstrap.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipPython,
    [switch]$SkipRecomp
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Repo

function Info($m) { Write-Host "[bootstrap] $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "  [ok] $m"   -ForegroundColor Green }
function Warn($m) { Write-Host "  [!]  $m"   -ForegroundColor Yellow }
function Have($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

$RECOMP_URL  = "https://github.com/doc-haz/infinite-undiscovery-recomp"
$RECOMP_DIR  = Join-Path $Repo "extract/f2/recomp"

# ---------------------------------------------------------------- 1. Python
if (-not $SkipPython) {
    Info "Python dependencies"
    $py = if (Have py) { "py" } elseif (Have python) { "python" } else { $null }
    if (-not $py) {
        Warn "Python not found. Install Python 3.10+ (https://www.python.org/downloads/) and re-run."
    } else {
        & $py -m pip install --upgrade pip
        & $py -m pip install -r (Join-Path $Repo "requirements.txt")
        Ok "pipeline dependencies installed"
    }
}

# ------------------------------------------------------------- 2. Submodules
Info "git submodules"
if (Have git) {
    git submodule update --init --recursive
    Ok "submodules ready (tools/vendor/pc-infiniteundiscovery)"
} else {
    Warn "git not found in PATH"
}

# ------------------------------------------------- 3. Upstream recomp + patch
if (-not $SkipRecomp) {
    Info "upstream recomp"
    if (Test-Path (Join-Path $RECOMP_DIR ".git")) {
        Ok "already present at $RECOMP_DIR"
    } elseif (Have git) {
        New-Item -ItemType Directory -Force -Path (Split-Path $RECOMP_DIR) | Out-Null
        git clone --recurse-submodules $RECOMP_URL $RECOMP_DIR
        Ok "cloned $RECOMP_URL"
    } else {
        Warn "git not found: cannot clone $RECOMP_URL"
    }

    $patch = Join-Path $Repo "mod/recomp/local-changes.patch"
    if ((Test-Path (Join-Path $RECOMP_DIR ".git")) -and (Test-Path $patch)) {
        Push-Location $RECOMP_DIR
        try {
            git apply --check $patch 2>$null
            if ($LASTEXITCODE -eq 0) {
                git apply $patch
                Ok "applied mod/recomp/local-changes.patch"
            } else {
                Warn "patch already applied or does not apply cleanly (skip)"
            }
        } finally { Pop-Location }
    }
}

# ------------------------------------------------------- 4. External tools
Info "external tools (install manually if missing)"
$checks = @(
    @{ n = "7-Zip";        p = "C:\Program Files\7-Zip\7z.exe" },
    @{ n = "Tesseract OCR"; p = "C:\Program Files\Tesseract-OCR\tesseract.exe" },
    @{ n = "CMake";        c = "cmake" },
    @{ n = "Ninja";        c = "ninja" },
    @{ n = "Clang";        c = "clang" },
    @{ n = "MSBuild";      c = "MSBuild" },
    @{ n = "git";          c = "git" }
)
foreach ($c in $checks) {
    $found = if ($c.p) { Test-Path $c.p } else { Have $c.c }
    if ($found) { Ok $c.n } else { Warn "$($c.n) — not found" }
}

Write-Host ""
Info "next steps"
Write-Host "  1. Put your LEGAL discs in roms\ (Disc 1 + Disc 2)."
Write-Host "  2. Extract resources:  python tools\extract_rmd.py --roms roms --out extract\f0"
Write-Host "  3. See docs\SETUP.md for the full reconstruction and docs\TOOLS.md for the pipeline."
