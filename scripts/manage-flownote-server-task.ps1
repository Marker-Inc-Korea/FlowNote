param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("start", "stop", "restart", "status", "unregister")]
    [string]$Action,
    [string]$TaskName = "FlowNoteApi",
    [string]$TaskPath = "\FlowNote\"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-FlowNoteTask {
    return Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction Stop
}

switch ($Action) {
    "start" {
        Get-FlowNoteTask | Out-Null
        Start-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath
        Write-Host "Started $TaskPath$TaskName"
    }
    "stop" {
        Get-FlowNoteTask | Out-Null
        Stop-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath
        Write-Host "Stopped $TaskPath$TaskName"
    }
    "restart" {
        Get-FlowNoteTask | Out-Null
        Stop-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        Start-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath
        Write-Host "Restarted $TaskPath$TaskName"
    }
    "status" {
        $task = Get-FlowNoteTask
        $info = Get-ScheduledTaskInfo -TaskName $TaskName -TaskPath $TaskPath
        [pscustomobject]@{
            TaskName = "$TaskPath$TaskName"
            State = $task.State
            LastRunTime = $info.LastRunTime
            LastTaskResult = $info.LastTaskResult
            NextRunTime = $info.NextRunTime
        } | Format-List
    }
    "unregister" {
        Get-FlowNoteTask | Out-Null
        Unregister-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Confirm:$false
        Write-Host "Unregistered $TaskPath$TaskName"
    }
}
