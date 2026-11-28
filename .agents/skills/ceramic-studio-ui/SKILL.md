---
name: ceramic-studio-ui
description: Apply the unified Studio Family UI design system (inspired by Peach Aviation 2026 nendo rebrand): four-step tinted surfaces, zero drop shadows, 2px/3px tinted borders, diagonal asymmetric corners, 13 switchable curated themes (Ceramic Teal, Ceramic Dark, Peach nendo, Catppuccin, Tokyo Night, Nord, Gruvbox, Rose Pine, Everforest, Kanagawa), mobile floating-island nav with scroll hide/show, single-screen fit, and anti-jitter fade transitions.
---

# Ceramic Studio UI — 同工作室家族风格设计系统

一套源自乐桃航空（2026 nendo 焕新）骨架、彻底摆脱「冷灰底 + 纯黑字 + 弥散阴影 + 对称圆角」AI 模板感的 Web UI 设计与交互规范。

---

## 一、核心原则（不可违背）

1. **Avoid unnecessary secondary labels and descriptions. Let the layout do the explaining.**
   - 绝不擅自添加原界面不存在的英文副标题、说明文案、状态废话或装饰性徽章。
2. **零纯黑、零冷灰、零弥散阴影**
   - 正文不用 `#000`，背景不用默认冷灰（如 `#f3f4f7` / Tailwind `slate`）；全部中性色（底面、正文、粗描边）都带有与主色协调的色相温度。
   - 卡片、按钮、表单一律 `box-shadow: none`，依靠**四阶底面色阶 + `2px/3px` 有色粗描边**建立层级（仅悬浮在内容之上的移动底栏浮岛和弹出菜单允许极轻投影）。
3. **标志性几何母题（对角非对称圆角）**
   - 大卡片 / 面板 / 弹窗：`border-radius: 0px 30px`（移动端 `0px 24px`），`border: 2.5px–3px solid var(--border-ceramic)`
   - 导航芯片 / 筛选按钮 / 列表项：`border-radius: 0px 18px`（或 `0px 20px`），`border: 2px solid var(--border-ceramic)`
   - 主 CTA 按钮：`border-radius: 0px 14px`，无描边实心 `--brand`
   - 输入框 / 表格单元格 / 棋盘格 / 日历格：保持工整对称 `border-radius: 6px`
4. **呼吸感与排版**
   - 西文与数字优先几何无衬线（`Montserrat` / `Avenir Next` / `DIN Alternate`）配中文无衬线，`font-variant-numeric: tabular-nums`。
   - 字重主要只用 `400` / `600` / `700` 三档拉开层级；背景用 1–2 个超大低对比圆形色块（`radial-gradient`）柔化矩形边界；底栏用整块实色 `--footer-bg` 配白字收尾。

---

## 二、统一 14 令牌 CSS 契约

所有主题只替换这一组 CSS 变量，**不改动任何组件结构与圆角骨架**：

```css
:root {
  /* 四阶底面：基底 -> 板块/侧栏 -> 外框/槽 -> 交互主体卡片 */
  --bg-base: #f7faf9;
  --bg-section: #eaf3f2;
  --bg-sand: #d8e8e7;
  --bg-paper: #ffffff;

  /* 正文与有色粗描边 */
  --ink: #355359;
  --ink-deep: #1f3a40;
  --ink-muted: #6b878d;
  --border-ceramic: #a5d5dc;

  /* 双阶品牌重点色 + 底栏 + 浅高亮 + 语义点缀 */
  --brand: #00aabb;
  --brand-hover: #008e9d;
  --brand-mid: #38beca;       /* 次级激活态：导航当前项、Toggle */
  --brand-ink: #007d8a;       /* 浅底上的高对比强调字色 */
  --brand-soft: #e6f7f9;
  --footer-bg: #1898a8;
  --warm-accent: #d9822b;     /* 少量冷暖平衡点缀 */
  --warm-soft: #fdf3e3;
  --danger: #c94a4a;

  /* 固定几何令牌 */
  --r-card: 0px 30px;
  --r-chip: 0px 18px;
  --r-cta: 0px 14px;
  --r-input: 6px;
}
```

### 主题切换协议（允许用户随心切换，无需逐组件特化）
- 通过 `document.documentElement.dataset.studioTheme` 切换主题 ID，默认 `ceramic-teal`（不写属性直接走 `:root`）。
- 持久化键名统一为 `localStorage.getItem("studio-theme")`。
- 入口保持极简：顶栏放一个图标/「主题」按钮，点击弹出 2 列色块网格弹窗即可任选。

