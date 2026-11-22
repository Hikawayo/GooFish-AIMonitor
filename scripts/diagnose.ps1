# 线上诊断: 容器状态 + 最近观测/事件 + 最近错误日志(最多 8 行)
param([int]$Minutes = 120)
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root 'data\deploy.env'
$conf = @{}
if (Test-Path $envFile) {
  foreach ($line in Get-Content $envFile) {
    if ($line -match '^\s*([A-Z_]+)\s*=\s*(.+)$') { $conf[$Matches[1]] = $Matches[2].Trim() }
  }
}
$Server = if ($env:XY_DEPLOY_HOST) { $env:XY_DEPLOY_HOST } else { $conf['XY_DEPLOY_HOST'] }
$Key = if ($env:XY_SSH_KEY) { $env:XY_SSH_KEY } else { $conf['XY_SSH_KEY'] }
if (-not $Server -or -not $Key) {
  Write-Output 'diagnose: 缺少 data/deploy.env 的 XY_DEPLOY_HOST / XY_SSH_KEY'
  exit 2
}

# 整条远程命令写成一行: 多行脚本经 PowerShell 管道会带上 CRLF, 远端会报 '4\r'
$py = "import sqlite3;c=sqlite3.connect('/app/data/xianyu.db');f=lambda s:c.execute(s).fetchone();" +
      "print('last_obs',f('select max(observed_at) from price_history')[0]);" +
      "print('items',f('select count(*) from items')[0]);" +
      "print('events',c.execute('select type,created_at from events order by id desc limit 2').fetchall())"
$remote = "cd /srv/GooFish-AIMonitor; " +
  "docker compose ps --format 'container: {{.Name}} {{.Status}}' | head -n 1; " +
  "docker exec xianyu-console python -c `"$py`"; " +
  "echo '--- 最近错误 ---'; " +
  "docker logs --since ${Minutes}m xianyu-console 2>&1 | grep -iE 'error|exception|timeout|超时|失败' | tail -n 4"

& ssh -o BatchMode=yes -o IdentitiesOnly=yes -i $Key $Server $remote 2>&1 |
  Where-Object { $_ -notmatch '^\s*$' } |
  Select-Object -First 8
