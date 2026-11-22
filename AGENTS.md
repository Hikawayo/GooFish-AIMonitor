# AGENTS.md — 给 AI 协作者的工程指南

海鲜价格监控：本地运行的闲鱼选品(R1) + 降价监控(R2) Web 控制台。Python 3.12+ / Playwright(sync) / SQLAlchemy 2 / FastAPI + APScheduler / React + Vite。面向人类的说明见 [`README.md`](README.md)。

## 本 Fork 的开发原则

1. **Avoid unnecessary secondary labels and descriptions. Let the layout do the explaining.** 界面优先通过布局和信息层级自解释，避免多余二级标签、状态徽章和说明文字。
2. **不写只是为了防止被质疑的代码。** 不做假设性过度设计、冗余兜底或无真实需求的复杂抽象。
3. **不做只是为了防止被质疑的测试。** 测试真实关键行为和已发生的缺陷，不为覆盖率或形式上的完整性增加测试；数据正确性、访问控制等必要验证仍要做。
4. **先可用，再改进。** 保留现有搜索、DeepSeek兼容审核、SQLite、Web 功能，以 [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md) 的三阶段计划实施；Live 只是首个监控场景，架构应复用于普通商品。
5. **可共享，按所有者隔离。** 复用服务器 SSO。监控默认私密，公开监控的结果可供获准使用本站的 SSO 用户只读查看；搜索、修改及收藏按用户身份授权。

## 多用户开发边界

- 在服务端校验现有 SSO 提供的身份，并用稳定用户 ID 关联所有权。公开只开放必要的行情字段，限制作用于详情、列表、搜索、计数、事件和历史。界面筛选不能作为权限检查。
- 搜索、收藏、AI 审核与通知必须使用任务所有者的设置。每用户隔离闲鱼登录态、API Key、任务状态和个人收藏。公共读者无需提供闲鱼账号或 API Key。
- 条件与结果的关联使用稳定 ID。同一商品可归入多个监控组，审核与共享范围由各组独立决定，个人收藏与忽略状态按用户保存。
- 旧数据迁移至原管理员账户，默认私密。双账号读写和凭据隔离验证通过前，保留现有管理员入口的服务端限制。实现顺序见开发计划。

### 已部署的隔离方式

- `web/runtime.py` 校验由统一登录签发的闲鱼专用票据，Caddy 验证登录后才转发票据。原管理员沿用旧数据目录，其他账号使用独立 SQLite 与浏览器状态目录。每个库各有自己的应用配置。
- `WatchFolder` 与 `WatchMatch` 保存文件夹和按稳定条件 ID 的结果关系。`web/sharing.py` 只投影公开条件的已匹配行情。启用共享入口后仍禁止匿名请求。
- 成员模型地址由管理员配置允许范围，每个成员自行配置 Key。成员不能借用管理员环境变量里的凭据或修改采集与 SMTP 的服务器地址。

## 站内收藏和公开商品

- Web 推荐、公开页的「站内收藏」只记录在当前用户库里。既有闲鱼收藏只读同步；任何新增 Web 收藏按钮都不得隐式操作闲鱼账号。
- 定时复检可使用已登录浏览器打开规范商品详情链接，按到期待查队列和数量上限轮转。明确成功才更新价格；超时、风控及未知响应保留原价，明确失效才更新状态。
- 公开列表排除组内不匹配、忽略、静音和失效商品。允许展示挂牌封面、公开卖家昵称和发布时间，个人配置、审核理由仍不进入共享字段。

## AI 接力协议（每次开发都执行）

**唯一进度入口**：[docs/PROGRESS.md](docs/PROGRESS.md)。需求与阶段划分见 [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md)。

1. **接手先读**：本文件 → `docs/PROGRESS.md` → 当前阶段对应计划。再检查 `git status` 和最新提交，按进度中的「下一步」有针对性地读源码；不要重新遍历整个项目。
2. **开发随时记**：任务开始时更新当前任务；有实质改动、决定、阻塞或验证结果时及时更新进度。记具体文件/关键函数、成功与未验证的区别，不写流水账。
3. **结束必须交接**：完成一个可运行节点、准备换 AI、额度将尽或结束本轮开发前，将「已完成、改动位置、验证结果、阻塞、下一步第一件事」更新进度并提交 GitHub。即使任务没做完，也要准确留下断点。
4. **计划和进度分工**：新需求、范围、验收标准写 `DEVELOPMENT_PLAN.md`；实时状态写 `PROGRESS.md`；Git 提交记录承载详细历史。不重复维护多个状态文档。
5. **提交权限**：用户已明确授权持续维护和提交开发进度文档；功能代码仍按当前任务授权范围执行和提交。不得写入账号Cookie、API Key、私有服务器凭据。
6. **以事实为准**：GitHub已提交不等于服务器已部署、存在代码不等于线上功能已验证；所有无法复现或未检查的结果明确标注。

