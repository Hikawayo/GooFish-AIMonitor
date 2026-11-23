#!/usr/bin/env bash
# 服务器端自动更新: 拉 main → 有变化就重建镜像并重启。由 systemd timer 定期触发。
# 构建失败时不动线上容器, 保留旧版本(比"半成品上线"安全)。
set -uo pipefail
cd /srv/GooFish-AIMonitor || exit 1

# 可选本地配置(不进 git): 支持 HTTPS_PROXY / HTTP_PROXY / GIT_FETCH_URL(空格分隔的备用源)
if [ -f data/autoupdate.env ]; then
  set -a
  # shellcheck disable=SC1091
  . data/autoupdate.env
  set +a
fi

# 与 scripts/deploy.ps1 共用同一把锁, 避免手动部署和自动更新同时构建
exec 9>/tmp/xy-deploy.lock
flock -w 900 9 || { echo "[$(date -Is)] 另一个部署还在跑, 跳过本轮"; exit 0; }

fetch_once() {
  local target="$1"
  local refspec="$2"
  timeout 25 git -c http.version=HTTP/1.1 \
                 -c http.lowSpeedLimit=1000 \
                 -c http.lowSpeedTime=15 \
                 fetch "$target" "$refspec" --quiet
}

fetch_ok=0
if [ -n "${GIT_FETCH_URL:-}" ]; then
  # 有备用源时: 直连试 1 次(最多 25s), 失败即按顺序切备用源
  if fetch_once origin main; then
    fetch_ok=1
  else
    for mirror in $GIT_FETCH_URL; do
      if fetch_once "$mirror" "refs/heads/main:refs/remotes/origin/main"; then
        fetch_ok=1
        break
      fi
    done
  fi
else
  for i in 1 2 3; do
    if fetch_once origin main; then
      fetch_ok=1
      break
    fi
    [ "$i" -lt 3 ] && sleep 3
  done
fi

if [ "$fetch_ok" -ne 1 ]; then
  echo "[$(date -Is)] fetch 失败(网络?)"
  exit 1
fi

local_head=$(git rev-parse HEAD)
remote_head=$(git rev-parse origin/main)
[ "$local_head" = "$remote_head" ] && exit 0

echo "[$(date -Is)] 发现新提交 ${local_head:0:7} -> ${remote_head:0:7}"
git reset --hard "$remote_head" --quiet || exit 1

export APP_VERSION="${remote_head:0:7}"
export APP_BUILD_TIME
APP_BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)

if ! docker compose build > /tmp/xy-autobuild.log 2>&1; then
  echo "[$(date -Is)] 构建失败, 保留当前版本"
  tail -5 /tmp/xy-autobuild.log
  exit 1
fi

if ! docker compose up -d --no-build > /tmp/xy-autoup.log 2>&1; then
  echo "[$(date -Is)] 重启失败"
  tail -5 /tmp/xy-autoup.log
  exit 1
fi

code=$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:8454/ || echo 000)
echo "[$(date -Is)] 已上线 ${remote_head:0:7} caddy=$code"
