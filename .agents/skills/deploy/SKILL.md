---
name: deploy
description: 把当前 main 发布到线上服务器（打包→构建→重启→探活），只回一行结果；纯文档或无需重建镜像时用 -NoBuild。
---

# Deploy

一条命令把仓库当前 `main` 发到线上。

```powershell
pwsh -File scripts/deploy.ps1            # 代码/前端改动: 重建镜像(约 90 秒)
pwsh -File scripts/deploy.ps1 -NoBuild   # 只同步 git + 重启(文档、服务器侧改动)
```

规则：

- 成功时脚本只输出一行，例如 `deploy: a5a5b7b | build ok | caddy 200 | 92s`。**把这一行贴给用户，不要贴构建过程。**
- 失败时脚本给一行原因；详细过程在 `data/deploy.log`，只在需要判断原因时读最后 20 行。
- 服务器地址与密钥来自 `data/deploy.env`（已 gitignore），不要写进仓库或回复。
- 只改 `docs/`、`.agents/`、`README`、`AGENTS.md` 时用 `-NoBuild`：镜像里不包含这些文件，构建纯属浪费。
- 同一会话里的多个小改**攒成一次发布**：一次构建约 90 秒，是整轮里最贵的等待。
- 发布前如果改了代码，先跑 `verify` skill，别把失败带上线。
