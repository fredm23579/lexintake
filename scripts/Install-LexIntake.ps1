<#
.SYNOPSIS
  One-shot LexIntake install on Windows: clones the three upstream repos,
  builds an isolated venv, installs everything, and verifies with `doctor`.

.DESCRIPTION
  Safe to re-run: existing clones are updated (git pull --ff-only), the venv
  is reused, and installs are idempotent. Requires only git + Python 3.11+
  on PATH (PowerShell 7 recommended; Windows PowerShell 5.1 works).

.EXAMPLE
  irm https://raw.githubusercontent.com/fredm23579/lexintake/main/scripts/Install-LexIntake.ps1 | iex

.EXAMPLE
  .\Install-LexIntake.ps1 -InstallDir D:\tools\lexintake -WithBrowser
#>
[CmdletBinding()]
param(
  # Where LexIntake and its upstream repos live.
  [string]$InstallDir = "$env:LOCALAPPDATA\LexIntake",
  # Also install Playwright + browser extras for live Stage 1 export.
  [switch]$WithBrowser
)

$ErrorActionPreference = 'Stop'
$repos = [ordered]@{
  'lexintake'            = 'https://github.com/fredm23579/lexintake.git'
  'mail2md-computer-use' = 'https://github.com/fredm23579/mail2md-computer-use.git'
  'omniconvert-md'       = 'https://github.com/fredm23579/omniconvert-md.git'
  'notebooklm-manager'   = 'https://github.com/fredm23579/notebooklm-manager.git'
}

function Resolve-Python {
  # Prefer the py launcher (handles multiple installs); fall back to python.
  foreach ($candidate in @('py -3.14', 'py -3.13', 'py -3.12', 'py -3.11', 'python')) {
    try {
      $v = Invoke-Expression "$candidate --version" 2>$null
      if ($v -match 'Python 3\.1[1-9]') { return $candidate }
    } catch { }
  }
  throw 'Python 3.11+ not found. Install from https://www.python.org/downloads/windows/ (check "Add to PATH").'
}

Write-Host "LexIntake installer -> $InstallDir" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

foreach ($name in $repos.Keys) {
  $dest = Join-Path $InstallDir $name
  if (Test-Path (Join-Path $dest '.git')) {
    Write-Host "  updating $name" -ForegroundColor DarkGray
    git -C $dest pull --ff-only --quiet
  } else {
    Write-Host "  cloning  $name" -ForegroundColor DarkGray
    git clone --depth 1 --quiet $repos[$name] $dest
  }
}

$venv = Join-Path $InstallDir '.venv'
$py   = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $py)) {
  $base = Resolve-Python
  Write-Host "  creating venv ($base)" -ForegroundColor DarkGray
  Invoke-Expression "$base -m venv `"$venv`""
}

Write-Host '  installing packages (first run takes a few minutes)' -ForegroundColor DarkGray
& $py -m pip install --quiet --upgrade pip
# omniconvert with Office/PDF extras, the source manager, then mail2md.
& $py -m pip install --quiet -e "$(Join-Path $InstallDir 'omniconvert-md')[documents,msg]"
& $py -m pip install --quiet -e (Join-Path $InstallDir 'notebooklm-manager')
if ($WithBrowser) {
  & $py -m pip install --quiet -e (Join-Path $InstallDir 'mail2md-computer-use')
  & $py -m playwright install chromium
} else {
  # Converter path only: skip playwright/google-genai until export is needed.
  & $py -m pip install --quiet --no-deps -e (Join-Path $InstallDir 'mail2md-computer-use')
  & $py -m pip install --quiet 'markdownify>=1.2,<2' 'extract-msg>=0.55,<1' 'typer>=0.16,<1'
}
& $py -m pip install --quiet --no-deps -e (Join-Path $InstallDir 'lexintake')

# Put a `lexintake` shim on the user PATH so any shell can run it.
$binDir = Join-Path $InstallDir 'bin'
New-Item -ItemType Directory -Force -Path $binDir | Out-Null
Set-Content -Path (Join-Path $binDir 'lexintake.cmd') -Value "@`"$py`" -m lexintake.cli %*"
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath -notlike "*$binDir*") {
  [Environment]::SetEnvironmentVariable('Path', "$userPath;$binDir", 'User')
  Write-Host "  added $binDir to your user PATH (new terminals pick it up)" -ForegroundColor DarkGray
}

Write-Host "`nVerifying:" -ForegroundColor Cyan
& $py -m lexintake.cli doctor $InstallDir

Write-Host @"

Done. Next steps (new terminal):
  lexintake init C:\cases\my-matter --notebook MY-NOTEBOOK-ID
  ... drop .eml/.msg/.mbox into C:\cases\my-matter\01_mail_in ...
  lexintake run  C:\cases\my-matter
"@ -ForegroundColor Green
