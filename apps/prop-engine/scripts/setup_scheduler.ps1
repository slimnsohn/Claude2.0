# Registers two daily Task Scheduler jobs for the WNBA pipeline.
# Run once as user (no admin needed for user-scoped tasks):
#   powershell -ExecutionPolicy Bypass -File setup_scheduler.ps1

$ErrorActionPreference = "Stop"
$appDir = Split-Path -Parent $PSScriptRoot
$python = "C:\Users\slims\miniconda3\python.exe"
$cli    = Join-Path $appDir "cli.py"

function RegisterJob($name, $hour, $minute) {
    $action = New-ScheduledTaskAction -Execute $python -Argument "`"$cli`" wnba" -WorkingDirectory $appDir
    $trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours($hour).AddMinutes($minute))
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Host "Registered: $name at ${hour}:${minute}"
}

RegisterJob "prop-engine-wnba-am" 10  0
RegisterJob "prop-engine-wnba-pm" 14  0

Write-Host "Done. Inspect with: Get-ScheduledTask -TaskName 'prop-engine-wnba*'"