---

## 三、13 套精选预设主题（开箱即用）

> 覆盖默认青瓷、深海青瓷、乐桃原版以及主流社区配色体系（Catppuccin、Tokyo Night、Nord、Gruvbox、Rosé Pine、Everforest、Kanagawa），全部已按「四阶面 + 有色粗描边 + 零纯黑」重新调和。

### 1. `ceramic-teal`（青瓷 · 默认浅色）
```css
:root,
:root[data-studio-theme="ceramic-teal"] {
  --bg-base: #f7faf9; --bg-section: #eaf3f2; --bg-sand: #d8e8e7; --bg-paper: #ffffff;
  --ink: #355359; --ink-deep: #1f3a40; --ink-muted: #6b878d; --border-ceramic: #a5d5dc;
  --brand: #00aabb; --brand-hover: #008e9d; --brand-mid: #38beca; --brand-ink: #007d8a;
  --brand-soft: #e6f7f9; --footer-bg: #1898a8; --warm-accent: #d9822b; --warm-soft: #fdf3e3; --danger: #c94a4a;
}
```

### 2. `ceramic-dark`（深海青瓷 · 配套深色）
```css
:root[data-studio-theme="ceramic-dark"] {
  --bg-base: #0f1719; --bg-section: #162225; --bg-sand: #1f3034; --bg-paper: #152023;
  --ink: #e5f0f2; --ink-deep: #f2f9fa; --ink-muted: #88a4aa; --border-ceramic: #2f555d;
  --brand: #38beca; --brand-hover: #53cdd8; --brand-mid: #2099a6; --brand-ink: #73d6df;
  --brand-soft: #19353a; --footer-bg: #13545c; --warm-accent: #e39b43; --warm-soft: #2b2114; --danger: #e26d6d;
}
```

### 3. `peach-nendo`（乐桃奶油 · 暖纸原版）
```css
:root[data-studio-theme="peach-nendo"] {
  --bg-base: #fff9f3; --bg-section: #f6ede4; --bg-sand: #eddfd4; --bg-paper: #ffffff;
  --ink: #6d564a; --ink-deep: #4e3a30; --ink-muted: #9a867a; --border-ceramic: #e2c3a6;
  --brand: #e65080; --brand-hover: #cf3d6d; --brand-mid: #ef8da5; --brand-ink: #c73c69;
  --brand-soft: #fce7ed; --footer-bg: #e5869a; --warm-accent: #2d8a68; --warm-soft: #e6f5ee; --danger: #bf0008;
}
```

### 4. `catppuccin-latte`（Catppuccin Latte · 柔和拿铁浅色）
```css
:root[data-studio-theme="catppuccin-latte"] {
  --bg-base: #eff1f5; --bg-section: #e6e9ef; --bg-sand: #dce0e8; --bg-paper: #ffffff;
  --ink: #4c4f69; --ink-deep: #303446; --ink-muted: #6c6f85; --border-ceramic: #bcc0cc;
  --brand: #179299; --brand-hover: #137a80; --brand-mid: #04a5e5; --brand-ink: #179299;
  --brand-soft: #dff3f4; --footer-bg: #1e66f5; --warm-accent: #df8e1d; --warm-soft: #fdf2dc; --danger: #d20f39;
}
```

### 5. `catppuccin-mocha`（Catppuccin Mocha · 摩卡深色）
```css
:root[data-studio-theme="catppuccin-mocha"] {
  --bg-base: #1e1e2e; --bg-section: #181825; --bg-sand: #313244; --bg-paper: #242436;
  --ink: #cdd6f4; --ink-deep: #f5e0dc; --ink-muted: #a6adc8; --border-ceramic: #585b70;
  --brand: #89b4fa; --brand-hover: #74c7ec; --brand-mid: #94e2d5; --brand-ink: #89dceb;
  --brand-soft: #263147; --footer-bg: #313244; --warm-accent: #f9e2af; --warm-soft: #3a3428; --danger: #f38ba8;
}
```

