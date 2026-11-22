---
name: verify
description: 一条命令跑完 pytest + pyright（可选前端构建），只回一行结果；失败才指向 data/verify.log。
---

# Verify

改完代码，用一条命令确认没坏：

```powershell
pwsh -File scripts/verify.ps1              # 后端: pytest + pyright
pwsh -File scripts/verify.ps1 -Frontend    # 再加前端构建
```

规则：

- 成功只输出一行：`verify: 142 passed | pyright 0 errors | build ok`。**直接把这一行贴给用户。**
- 失败输出第一处失败 + 日志路径；需要定位时只读 `data/verify.log` 末尾 20 行，不要把整段测试输出搬进回复。
- 同一会话里不要每改一个文件就跑一次：**改完一批再跑**，一次约 10 秒。
- 权威命令就是这两个（`.venv\Scripts\python.exe -m pytest -q` 与 `npx pyright`）；内置诊断不可信。
