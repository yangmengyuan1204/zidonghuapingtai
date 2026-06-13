$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Venv = Join-Path $Root ".venv_ocr"

$created = $false
$launcher = Get-Command py -ErrorAction SilentlyContinue
if ($launcher) {
    foreach ($version in @("-3.11", "-3.12")) {
        & py $version -c "import sys, struct; raise SystemExit(0 if sys.version_info[:2] in [(3,11),(3,12)] and struct.calcsize('P') * 8 == 64 else 1)"
        if ($LASTEXITCODE -eq 0) {
            & py $version -m venv $Venv
            if ($LASTEXITCODE -eq 0) {
                $created = $true
                break
            }
        }
    }
}

if (-not $created) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        & python -c "import sys, struct; raise SystemExit(0 if sys.version_info[:2] in [(3,11),(3,12)] and struct.calcsize('P') * 8 == 64 else 1)"
        if ($LASTEXITCODE -eq 0) {
            & python -m venv $Venv
            if ($LASTEXITCODE -eq 0) {
                $created = $true
            }
        }
    }
}

if (-not $created) {
    throw "Python 3.11/3.12 x64 is required. Install Python 3.11 x64 and rerun this script."
}

$pip = Join-Path $Venv "Scripts\pip.exe"
& $pip install --upgrade pip
& $pip install "paddlepaddle==2.6.2" "paddleocr==2.9.1" "Pillow>=12.0.0" "opencv-python==4.10.0.84"

Write-Host "OCR runtime ready: $Venv"