### 6. `tokyo-night`（Tokyo Night · 东京夜深色）
```css
:root[data-studio-theme="tokyo-night"] {
  --bg-base: #1a1b26; --bg-section: #16161e; --bg-sand: #292e42; --bg-paper: #24283b;
  --ink: #c0caf5; --ink-deep: #e2e8ff; --ink-muted: #7aa2f7; --border-ceramic: #3b4261;
  --brand: #2ac3de; --brand-hover: #7dcfff; --brand-mid: #7aa2f7; --brand-ink: #7dcfff;
  --brand-soft: #1f3344; --footer-bg: #292e42; --warm-accent: #e0af68; --warm-soft: #332c20; --danger: #f7768e;
}
```

### 7. `nord-light`（Nord Snow Storm · 北欧雪原浅色）
```css
:root[data-studio-theme="nord-light"] {
  --bg-base: #eceff4; --bg-section: #e5e9f0; --bg-sand: #d8dee9; --bg-paper: #ffffff;
  --ink: #3b4252; --ink-deep: #2e3440; --ink-muted: #4c566a; --border-ceramic: #b7c5d8;
  --brand: #5e81ac; --brand-hover: #4c6c94; --brand-mid: #81a1c1; --brand-ink: #46658c;
  --brand-soft: #e4edf5; --footer-bg: #4c566a; --warm-accent: #d08770; --warm-soft: #faece7; --danger: #bf616a;
}
```

### 8. `nord-dark`（Nord Polar Night · 北欧极夜深色）
```css
:root[data-studio-theme="nord-dark"] {
  --bg-base: #2e3440; --bg-section: #272c36; --bg-sand: #3b4252; --bg-paper: #343b48;
  --ink: #e5e9f0; --ink-deep: #eceff4; --ink-muted: #9aa7bc; --border-ceramic: #4c566a;
  --brand: #88c0d0; --brand-hover: #8fbcbb; --brand-mid: #81a1c1; --brand-ink: #88c0d0;
  --brand-soft: #31424c; --footer-bg: #3b4252; --warm-accent: #ebcb8b; --warm-soft: #413b2d; --danger: #bf616a;
}
```

### 9. `gruvbox-light`（Gruvbox Light · 复古暖羊皮纸浅色）
```css
:root[data-studio-theme="gruvbox-light"] {
  --bg-base: #fbf1c7; --bg-section: #f2e5bc; --bg-sand: #ebdbb2; --bg-paper: #fffaf0;
  --ink: #504945; --ink-deep: #3c3836; --ink-muted: #7c6f64; --border-ceramic: #d5c4a1;
  --brand: #458588; --brand-hover: #076678; --brand-mid: #689d6a; --brand-ink: #076678;
  --brand-soft: #e3eee8; --footer-bg: #458588; --warm-accent: #d79921; --warm-soft: #f9ecc9; --danger: #cc241d;
}
```

### 10. `gruvbox-dark`（Gruvbox Dark · 复古暖炭深色）
```css
:root[data-studio-theme="gruvbox-dark"] {
  --bg-base: #282828; --bg-section: #1d2021; --bg-sand: #3c3836; --bg-paper: #32302f;
  --ink: #ebdbb2; --ink-deep: #fbf1c7; --ink-muted: #a89984; --border-ceramic: #665c54;
  --brand: #83a598; --brand-hover: #8ec07c; --brand-mid: #d79921; --brand-ink: #8ec07c;
  --brand-soft: #2e3b38; --footer-bg: #3c3836; --warm-accent: #fabd2f; --warm-soft: #3d3421; --danger: #fb4934;
}
```

### 11. `rose-pine-dawn`（Rosé Pine Dawn · 暮色玫瑰纸张浅色）
```css
:root[data-studio-theme="rose-pine-dawn"] {
  --bg-base: #faf4ed; --bg-section: #f2e9e1; --bg-sand: #dfdad9; --bg-paper: #fffaf3;
  --ink: #575279; --ink-deep: #3f3a5b; --ink-muted: #797593; --border-ceramic: #d7c7c2;
  --brand: #286983; --brand-hover: #1f5469; --brand-mid: #d7827e; --brand-ink: #286983;
  --brand-soft: #e5eff2; --footer-bg: #907aa9; --warm-accent: #ea9d34; --warm-soft: #fbf0dd; --danger: #b4637a;
}
```

### 12. `everforest-light`（Everforest · 森系和纸浅色）
```css
:root[data-studio-theme="everforest-light"] {
  --bg-base: #fdf6e3; --bg-section: #f4f0d9; --bg-sand: #e6e2cc; --bg-paper: #fffdf5;
  --ink: #5c6a72; --ink-deep: #3d484d; --ink-muted: #829181; --border-ceramic: #c5d0b8;
  --brand: #35a77c; --brand-hover: #2a8a66; --brand-mid: #8da101; --brand-ink: #2a8a66;
  --brand-soft: #e5f3ec; --footer-bg: #3a94c5; --warm-accent: #dfa000; --warm-soft: #fbf1d4; --danger: #f85552;
}
```

