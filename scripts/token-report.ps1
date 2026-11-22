# 本会话用量报告: 只输出几行, 用来对比优化前后
param([string]$Session = '')
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $PSScriptRoot 'token_report.js'

$node = (Get-Command node -ErrorAction SilentlyContinue).Source
if (-not $node) {
  $candidate = Get-ChildItem "$env:USERPROFILE\.dsh\dsh-runtimes" -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { Join-Path $_.FullName 'dependencies\node\bin\node.exe' } |
    Where-Object { Test-Path $_ } | Select-Object -First 1
  $node = $candidate
}
if (-not $node) { Write-Output 'token-report: 找不到 node'; exit 2 }

if ($Session) { & $node $script $Session } else { & $node $script }
