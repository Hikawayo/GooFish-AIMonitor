# 开发进展与接力

> 本文件是当前进度快照。需求与验收标准见 [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md)。接手先读 [AGENTS.md](../AGENTS.md)。

## 当前状态

- **更新时间**：2026-11-22
- **阶段**：阶段二的多人访问、监控文件夹、公开/私密隔离、推荐/收藏筛选已上线。本轮上线人工审核模式与单商品价格走势，主题重点色改为 `#00AABB`。
- **线上入口**：Caddy `8454` 继续接入 `8445` 统一登录。应用 `goofish` 已允许 SSO 成员，Caddy 把统一登录签发的应用专用票据传给 FastAPI。匿名请求（含 `/`）返回 `401`。容器仍绑定 `127.0.0.1:18080`。
- **数据归属**：原管理员沿用既有 SQLite、闲鱼账户和模型配置；服务器保留了 1 条监控、28 条待审、14 条收藏。其他成员的 SQLite、扫码状态、Key、定时任务和收藏按账号隔离。Key 只写入自己的配置，成员接口采用管理员配置的 HTTPS 地址范围，SMTP 服务器设置仍限管理员。
- **文件夹与公开**：条件可单独作为文件夹，也可选择自建文件夹。推荐、收藏可按组和公开/私密筛选。公开目录只转发当前公开条件里已匹配的商品数据，成员可在本站收藏，收藏记录私密。已有条件须由所有者主动公开。
- **人工审核（本轮）**：设置里关掉「AI 审核」即进入人工审核模式——搜索照常跑，候选以「未审」进入待审队列，由本人逐个通过或忽略，不需要 AI API Key（仍需自己的闲鱼登录态）。人工裁决写回该条件的匹配记录，公开行情与价格观测据此判断「已确认匹配」；AI 模式行为不变，批准/忽略不改动 AI 裁决。
- **价格走势（本轮）**：推荐、收藏、公开卡片都有「价格记录」，弹窗给出最近挂牌价、记录最低、走势图和逐条观测时间，不必为看几天来的变化先跳去闲鱼商品页。
- **主题（本轮）**：Linear 与 Stripe 两套皮肤的重点色由紫色改为 `#00AABB`，前景色与柔和底色同步；Vercel / Supabase / Apple 未改。
- **改动位置**：`review.py`（`skipped` 与 `REVIEW_MANUAL`）、`service.py`（`record_manual_verdict`）、`web/runtime.py`（`can_search` / `search_block_reason`）、`web/app.py`（运行入口与人工裁决）、`web/runner.py`，前端 `components/PriceHistory.jsx`、`sections/Recommendations.jsx`、`sections/Settings.jsx`、`App.jsx`、`styles.css`，另有上一轮未入库的 `web/sharing.py`、`components/Folders.jsx`、`components/ItemSort.jsx`。
- **验证**：111 项 pytest、Pyright 0 error、前端构建通过；本地浏览器核对两套皮肤 `--acc` 为 `#00aabb`、运行按钮底色 `rgb(0,170,187)` 配深色字、人工模式下待审列表无 AI 筛选项、价格弹窗 5 条观测加走势图。服务器已用 `git bundle` 同步到 `d66fbab` 并重建镜像，容器重建后 Caddy `8454` 返回 `200`，容器内静态产物含 `00aabb` 与「价格记录」，现有库数据不变。重建前数据库备份 `/srv/backups/xianyu-20261122-003552.db`。
- **未验证**：没有用真实 SSO 会话在浏览器里打开线上页面，也没有触发真实抓取；成员侧人工审核的线上使用仍需同事实际跑一轮。
- **GitHub**：`github.com:443` 期间中断过，恢复后已推送；当前 `main` 与 `origin/main` 同步（`94354d7`）。服务器工作副本用 `git bundle` 同步，未直接走 GitHub。
- **既有能力**：逐条 AI 审核、提示词、搜索和 HTTPS 均已上线。`libatomic1` 构建补丁已进入 `Dockerfile`。

## 2026-11-22 人工审核与价格走势

- **人工审核模式**：`review.ReviewVerdict` 增加 `skipped`；关闭 AI 审核时不再用 `ok=True` 假装通过，改为不留裁决、只进待审队列。`runtime.can_search` 在有登录态时不再强制要求 API Key，`search_block_reason()` 区分「先扫码登录」和「配 Key 或改人工审核」两种提示。`service.record_manual_verdict` 在人工模式下把通过/忽略写入 `WatchMatch`，公开页与 `PublishedPrice` 才认这份确认；AI 模式下该函数直接返回，不动 AI 裁决。
- **走势查看**：`PriceHistory.jsx` 从 `/api/items/{id}/prices` 或公开接口取观测，画线并列出逐条时间与价格；本地收藏由 `refresh_local_favorites` 每轮复检累积观测点，因此几天后打开就有曲线。
- **验收**：种两条测试商品到本地冒烟库（4 个观测点跨 5 天）验证弹窗；线上容器用 `docker exec` 核对代码与产物，未触发真实采集。

## 下一步

1. 把确实要分享的条件由所有者切为公开，用同事的 SSO 会话查看，并核对同组结果。
2. 用成员自己的闲鱼账号（人工审核模式，不配 Key）完整跑一轮：搜索、待审队列、通过后出现在收藏、公开组行情可见。
3. 继续阶段二的目标价提醒及实际告警，之后再做未收藏商品复查和按组的多商品走势。
4. `docs/screenshots/` 里的皮肤截图仍是旧紫色重点色，改版后未重拍。
