<#
.SYNOPSIS
  Watch a case workspace's 01_mail_in folder and run LexIntake on new mail.

.DESCRIPTION
  The hands-free attorney loop: drag exports from Outlook (or save from
  Clio/iManage) into 01_mail_in and the pipeline runs itself a few seconds
  later. Debounced so a 50-file drag triggers one run, not fifty; the
  pipeline's idempotency makes overlapping triggers harmless anyway.

.EXAMPLE
  pwsh .\Watch-MailIn.ps1 -Workspace C:\cases\lucerne
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string]$Workspace,
  [int]$DebounceSeconds = 5
)

$ErrorActionPreference = 'Stop'
$inbox = Join-Path $Workspace '01_mail_in'
if (-not (Test-Path $inbox)) { throw "Not a LexIntake workspace (no 01_mail_in): $Workspace" }

$watcher = [System.IO.FileSystemWatcher]::new($inbox)
$watcher.Filter = '*.*'
$watcher.EnableRaisingEvents = $true

Write-Host "Watching $inbox — Ctrl+C to stop." -ForegroundColor Cyan
$pending = $false
Register-ObjectEvent $watcher Created -Action { $script:pending = $true } | Out-Null
Register-ObjectEvent $watcher Renamed -Action { $script:pending = $true } | Out-Null

try {
  while ($true) {
    Start-Sleep -Seconds $DebounceSeconds
    if ($pending) {
      $pending = $false
      Write-Host "`n[$(Get-Date -Format HH:mm:ss)] new mail detected — running pipeline" -ForegroundColor Green
      lexintake run $Workspace
    }
  }
} finally {
  $watcher.Dispose()
}