## 上下文纪律（省 token 的硬规则）

会话成本 ≈ **模型调用次数 × 平均上下文**，两条都要压。实测本仓库一次 33 轮的会话：1095 次调用、平均每次携带 400k token、累计约 439M —— 其中 `read` 占了工具输出的 50%。规则：

1. **大输出一律落盘**：超过约 30 行的输出写 `data/<用途>.log`，回复里只留一行结论。`deploy` / `verify` / `diagnose` 三个脚本已经是这个形状，优先用它们。不把 pytest、docker build、完整日志贴进回复。
2. **grep 先于 read**：先 `grep` 定位，再用 `read` 的 `offset`/`limit` 取 40–120 行。整篇读 300 行以上的文件是最大的上下文污染源。
3. **大日志交给子代理**：要从长日志/大文件里找结论时用 `subagent`，只让它回结论，原始文本不进主线。
4. **批量命令**：同一件事的多步合成一次 `pwsh`（`;` 串联 + `Select-Object -Last N`），不要一步一次调用——每次调用都要重发整个上下文。
5. **节点处压缩**：每完成一个可交付节点（已提交、已部署、PROGRESS 已更新）就提示用户执行 `/compact`；换天或换主题另开会话，靠 `docs/PROGRESS.md` 交接。
6. **量一下再改**：`pwsh -File scripts/token-report.ps1` 输出 6 行（轮次 / 调用次数 / 累计输入 / 输出构成 / 工具输出占比），优化前后各跑一次对比。

## 黄金规则(先读这条)

1. **内置(inline)Pyright 在本仓库是坏的**，会报不可能的错(`import time` 无法解析、`X | None` 操作符不支持、`Mapped[...]` 参数错误等)。**不要信任内置诊断**。权威检查只用：
   ```bash
   npx --yes pyright@latest --pythonpath /opt/miniconda3/bin/python src tests scripts
   /opt/miniconda3/bin/python -m pytest -q
   ```
2. **绝不把隐私/密钥写进仓库**：邮箱、SMTP 密码、LLM Token、内网接口地址、登录态——全部只能来自系统环境变量或 gitignored 的 `data/secret.env`。内网/私有模型代理等地址**只配在 `data/secret.env`**，代码里默认值必须是通用占位(`https://api.openai.com/v1`)。
3. **没有任何写死的业务配置**：可调项走 `config.py` 默认 ← `AppConfig`(DB) ← 设置页 三层。新增配置项要三层都过。
4. **不要主动 `git commit`**，除非用户明确要求。
5. **默认中文回答**；代码标识符/库名/报错保留英文。

## 验证命令(完成前必跑)

```powershell
pwsh -File scripts/verify.ps1              # pytest + pyright, 只回一行
pwsh -File scripts/verify.ps1 -Frontend    # 再加前端构建
```

三个固定入口(也是 skill: `verify` / `deploy` / `diagnose`)。它们的约定是**只输出一行**，详细过程写 `data/*.log`；回复里贴那一行就够，不要整段贴输出。

```bash
# 等价的手工命令(Windows 上路径换成 .venv\Scripts\python.exe)
.venv/Scripts/python.exe -m pytest -q
npx --yes pyright@latest --pythonpath .venv/Scripts/python.exe src tests scripts
cd frontend && npm run build          # 产物 → ../src/xianyu_crawler/web/static
```

## 代码地图

```
src/xianyu_crawler/
  config.py        Settings(BaseSettings, env_prefix=XIANYU_, 读 .env + data/secret.env) + Watch + 默认提示词
  models.py        Item 等领域值对象
  search.py        搜索(关键词空格合并成一条 query, 单次 goto)
  filter.py        matches(): 价格/城市/成色/包邮 规则过滤
  favorite.py      点"收藏"(get_by_text("收藏", exact=True)) — 不是"想要"
  favorites_list.py 读收藏夹(含 reducePrice、死链信号)
  price_monitor.py / pipeline.py  降价检测 + 事件
  review.py        LLM 二次审核(OpenAI 兼容)
  liveness.py      详情页核活(死链判定)
  parsing.py       mtop JSON 字段解析(随版本变, 有 *.sample.json 回归)
  service.py       用例层: 桥接 DB ↔ 引擎; effective_settings() 做配置合并
  storage/
    orm.py         ItemRow / PriceHistory / Event / WatchRow / AppConfig
    repo.py        纯 DB 操作(可独立测试); _now() = naive UTC
    migrate.py     幂等 ALTER 列迁移(加字段必改这里)
    db.py          make_session(create=True 时自动跑迁移)
  web/
    app.py         FastAPI 路由(/api/*) + SPA 静态托管
    runner.py      浏览器 worker(全局 _LOCK 串行) + _notify(按事件类型过滤邮件)
    scheduler.py   APScheduler 两个周期: crawl + favorites
    login_runner.py 扫码登录状态机 + logout() + _account()(取 tracknick 昵称)
    dto.py         Pydantic DTO + row↔DTO 映射; _iso() 把 naive UTC 标成 +00:00
    runtime.py     进程内单例 session
frontend/src/
  App.jsx          全屏 grid 外壳(顶栏/侧栏/主区/右栏) + 主题/收起 + 轮询
  sections/        Recommendations / Drops(收藏) / Watches / Settings
  components/ui.jsx, api.js, util.js, styles.css(设计系统 + 主题令牌), theme.js(浅/深/自定义配色)
```

