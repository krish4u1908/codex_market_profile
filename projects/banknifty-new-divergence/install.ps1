[CmdletBinding()]
param(
    [string]$Python = "",
    [string]$VenvDir = ".venv"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Test-Path -LiteralPath (Join-Path $ProjectDir "pyproject.toml") -PathType Leaf)) {
    throw "pyproject.toml was not found. Extract the complete release archive, then run this script from that extracted folder."
}

$PythonExe = $null
$PythonPrefixArgs = @()

if ($Python) {
    $PythonCommand = Get-Command $Python -ErrorAction SilentlyContinue
    if (-not $PythonCommand) {
        throw "Python command '$Python' was not found."
    }
    $PythonExe = $PythonCommand.Source
}
else {
    $PyLauncher = Get-Command "py" -ErrorAction SilentlyContinue
    if ($PyLauncher) {
        $PythonExe = $PyLauncher.Source
        $PythonPrefixArgs = @("-3")
    }
    else {
        $PythonCommand = Get-Command "python" -ErrorAction SilentlyContinue
        if (-not $PythonCommand) {
            throw "Python 3.12 or newer is required. Install it, select 'Add python.exe to PATH', and rerun this script."
        }
        $PythonExe = $PythonCommand.Source
    }
}

& $PythonExe @PythonPrefixArgs -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "The selected Python is too old or Python 3.12 is unavailable. Python 3.12 or newer is required."
}

if ([System.IO.Path]::IsPathRooted($VenvDir)) {
    $ResolvedVenvDir = $VenvDir
}
else {
    $ResolvedVenvDir = Join-Path $ProjectDir $VenvDir
}
$VenvPython = Join-Path $ResolvedVenvDir "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    if (Test-Path -LiteralPath $ResolvedVenvDir) {
        throw "$ResolvedVenvDir exists but is not a usable virtual environment. Move it aside and rerun this script."
    }
    Write-Host "Creating virtual environment: $ResolvedVenvDir"
    & $PythonExe @PythonPrefixArgs -m venv $ResolvedVenvDir
    if ($LASTEXITCODE -ne 0) {
        throw "Virtual-environment creation failed."
    }
}

& $VenvPython -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "The existing virtual environment uses Python older than 3.12. Move $ResolvedVenvDir aside and rerun this script."
}

Write-Host "Installing BankNifty New Divergence..."
& $VenvPython -m pip install --disable-pip-version-check --upgrade $ProjectDir
if ($LASTEXITCODE -ne 0) {
    throw "Package installation failed."
}

Write-Host "Checking the installed command..."
& $VenvPython -m banknifty_profiler.new_divergence --help | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "The installed command failed its smoke check."
}

$ActivateScript = Join-Path $ResolvedVenvDir "Scripts\Activate.ps1"
Write-Host ""
Write-Host "Installation complete."
Write-Host "Activate it with:"
Write-Host "  & `"$ActivateScript`""
Write-Host "Then verify it with:"
Write-Host "  banknifty-new-divergence --help"
Write-Host ""
Write-Host "No replay, server, service, or background process was started."
