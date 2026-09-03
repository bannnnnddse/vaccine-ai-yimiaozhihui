#requires -Version 5.1
<#
dev.ps1 - 挑战杯项目本地开发一键启动脚本

用法:
    .\dev.ps1

在同一终端并行启动 Backend (uvicorn) 与 Frontend (vite),
按 Ctrl+C 即可同时停止两个服务。
#>

$ErrorActionPreference = 'Stop'

$Root        = $PSScriptRoot
$BackendDir  = Join-Path $Root 'backend'
$FrontendDir = Join-Path $Root 'frontend'
$Uvicorn     = Join-Path $BackendDir '.venv\Scripts\uvicorn.exe'
$BackendApp  = Join-Path $BackendDir 'app\main.py'

# ---------- 环境检查 ----------
if (-not (Test-Path -LiteralPath $BackendDir)) {
    Write-Host "错误: 未找到 backend 目录: $BackendDir" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path -LiteralPath $FrontendDir)) {
    Write-Host "错误: 未找到 frontend 目录: $FrontendDir" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path -LiteralPath $Uvicorn)) {
    Write-Host "错误: 未找到后端虚拟环境: $Uvicorn" -ForegroundColor Red
    Write-Host '请先在 backend 目录创建虚拟环境并安装依赖:' -ForegroundColor Yellow
    Write-Host '  cd backend'
    Write-Host '  python -m venv .venv'
    Write-Host '  .\.venv\Scripts\python.exe -m pip install -e ".[dev]"'
    exit 1
}
if (-not (Test-Path -LiteralPath $BackendApp)) {
    Write-Host "错误: 未找到后端入口: $BackendApp" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $FrontendDir 'package.json'))) {
    Write-Host "错误: 未找到前端 package.json: $(Join-Path $FrontendDir 'package.json')" -ForegroundColor Red
    exit 1
}
$Pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
if (-not $Pnpm) {
    Write-Host '错误: 未找到 pnpm 命令, 请先安装 pnpm (corepack enable 或 https://pnpm.io/installation)' -ForegroundColor Red
    exit 1
}

# 端口占用提示(不阻断启动)
foreach ($port in 8000, 5173) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        Write-Warning "端口 $port 已被占用, 可能已有服务在运行"
    }
}

# ---------- 并行启动前后端 ----------
Write-Host ''
Write-Host '==> 正在启动 Backend  (uvicorn  http://127.0.0.1:8000)' -ForegroundColor Cyan
$backend = Start-Process -FilePath $Uvicorn `
    -ArgumentList 'app.main:app', '--host', '127.0.0.1', '--port', '8000' `
    -WorkingDirectory $BackendDir -NoNewWindow -PassThru

Write-Host '==> 正在启动 Frontend (vite    http://localhost:5173)' -ForegroundColor Cyan
$frontend = Start-Process -FilePath $env:ComSpec `
    -ArgumentList '/d', '/s', '/c', 'pnpm dev' `
    -WorkingDirectory $FrontendDir -NoNewWindow -PassThru

Write-Host ''
Write-Host '两个服务已并行启动:'
Write-Host '  Backend  API : http://127.0.0.1:8000   (接口文档 http://127.0.0.1:8000/docs)'
Write-Host '  Frontend 页面: http://localhost:5173'
Write-Host '按 Ctrl+C 可同时停止前后端服务。' -ForegroundColor Green
Write-Host ''

# ---------- 监控: 任一服务退出则停止另一个, Ctrl+C 时全部停止 ----------
$exitCode = 0
try {
    while ($true) {
        Start-Sleep -Seconds 1
        $backendAlive  = [bool](Get-Process -Id $backend.Id  -ErrorAction SilentlyContinue)
        $frontendAlive = [bool](Get-Process -Id $frontend.Id -ErrorAction SilentlyContinue)
        if (-not $backendAlive -and -not $frontendAlive) { break }
        if (-not $backendAlive) {
            Write-Warning 'Backend 已退出, 正在停止 Frontend ...'
            $exitCode = 1
            break
        }
        if (-not $frontendAlive) {
            Write-Warning 'Frontend 已退出, 正在停止 Backend ...'
            $exitCode = 1
            break
        }
    }
}
finally {
    # 收尾: 优先等待服务自行退出(Ctrl+C 场景), 残留进程再强制清理
    $remaining = @($backend, $frontend) | Where-Object {
        Get-Process -Id $_.Id -ErrorAction SilentlyContinue
    }
    if ($remaining) {
        if ($remaining.Count -eq 2) { Start-Sleep -Seconds 5 }
        foreach ($p in $remaining) {
            if (-not (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)) { continue }
            # 先按进程树强制清理, 失败则退回 Stop-Process
            try { $null = & taskkill /PID $p.Id /T /F 2>$null } catch { }
            if (Get-Process -Id $p.Id -ErrorAction SilentlyContinue) {
                Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

if ($exitCode -ne 0) {
    Write-Host '开发服务已停止(有服务异常退出)。' -ForegroundColor Yellow
}
exit $exitCode