## 数据模型要点

- **`ItemRow`** 一行即一个商品：`rec_status`(new/approved/rejected)、`rec_ok`(LLM 裁决 True/False/None)、`rec_reason`、`favorited`/`favorited_at`、`dead`/`dead_reason`(粘性)、`muted_until`、`publish_time`、`price_changed_at`、`reduce_price`。
- **`Event.type`** 目前只有 `price_drop` 和 `favorited`(右栏事件流/邮件据此)。
- **`AppConfig`** 单行(id=1)：定时/阈值/SMTP/LLM/高级/`notify_on_{drop,favorite,login}` 邮件开关。
- 列表查询语义在 `repo.py`：`list_recommendations` 排除已收藏/静音、死链排末尾；`list_favorites` = favorited ∪ source==favorite。

## 时间处理(易错)

SQLite 读回的 datetime 一律 **naive**。统一约定：库里存 **naive UTC**(`repo._now()`)；出 API 时 `dto._iso()` 标成 `+00:00`，前端再转本地时区。**新加的时间字段出参一律走 `_iso()`**（`/api/events` 曾漏标导致差 8 小时）。

## 数据库迁移

改 `orm.py` 加列 → **必须**同步在 `migrate.py` 的 `COLUMNS` 追加 `(表, 列, "DDL")`。`make_session(create=True)` 启动即幂等执行，保住用户真实数据。

## 配置分层 / 密钥

`service.effective_settings(cfg)`：`Settings()` 基线被 `AppConfig` 覆盖；SMTP/LLM 接口地址/Token 用 `pick(db_val, env_val)`——控制台填了用控制台的，留空回退 `data/secret.env`/环境变量。DTO 里密码与 Token **只接收不回传**(只给 `*_set` 布尔)。

## 前端约定

- 主题只有浅色、深色两套预设 + 用户自定义；颜色令牌由 `theme.js` 从「背景/文字/强调」三个颜色推导，以行内 CSS 变量挂在 `#app` 上（不再有 `data-s`）。收起靠 `#app[data-collapsed]`；主题/收起记忆在 `localStorage`，只影响本人浏览器。
- Vite 构建 **压缩 CSS**(去引号/空格)——grep 验证产物时用 `data-collapsed=1` 而非 `data-collapsed='1'`。
- 字体：全局 `Microsoft YaHei`（`--font-ui`，macOS/Linux 回退 PingFang SC / Noto Sans SC / system-ui），不再外链 Google Fonts；图标仍是 tabler 图标字体。

## 部署

```powershell
pwsh -File scripts/deploy.ps1            # 打包→scp→构建→重启→探活, 只回一行
pwsh -File scripts/deploy.ps1 -NoBuild   # 只同步 git + 重启(纯文档改动)
```

服务器地址与密钥在 `data/deploy.env`（gitignore），不在仓库里。手工作业流程如下，脚本就是它的固化：

```bash
docker build -t xianyu-console:latest \
  --build-arg PYTHON_IMAGE=<your-mirror>/python:3.12-slim \
  --build-arg NODE_IMAGE=node:22-alpine .
docker compose up -d --no-build --force-recreate
```
前端在镜像 `fe` 阶段构建并 COPY 进 `web/static`；只挂载 `./data`，**改 `src`/前端必须重建镜像**(不是 restart)。

## 坑 / 禁忌

- **Playwright headless 必须用真实 Chrome UA**(`anti_detect.pick_profile()`)，否则闲鱼报「非法访问」。
- 截图读取有累计上限：验证视觉用「computed-style 断言 + SendUserFile(让用户看)」，不要狂读大图。
- 浏览器作业一律经 `runner._LOCK` 串行(Playwright sync 一次只能跑一个)。
- 不要用 `as any` / `@ts-ignore` / `# type: ignore` 掩盖类型错误；按权威 pyright 修根因。
