# register_bot_task.ps1 — AAABotRestart 예약 작업을 올바른 설정으로 (재)등록한다.
#
# 왜: 이 작업의 설정은 Task Scheduler(기계 상태)에만 있고 repo에 백업이 없어
#     단일 실패점이었다(§29). 기계 재구성/작업 삭제 시 이 스크립트 한 줄로 복구한다.
#
# 사용(관리자 PowerShell, C:\Users\USER\aaa 에서):
#     powershell -ExecutionPolicy Bypass -File .\register_bot_task.ps1          # 등록만
#     powershell -ExecutionPolicy Bypass -File .\register_bot_task.ps1 -Run     # 등록 + 즉시 기동
#
# 기존 동명 작업이 있으면 -Force로 덮어쓴다(멱등).
#
# 박아두는 핵심 설정(근거):
#   - LogonType Interactive          → 인터랙티브 로그온 토큰. Docker named-pipe ACL 요구(§23).
#   - StopOnIdleEnd  = $false        → PC 유휴 해제 시 ~30초 만에 봇을 죽이던 함정(§29 첫째 버그).
#   - RunOnlyIfIdle  = $false        → 유휴 아니어도 실행.
#   - RestartOnIdle  = $false        → 유휴 진입 시 재시작 안 함.
#   - MultipleInstances = Parallel   → /재시작봇(schtasks /run)이 자기를 IgnoreNew로 죽이던 둘째 버그(§29).
#   - ExecutionTimeLimit = 0         → 장수 봇이 기본 3일 한도로 종료되지 않게.
#   - 배터리/유휴 강제종료 트랩 해제  → 침묵 사망 경로 차단.

param(
    [string]$TaskName = "AAABotRestart",
    [string]$RepoDir  = "C:\Users\USER\aaa",
    [string]$Pythonw  = "C:\Python314\pythonw.exe",
    [string]$BotScript = "discord_bot.py",
    [string]$User     = "$env:USERNAME",
    [switch]$Run
)

$ErrorActionPreference = "Stop"

# --- 사전 점검 ---
if (-not (Test-Path $Pythonw))                       { throw "pythonw 없음: $Pythonw" }
if (-not (Test-Path (Join-Path $RepoDir $BotScript))){ throw "봇 스크립트 없음: $(Join-Path $RepoDir $BotScript)" }

# --- 액션: 작업 인스턴스 = 봇 프로세스(수명 일치) ---
$action = New-ScheduledTaskAction `
    -Execute $Pythonw `
    -Argument $BotScript `
    -WorkingDirectory $RepoDir

# --- 트리거: 로그온 시 자동 기동(재부팅 복구). schtasks /run 온디맨드도 그대로 동작 ---
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $User

# --- 주체: 인터랙티브 로그온 토큰(§23 — Docker 권한) ---
$principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited

# --- 설정: §29 수정 + 침묵 사망 트랩 해제 ---
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances Parallel `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

# New-ScheduledTaskSettingsSet 가 직접 노출 안 하는 idle 항목은 객체에서 직접 박는다(§29 핵심).
$settings.IdleSettings.StopOnIdleEnd = $false
$settings.IdleSettings.RestartOnIdle = $false
$settings.RunOnlyIfIdle              = $false

# --- 등록(멱등: 동명 작업 덮어쓰기) ---
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Force | Out-Null

Write-Host "[OK] '$TaskName' 등록 완료." -ForegroundColor Green

# --- 검증 출력: 박힌 값이 맞는지 즉시 대조 ---
$t = Get-ScheduledTask -TaskName $TaskName
[pscustomobject]@{
    TaskName          = $t.TaskName
    Execute           = $t.Actions[0].Execute
    Argument          = $t.Actions[0].Arguments
    WorkingDirectory  = $t.Actions[0].WorkingDirectory
    LogonType         = $t.Principal.LogonType
    UserId            = $t.Principal.UserId
    MultipleInstances = $t.Settings.MultipleInstances
    StopOnIdleEnd     = $t.Settings.IdleSettings.StopOnIdleEnd
    RestartOnIdle     = $t.Settings.IdleSettings.RestartOnIdle
    RunOnlyIfIdle     = $t.Settings.RunOnlyIfIdle
    ExecutionTimeLimit= $t.Settings.ExecutionTimeLimit
} | Format-List

# --- 선택: 즉시 기동 ---
if ($Run) {
    schtasks /run /tn $TaskName | Out-Null
    Write-Host "[OK] schtasks /run /tn $TaskName 트리거 — Docker 권한 있는 봇 기동." -ForegroundColor Green
}
