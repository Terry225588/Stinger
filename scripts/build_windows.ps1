# Build a Windows folder. This file is ASCII plus a UTF-8 BOM so
# Windows PowerShell 5.1 does not mis-read it as the system ANSI code page.
# It has not been executed in the Linux environment that wrote it.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ($env:OS -ne "Windows_NT") {
    Write-Error "Run this script on Windows."
}

function Test-Python312 {
    param([string]$Executable, [string[]]$Prefix)
    if (-not $Executable) { return $false }
    if ($Prefix.Count -eq 0 -and -not (Test-Path -LiteralPath $Executable) -and -not (Get-Command $Executable -ErrorAction SilentlyContinue)) {
        return $false
    }
    try {
        $versionText = & $Executable @Prefix -c "import sys; print(str(sys.version_info[0]) + '.' + str(sys.version_info[1]))"
    } catch {
        return $false
    }
    return ($versionText -eq "3.12")
}

function Find-Python312 {
    $fromEnv = $env:SCREENMATCH_PYTHON
    if ($fromEnv -and (Test-Python312 -Executable $fromEnv -Prefix @())) {
        return $fromEnv
    }
    $sibling = Join-Path $root "..\Python312\python.exe"
    if (Test-Python312 -Executable $sibling -Prefix @()) {
        return (Resolve-Path -LiteralPath $sibling).Path
    }
    $localApp = $env:LOCALAPPDATA
    if ($localApp) {
        $userInstall = Join-Path $localApp "Programs\Python\Python312\python.exe"
        if (Test-Python312 -Executable $userInstall -Prefix @()) {
            return $userInstall
        }
    }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py -and (Test-Python312 -Executable "py" -Prefix @("-3.12"))) {
        return "py"
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python -and (Test-Python312 -Executable "python" -Prefix @())) {
        return "python"
    }
    return $null
}

$found = Find-Python312
if ($null -eq $found) {
    Write-Error "Python 3.12 was not found. Set SCREENMATCH_PYTHON to python.exe. Python 3.12 is required because numpy 2.5.5 has no older Windows wheel. The py launcher and global PATH are optional."
}

$entry = Join-Path $root "main.py"
$spec = Join-Path $root "packaging\screenmatch.spec"
if (-not (Test-Path -LiteralPath $entry)) {
    Write-Error "main.py is missing at the repository root: $entry"
}
if (-not (Test-Path -LiteralPath $spec)) {
    Write-Error "Spec file is missing: $spec"
}

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    if ($found -eq "py") {
        & py -3.12 -m venv (Join-Path $root ".venv")
    } else {
        & $found -m venv (Join-Path $root ".venv")
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "venv creation failed with exit code $LASTEXITCODE"
    }
}
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Error "venv python was not created: $venvPython"
}

& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip upgrade failed with exit code $LASTEXITCODE"
}
& $venvPython -m pip install -r (Join-Path $root "requirements.txt") -r (Join-Path $root "requirements-build.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install failed with exit code $LASTEXITCODE"
}
& $venvPython -m PyInstaller --noconfirm --clean $spec
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed with exit code $LASTEXITCODE"
}

$dist = Join-Path $root "dist\Stinger"
$required = @(
    "ch_PP-OCRv4_det_infer.onnx",
    "ch_PP-OCRv4_rec_infer.onnx",
    "ch_ppocr_mobile_v2.0_cls_infer.onnx"
)
$foundModels = @()
if (Test-Path -LiteralPath $dist) {
    $foundModels = @(Get-ChildItem -Recurse -File -LiteralPath $dist | Where-Object { $required -contains $_.Name } | Select-Object -ExpandProperty Name -Unique)
}
$missing = @($required | Where-Object { $foundModels -notcontains $_ })
if ($missing.Count -gt 0) {
    Write-Error ("Packaged folder is missing local OCR models: " + ($missing -join ", "))
}

Write-Host "Models were copied into dist\Stinger. Keep the whole folder."
Write-Host "This script has not been run on the machine that wrote it. Open the folder on Windows 10 and test a real selection before trusting it."
