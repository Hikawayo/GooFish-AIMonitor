/**
 * 主题: 两套预设(浅色=白+#00AABB、深色=黑白) + 一套个人自定义。
 *
 * 一套主题只要三个颜色(背景/文字/强调), 其余令牌由这三个推导, 自定义主题才不会
 * 因为漏配某个颜色而出现不可读的按钮或边框。选择存在 localStorage, 只影响本人浏览器。
 */

export const LIGHT = { bg: '#f7faf9', fg: '#355359', acc: '#00aabb' }
export const DARK = { bg: '#0f1719', fg: '#e5f0f2', acc: '#38beca' }

export const PRESETS = [
  { key: 'light', name: '青瓷', ...LIGHT },
  { key: 'dark', name: '深海青瓷', ...DARK },
  { key: 'peach-nendo', name: '乐桃奶油', bg: '#fff9f3', fg: '#6d564a', acc: '#e65080' },
  { key: 'catppuccin-latte', name: 'Catppuccin Latte', bg: '#eff1f5', fg: '#4c4f69', acc: '#179299' },
  { key: 'catppuccin-mocha', name: 'Catppuccin Mocha', bg: '#1e1e2e', fg: '#cdd6f4', acc: '#89b4fa' },
  { key: 'tokyo-night', name: 'Tokyo Night', bg: '#1a1b26', fg: '#c0caf5', acc: '#2ac3de' },
  { key: 'nord-light', name: 'Nord Light', bg: '#eceff4', fg: '#3b4252', acc: '#5e81ac' },
  { key: 'nord-dark', name: 'Nord Dark', bg: '#2e3440', fg: '#e5e9f0', acc: '#88c0d0' },
  { key: 'gruvbox-light', name: 'Gruvbox Light', bg: '#fbf1c7', fg: '#504945', acc: '#458588' },
  { key: 'gruvbox-dark', name: 'Gruvbox Dark', bg: '#282828', fg: '#ebdbb2', acc: '#83a598' },
  { key: 'rose-pine-dawn', name: 'Rosé Pine Dawn', bg: '#faf4ed', fg: '#575279', acc: '#286983' },
  { key: 'everforest-light', name: 'Everforest', bg: '#fdf6e3', fg: '#5c6a72', acc: '#35a77c' },
  { key: 'kanagawa', name: 'Kanagawa', bg: '#1f1f28', fg: '#dcd7ba', acc: '#7e9cd8' },
]

export const QUICK_PRESETS = PRESETS.slice(0, 3)

const STORAGE_KEY = 'xy-theme-key'
const STORAGE_CUSTOM = 'xy-theme-custom'
const LEGACY_KEY = 'xy-skin'
// 旧版五套皮肤 → 现在的浅/深两套(用户看不出变化, 但不会掉成无样式)
const LEGACY = { linear: 'dark', vercel: 'dark', supabase: 'dark', stripe: 'light', apple: 'light', 'ceramic-teal': 'light', 'ceramic-dark': 'dark' }

const isHex = (value) => typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value)

function channels(hex) {
  const text = (isHex(hex) ? hex : '#000000').slice(1)
  return [0, 2, 4].map((i) => parseInt(text.slice(i, i + 2), 16))
}

function toHex(values) {
  return '#' + values.map((v) => Math.round(Math.min(255, Math.max(0, v)))
    .toString(16).padStart(2, '0')).join('')
}

/** t=0 取 first, t=1 取 second。 */
function mix(first, second, t) {
  const a = channels(first)
  const b = channels(second)
  return toHex(a.map((v, i) => v + (b[i] - v) * t))
}

function alpha(hex, a) {
  const [r, g, b] = channels(hex)
  return `rgba(${r}, ${g}, ${b}, ${a})`
}

function luminance(hex) {
  const [r, g, b] = channels(hex).map((v) => {
    const c = v / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(a, b) {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (high + 0.05) / (low + 0.05)
}

/** 主题 → #app 的 CSS 变量。浅色采用海盐白瓷四阶面 + 青釉描边 + 零投影；深色与自定义沿用同一推导逻辑。 */
export function themeVars(palette) {
  const dark = luminance(palette.bg) < 0.3
  const paper = dark ? mix(palette.bg, palette.fg, 0.06) : '#ffffff'
  const beige = dark ? mix(palette.bg, palette.fg, 0.11) : mix(palette.bg, palette.acc, 0.07)
  const sand = dark ? mix(palette.bg, palette.fg, 0.16) : mix(palette.bg, palette.acc, 0.14)
  const borderCeramic = dark ? alpha(palette.acc, 0.34) : mix(palette.acc, '#ffffff', 0.65)
  return {
    '--bg': palette.bg,
    '--s1': paper,
    '--s2': beige,
    '--sand': sand,
    '--fg': palette.fg,
    '--fg-deep': dark ? palette.fg : mix(palette.fg, '#0c1c20', 0.35),
    '--dim': mix(palette.fg, palette.bg, 0.42),
    '--line': dark ? alpha(palette.fg, 0.14) : sand,
    '--line2': borderCeramic,
    '--acc': palette.acc,
    '--acc-mid': dark ? mix(palette.acc, '#ffffff', 0.12) : mix(palette.acc, '#ffffff', 0.22),
    '--acc-ink': dark ? mix(palette.acc, '#ffffff', 0.2) : mix(palette.acc, '#002c32', 0.25),
    '--af': luminance(palette.acc) < 0.44 ? '#ffffff' : (contrast(palette.acc, '#ffffff') >= contrast(palette.acc, '#111111') ? '#ffffff' : '#111111'),
    '--soft': dark ? alpha(palette.acc, 0.2) : mix(palette.acc, '#ffffff', 0.89),
    '--rad': '0px 18px',
    '--rad-card': '0px 30px',
    '--rad-cta': '0px 14px',
    '--rad-in': '6px',
    '--sh': 'none',
  }
}

export function paletteOf(key, custom) {
  if (key === 'custom' && custom) return custom
  return PRESETS.find((preset) => preset.key === key) ?? LIGHT
}

function readCustom() {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_CUSTOM) || 'null')
    return raw && isHex(raw.bg) && isHex(raw.fg) && isHex(raw.acc)
      ? { bg: raw.bg, fg: raw.fg, acc: raw.acc }
      : null
  } catch {
    return null
  }
}

export function loadTheme() {
  const custom = readCustom()
  let stored = null
  try {
    stored = localStorage.getItem(STORAGE_KEY) || localStorage.getItem(LEGACY_KEY)
  } catch {
    /* 隐私模式读不到, 按新用户处理 */
  }
  const hasPreset = PRESETS.some((p) => p.key === stored)
  const key = stored === 'custom'
    ? (custom ? 'custom' : 'light')
    : (hasPreset ? stored : LEGACY[stored] || 'light')
  return { key, custom }
}

export function saveTheme(key, custom) {
  try {
    localStorage.setItem(STORAGE_KEY, key)
    if (custom) localStorage.setItem(STORAGE_CUSTOM, JSON.stringify(custom))
    localStorage.removeItem(LEGACY_KEY)
  } catch {
    /* 存不了就只在本次会话生效 */
  }
}
