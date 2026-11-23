#!/usr/bin/env bash
# 服务器端自动更新: 拉 main → 有变化就重建镜像并重启。由 systemd timer 定期触发。
# 构建失败时不动线上容器, 保留旧版本(比"半成品上线"安全)。
set -uo pipefail
cd /srv/GooFish-AIMonitor || exit 1

# 与 scripts/deploy.ps1 共用同一把锁, 避免手动部署和自动更新同时构建
exec 9>/tmp/xy-deploy.lock
flock -w 900 9 || { echo "[$(date -Is)] 另一个部署还在跑, 跳过本轮"; exit 0; }

git fetch origin main --quiet || { echo "[$(date -Is)] fetch 失败(网络?)"; exit 1; }
local_head=$(git rev-parse HEAD)
remote_head=$(git rev-parse origin/main)
[ "$local_head" = "$remote_head" ] && exit 0

echo "[$(date -Is)] 发现新提交 ${local_head:0:7} -> ${remote_head:0:7}"
git reset --hard "$remote_head" --quiet || exit 1

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