### 13. `kanagawa`（Kanagawa · 葛饰北斋深蓝）
```css
:root[data-studio-theme="kanagawa"] {
  --bg-base: #1f1f28; --bg-section: #16161d; --bg-sand: #2a2a37; --bg-paper: #252533;
  --ink: #dcd7ba; --ink-deep: #f0ebd0; --ink-muted: #9cabca; --border-ceramic: #54546d;
  --brand: #7e9cd8; --brand-hover: #7fb4ca; --brand-mid: #7aa89f; --brand-ink: #7fb4ca;
  --brand-soft: #263043; --footer-bg: #2a2a37; --warm-accent: #e6c384; --warm-soft: #383226; --danger: #e46876;
}
```

---

## 四、移动端规范（仅移动端断点生效，PC 端严禁启用）

### 4.1 底部浮岛导航 + 顶部单页操作栏
- 移动断点（`max-width: 760px` / `860px` / `900px`）：
  - **页面级主导航**固定在底部做成浮岛：`position: fixed; left: 12px; right: 12px; bottom: calc(10px + env(safe-area-inset-bottom, 0px)); z-index: 42; border: 2px solid var(--border-ceramic); border-radius: 0px 22px; background: var(--bg-paper);`
  - **单页高频操作**（如扫描、返回、筛选、账号/主题）保留在顶部栏。
  - **防 `transform` 包含块陷阱**：如果底部浮岛 `<nav>` 在 `<header>` 内部，**绝不能给 `<header>` 本身加 `transform` 或 `will-change: transform`**；必须把顶部内容包进独立 `.top-bar`（桌面端 `display: contents`，移动端 `position: fixed; top: 0;`），让 `.top-bar` 与底部 `<nav>` 各自独立执行 `translateY`。

### 4.2 顶栏与底栏同步滚动显隐
- 手指自下往上滑（`scrollTop` 增大 `>= 10px` 且 `scrollTop > 8`）→ 顶栏上滑隐藏（`translateY(calc(-100% - 8px))`），底部浮岛下滑隐藏（`translateY(calc(100% + 28px + env(safe-area-inset-bottom)))`）。
- 手指自上往下滑（`scrollTop` 减小 `>= 10px`）→ 两者同步显示。
- **停止滑动继承当前状态**（不设定时器回弹）；切换标签/路由或回到顶部（`<= 8px`）时重置可见；PC 端 `matchMedia` 不命中时永不隐藏。
- 注意监听实际滚动容器（`window`、内部 `.main` 或 capture 阶段多面板滚动）。

### 4.3 非信息流页面一屏显示全
- 信息流类页面（商品列表、航班列表、长文档）正常下滑；
- 交互型单屏页面（如 Wordle 猜词棋盘+键盘、小游戏、登录页）在移动端（含 `390×844` 与 `375×667` 矮屏）必须通过 `100dvh` 紧凑排布，让核心交互区完整落在底部浮岛上方，**无需垂直下滑即可完整操作**。

---

## 五、防左右抖动与切换动效（必做）

1. **防滚动条显隐导致左右跳动**：
   - 全局必须设置 `html { scrollbar-gutter: stable; }` 与 `body { overflow-x: clip; }`（内部滚动区如 `.main`、`.detail-pane` 同理加 `scrollbar-gutter: stable;`）。
   - **禁止**使用 `margin-inline: calc(50% - 50vw)` 这类带 `vw` 的全幅撑宽（会包含滚动条宽度引起横向溢出）。
   - SPA 切换标签时**禁止**销毁重建外层壳（如 `root.innerHTML`），仅原地更新导航高亮并替换内容区。
2. **丝滑淡入淡出动效**：
   - 多页跳转：`@view-transition { navigation: auto; }`
   - 单页切标签/路由：旧内容短暂淡出（`opacity: 0; transform: translateY(4px); 95–130ms`）后替换，新内容执行 `@keyframes viewFadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }`（`220ms cubic-bezier(0.22, 1, 0.36, 1)`）。
   - 全站必须配合 `@media (prefers-reduced-motion: reduce)` 关闭位移动画。
