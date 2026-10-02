<#
    HowToLiveBetter-Local —— 自动同步的 Windows 计划任务安装脚本

    注册一个计划任务：每天定时 + 每次登录后，调用 WSL 里的同步脚本
    （tools/sync_upstream.py），拉取上游更新并提交/推送到你的 GitHub 仓库。

    为什么走 WSL：这个项目的 git / gh 认证和 Python 环境都在 WSL 里，
    用 wsl.exe 调用可以沿用同一套身份和凭据，不用在 Windows 侧重复配一遍。

    用法（普通 PowerShell 即可，不需要管理员）：
        powershell -ExecutionPolicy Bypass -File tools\install-sync-task.ps1
        powershell -ExecutionPolicy Bypass -File tools\install-sync-task.ps1 -At 09:30
        powershell -ExecutionPolicy Bypass -File tools\install-sync-task.ps1 -NoPush
        powershell -ExecutionPolicy Bypass -File tools\install-sync-task.ps1 -Remove

    注意：本文件必须保存为「UTF-8 with BOM」。Windows PowerShell 5.1 在没有 BOM 时
    会按系统 ANSI 编码读取 .ps1，中文会被拆坏并导致语法错误。

    如果注册失败（比如权限受限），可以用 tools\sync_upstream.py 手动同步，
    或用「任务计划程序」图形界面按下面的「执行」命令自己建一个任务。
#>
[CmdletBinding()]
param(
    [string]$TaskName   = "HowToLiveBetter-AutoSync",
    [string]$Distro     = "Ubuntu-24.04",
    [string]$ProjectDir = "/mnt/d/Projects/HowToLiveBetter-Local",
    [string]$At         = "10:00",
    [switch]$NoPush,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"

if ($Remove) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "已删除计划任务：$TaskName"
    } else {
        Write-Host "没有找到计划任务：$TaskName"
    }
    return
}

# 组装在 WSL 里执行的命令
$syncArgs = if ($NoPush) { "--no-push" } else { "" }
$inner = "cd '$ProjectDir' && mkdir -p logs && python3 tools/sync_upstream.py $syncArgs >> logs/sync.log 2>&1"
$wslArgs = "-d $Distro -- bash -lc `"$inner`""

$action = New-ScheduledTaskAction -Execute "wsl.exe" -Argument $wslArgs

# 两个触发器：每天定时 + 登录后。
# 注意：-AtLogOn 不加 -User 会报 Access is denied（实测），必须显式指定当前用户。
$triggers = @(
    (New-ScheduledTaskTrigger -Daily -At $At),
    (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME)
)

# -StartWhenAvailable：错过的时间点（比如当时关机）恢复后补跑一次
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

try {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers `
        -Settings $settings `
        -Description "拉取 HowToLiveBetter 上游更新并同步到本地仓库（每天 $At 及登录后）" `
        -ErrorAction Stop | Out-Null
} catch {
    Write-Host "注册计划任务失败：$($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    Write-Host "可以改用「任务计划程序」图形界面手动创建，操作如下："
    Write-Host "  常规：使用当前用户，勾选「只在用户登录时运行」"
    Write-Host "  触发器：每天 $At，以及「登录时」"
    Write-Host "  操作：启动程序 wsl.exe"
    Write-Host "  参数：$wslArgs"
    Write-Host ""
    Write-Host "或者不用定时任务，需要时手动跑："
    Write-Host "  wsl -d $Distro -- bash -lc `"cd $ProjectDir && python3 tools/sync_upstream.py`""
    exit 1
}

# 复核确实注册上了，不能只信 Register-ScheduledTask 没报错
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "注册后查不到任务 $TaskName，视为失败。" -ForegroundColor Red
    exit 1
}

Write-Host "已注册计划任务：$TaskName" -ForegroundColor Green
Write-Host "  触发：每天 $At + 每次登录（$env:USERNAME）"
Write-Host "  执行：wsl.exe $wslArgs"
Write-Host "  日志：$ProjectDir/logs/sync.log"
Write-Host ""
Write-Host "立刻试跑一次：  Start-ScheduledTask -TaskName $TaskName"
Write-Host "查看上次结果：  Get-ScheduledTaskInfo -TaskName $TaskName"
Write-Host "手动同步一次：  wsl -d $Distro -- bash -lc `"cd $ProjectDir && python3 tools/sync_upstream.py`""
Write-Host "不再需要：      powershell -ExecutionPolicy Bypass -File tools\install-sync-task.ps1 -Remove"
