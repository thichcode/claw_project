param(
    [int]$RestartDelaySeconds = 5
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$python = Join-Path $scriptDir ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python venv not found at $python"
}

$logDir = Join-Path $scriptDir "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

while ($true) {
    $ts = Get-Date -Format "yyyy-MM-dd"
    $outLog = Join-Path $logDir "bot-$ts.log"

    "[$(Get-Date -Format s)] starting bot process" | Tee-Object -FilePath $outLog -Append
    & $python "bot.py" *>> $outLog
    $exitCode = $LASTEXITCODE

    "[$(Get-Date -Format s)] bot exited with code $exitCode; restart in $RestartDelaySeconds sec" | Tee-Object -FilePath $outLog -Append
    Start-Sleep -Seconds $RestartDelaySeconds
}
