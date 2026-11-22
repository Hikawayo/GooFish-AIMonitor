---
name: diagnose
description: 线上排查一条命令：容器状态、最近观测时间、最近事件、最近错误日志，输出控制在 8 行内。
---

# Diagnose

用户说「没更新 / 没反应 / 报错了」时，先跑这一条，不要一上来翻全量日志：

```powershell
pwsh -File scripts/diagnose.ps1               # 最近 2 小时
pwsh -File scripts/diagnose.ps1 -Minutes 720  # 更长窗口
```

输出已经是截断过的（容器状态、`last_obs`、商品数、最近 2 条事件、最近 4 行错误），**直接贴给用户**。

判断顺序：

1. `container: Up` 否则先看容器；`caddy` 探活失败同样先修部署。
2. `last_obs` 是否就是刚才那轮的时间：没变 = 那轮没跑成或没搜到，别猜价格。
3. 最近事件里有没有 `price_drop`：没有降价事件才需要看阈值（`min_drop_pct`/`min_drop_abs`）。
4. 错误行只取 4 行；要更深的原因再定向 `docker logs --since 30m | grep -i <关键词> | tail -10`。

不要用「翻 200 行日志」来回答「为什么没更新」——先在事件表和 `price_history` 的时间里找矛盾点。

统一纪律见 AGENTS.md 的「上下文纪律」：大输出落盘、grep 先于 read、大日志交给子代理、多步合成一次命令。
