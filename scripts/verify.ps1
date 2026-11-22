# 本地验证: pytest + pyright(+ 可选前端构建), 只输出一行
param([switch]$Frontend)
$ErrorActionPreference = 'Continue'

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$log = Join-Path $root 'data\verify.log'
Set-Content $log "verify $(Get-Date -Format o)"

Push-Location $root
try {
  $tests = & $python -m pytest -q 2>&1
  $tests | Out-File $log -Append
  $summary = ($tests | Where-Object { $_ -match '\d+ (passed|failed|error)' } | Select-Object -Last 1)
  if ("$tests" -match '(\d+) failed|(\d+) error') {
    $why = ($tests | Where-Object { $_ -match '^FAILED|^ERROR|^E ' } | Select-Object -First 1)
    Write-Output "verify: 测试失败 - $why（详见 data/verify.log）"
    exit 1
  }
  $passed = if ("$summary" -match '(\d+) passed') { $Matches[1] } else { '?' }

  $py = & npx --yes pyright@latest --pythonpath $python src tests scripts 2>&1
  $py | Out-File $log -Append
  $pyLine = ($py | Where-Object { $_ -match 'errors?, \d+ warnings?' } | Select-Object -Last 1)
  if ("$pyLine" -notmatch '^0 errors') {
    $first = ($py | Where-Object { $_ -match '\s-\s(error|warning):' } | Select-Object -First 1)
    Write-Output "verify: pyright 有问题 - $first（详见 data/verify.log）"
    exit 1
  }

  $front = 'skip'
  if ($Frontend) {
    $build = & npm --prefix (Join-Path $root 'frontend') run build 2>&1
    $build | Out-File $log -Append
    if ("$build" -notmatch 'built in') {
      $why = ($build | Where-Object { $_ -match 'error|Error' } | Select-Object -First 1)
      Write-Output "verify: 前端构建失败 - $why（详见 data/verify.log）"
      exit 1
    }
    $front = 'build ok'
  }

  Write-Output "verify: $passed passed | pyright 0 errors | $front"
}
finally {
  Pop-Location
}
