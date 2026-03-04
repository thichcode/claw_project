param(
    [string]$TaskName = "TelegramStockBot",
    [string]$WorkingDir = "$PSScriptRoot"
)

$ErrorActionPreference = 'Stop'

$runner = Join-Path $WorkingDir "run_bot_forever.ps1"
if (-not (Test-Path $runner)) {
    throw "Missing runner script: $runner"
}

$pwsh = (Get-Command powershell.exe).Source
$action = New-ScheduledTaskAction -Execute $pwsh -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`"" -WorkingDirectory $WorkingDir
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Auto-start Telegram stock bot" -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "Installed + started scheduled task: $TaskName"
