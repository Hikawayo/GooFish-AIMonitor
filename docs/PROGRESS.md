# 开发进展与接力

> 本文件是当前进度快照。需求与验收标准见 [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md)。接手先读 [AGENTS.md](../AGENTS.md) 和本文件。

## 当前状态

- **更新时间**：2026-11-21
- **阶段**：阶段一，腾讯云部署已完成，接下来验收闲鱼账号和真实搜索。
- **运行位置**：服务器 `/srv/GooFish-AIMonitor`，应用基于 `3a0071a`。Compose 容器为 `xianyu-console`，宿主机绑定 `127.0.0.1:18080`，通过 SSH 本地转发访问管理页。
- **端口检查**：Caddy 当前最高监听到 `8453`，从部署电脑发起 HTTPS 请求得到 `302`（跳过了证书验证）。`8454` 无本机监听，公网连接超时。公网直连 `18080` 也超时。
- **部署差异**：服务器直连 Docker Hub 超时，构建时通过 `PYTHON_IMAGE=mirror.ccs.tencentyun.com/library/python:3.12-slim` 和 `NODE_IMAGE=mirror.ccs.tencentyun.com/library/node:20-slim` 两个构建参数使用腾讯云镜像。基础镜像缺少 Playwright 驱动所需的 `libatomic.so.1`，已在服务器工作副本的 `Dockerfile` 中于 `WORKDIR /app` 前安装 `libatomic1`。这是服务器上的未提交改动，更新代码时应保留。构建日志位于 `/var/log/goofish-aimonitor-build.log`。
- **服务器已验证**：Compose 启动成功，首页、前端 JS、`/api/status` 通过服务器回环和 Windows 的 SSH 隧道访问正常。容器内无头 Chromium 可以启动。通过管理 API 写入一条停用监控，重启后仍能读到，测试记录已清除。SQLite 在 `./data/xianyu.db`，数据目录已挂载。
- **本地检查**：前端构建通过，Windows Python 3.12 下 pytest 共 106 项通过。CLI Pyright 报 9 条既有类型问题，位于 `service.py` 和三份测试文件。这一轮仅部署，没有修改业务源码。
- **尚未验证**：闲鱼扫码登录、登录后的真实搜索、DeepSeek 审核和邮件告警。部署时登录状态为 `idle`，没有已保存的登录态。

## 下一步

1. 从管理员电脑建立 SSH 转发（本机 `127.0.0.1:18080` → 服务器 `127.0.0.1:18080`），在浏览器打开管理页并用闲鱼 App 扫码。
2. 登录后先用一组关键词验证返回标题、价格和商品链接，再按阶段一验收 DeepSeek 审核和告警。账号状态与密钥只保留在服务器受保护配置中。
3. 本阶段保留管理后台的回环绑定。团队共享入口按阶段二的只读权限设计实施。
