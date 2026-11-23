# 发布上线: 打包 → scp → 服务器 reset → 构建 → 重启 → 探活
# 只输出一行结果; 详细过程写 data/deploy.log
param([switch]$NoBuild, [switch]$Fast)
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$log = Join-Path $root 'data\deploy.log'
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
  Write-Output 'deploy: 缺少 data/deploy.env 的 XY_DEPLOY_HOST / XY_SSH_KEY'
  exit 2
}

$sshArgs = @('-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-i', $Key)
$started = Get-Date
function Fail($message) {
  Add-Content $log "FAIL $(Get-Date -Format o) $message"
  Write-Output "deploy: 失败 - $message（详见 data/deploy.log）"
  exit 1
}

Set-Content $log "deploy $(Get-Date -Format o) on $Server"
Push-Location $root
try {
  & git bundle create 'data\xy-main.bundle' main *>> $log
  if ($LASTEXITCODE -ne 0) { Fail 'git bundle 失败' }
  & scp @sshArgs -q 'data\xy-main.bundle' "${Server}:/tmp/xy-main.bundle" *>> $log
  if ($LASTEXITCODE -ne 0) { Fail 'scp 失败(网络或密钥)' }

  $sync = & ssh @sshArgs $Server 'cd /srv/GooFish-AIMonitor && git fetch /tmp/xy-main.bundle main -q && git reset --hard FETCH_HEAD -q && git rev-parse --short HEAD' 2>&1
  if ($LASTEXITCODE -ne 0) { Fail "服务器同步失败: $($sync | Select-Object -Last 1)" }
  $sha = ($sync | Select-Object -Last 1).Trim()

  $built = 'skip'
  if (-not $NoBuild) {
    $buildTime = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    $build = & ssh @sshArgs $Server "cd /srv/GooFish-AIMonitor && APP_VERSION=$sha APP_BUILD_TIME=$buildTime flock -w 900 /tmp/xy-deploy.lock docker compose build > /tmp/xy-build.log 2>&1 && echo BUILD_OK || (tail -3 /tmp/xy-build.log; echo BUILD_FAIL)" 2>&1
    if ("$build" -notmatch 'BUILD_OK') { Fail "镜像构建失败: $($build | Select-Object -Last 1)" }
    $built = 'build ok'
  }

  $up = & ssh @sshArgs $Server 'cd /srv/GooFish-AIMonitor && flock -w 900 /tmp/xy-deploy.lock docker compose up -d --no-build 2>&1 | tail -1' 2>&1
  if ($LASTEXITCODE -ne 0) { Fail '容器重启失败' }
  Start-Sleep -Seconds 6
  $code = (& ssh @sshArgs $Server 'curl -sk -o /dev/null -w "%{http_code}" https://127.0.0.1:8454/') 2>&1
  if ("$code".Trim() -ne '200') { Fail "探活失败 caddy=$($code.ToString().Trim())" }

  $cost = [int]((Get-Date) - $started).TotalSeconds
  Write-Output "deploy: $sha | $built | caddy 200 | ${cost}s"
}
finally {
  Pop-Location
}
