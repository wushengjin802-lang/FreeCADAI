#!/usr/bin/env pwsh
<#
.SYNOPSIS
  开发阶段快速部署——仅同步代码到服务器容器，跳过 Docker 镜像构建。
  适合只改 Python / 前端代码时的快速迭代。
  完整部署（含镜像构建）请用 sync_and_deploy.ps1。
#>
$ErrorActionPreference = "Stop"

$Server = "root@119.29.16.170"
$RemoteDir = "/home/app/freecadai"

# ===== 配置区 =====
# 使用密码登录（研发阶段方便），如果已配 SSH 免密可留空
$Password = "HONGSHAN@2026!&"
# ==================

$HasKey = $null -ne (Get-ChildItem "$env:USERPROFILE\.ssh\*" -ErrorAction SilentlyContinue)

function ExecRemote($Cmd) {
  if ($Password -and -not $HasKey) {
    # 用 Python paramiko 执行远程命令（Windows 原生无需额外工具）
    python -c @"
import paramiko, sys
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('119.29.16.170', 22, 'root', '$Password', timeout=10)
s, o, e = c.exec_command('$Cmd'.replace('\`','\\"'), timeout=120)
print(o.read().decode(errors='replace'))
err = e.read().decode(errors='replace')
if err: print('STDERR:', err, file=sys.stderr)
c.close()
"@
  } else {
    ssh $Server $Cmd
  }
}

function SyncToServer {
  Write-Host "=== Syncing changed code to server ===" -ForegroundColor Green
  $items = @(
    "docker-compose.prod.yml",
    "server/",
    "freecad_ai/",
    "scripts/",
    "web/src/",
    "web/package.json",
    "web/package-lock.json",
    "web/tsconfig.json",
    "web/next.config.mjs",
    "web/Dockerfile",
    "web/public/",
    "Init.py", "InitGui.py", "package.xml"
  )

  # Use Python paramiko SFTP to sync
  python -c @"
import paramiko, os, sys

host, pw = '119.29.16.170', '$Password'
local_base = r'$PWD'.replace('\\', '/')
remote_base = '/home/app/freecadai'

items = [
$(
  $items | ForEach-Object { "    '" + $_.Replace("'", "\'") + "'," }
)
]

exclude = {'node_modules', '.git', '__pycache__', '.next', 'dist'}

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(host, 22, 'root', pw, timeout=10)
sftp = c.open_sftp()

def ensure_dir(path):
    try: sftp.stat(path)
    except:
        parts = path.split('/')
        for i in range(1, len(parts)+1):
            p = '/'.join(parts[:i])
            if p:
                try: sftp.stat(p)
                except: sftp.mkdir(p)

total = 0
for item in items:
    local = local_base + '/' + item
    remote = remote_base + '/' + item
    if remote.endswith('/'): remote = remote[:-1]
    if os.path.isdir(local):
        for root, dirs, files in os.walk(local):
            dirs[:] = [d for d in dirs if d not in exclude]
            rel = os.path.relpath(root, local)
            target = remote if rel == '.' else remote + '/' + rel.replace('\\', '/')
            for f in files:
                if f.endswith('.pyc'): continue
                lf = os.path.join(root, f)
                rf = target + '/' + f
                ensure_dir(target)
                sftp.put(lf, rf)
                total += 1
    elif os.path.isfile(local):
        ensure_dir(os.path.dirname(remote))
        sftp.put(local, remote)
        total += 1

sftp.close(); c.close()
print(f'Synced {total} files')
"@
}

function RestartContainers {
  param([string[]]$Services)
  Write-Host "=== Restarting: $($Services -join ', ') ===" -ForegroundColor Green

  foreach ($svc in $Services) {
    ExecRemote("docker cp $RemoteDir/server/. freecadai-${svc}:/app/server/ 2>&1")
    ExecRemote("docker cp $RemoteDir/freecad_ai/. freecadai-${svc}:/app/freecad_ai/ 2>&1")
  }

  ExecRemote("docker restart $($Services | ForEach-Object { "freecadai-$_" }) 2>&1")
  Write-Host "Done." -ForegroundColor Green
}

# ===== 主流程 =====
Write-Host "Fast dev deploy — no image build" -ForegroundColor Cyan
Write-Host ""

# 1. 同步代码
SyncToServer

# 2. 复制到容器并重启
RestartContainers -Services @("api", "worker")

# 3. 检查状态
Start-Sleep -Seconds 2
Write-Host ""
Write-Host "=== Health Check ===" -ForegroundColor Green
python -c @"
import paramiko
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('119.29.16.170', 22, 'root', '$Password', timeout=10)
s, o, e = c.exec_command("docker ps --filter name=freecadai --format 'table {{.Names}}\t{{.Status}}' && curl -s http://localhost:8000/health", timeout=10)
print(o.read().decode(errors='replace'))
c.close()
"@
