// 不走 DOM 截图, 直接用 canvas 画一张固定版式的行情图:
// 标题 + 统计 + 价格走势 + 在售商品表。快、可预测、不会挤动界面。
const WIDTH = 1600
const PAD = 48
const HEADER_H = 176   // 留够标题+统计的高度, 不然会压到图表刻度的第一行
const CHART_H = 300
const ROW_H = 46
const FONT = '"Microsoft YaHei", "PingFang SC", "Noto Sans SC", system-ui, sans-serif'
const GAP = 18

const price = (value) => `¥${Math.round(value).toLocaleString('zh-CN')}`
const shortDate = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function themeColors() {
  const style = getComputedStyle(document.getElementById('app') || document.documentElement)
  const pick = (name, fallback) => (style.getPropertyValue(name) || '').trim() || fallback
  return {
    bg: pick('--bg', '#ffffff'),
    fg: pick('--fg', '#0a2540'),
    dim: pick('--dim', '#5b6b7a'),
    line: pick('--line', '#e3e9ee'),
    acc: pick('--acc', '#00aabb'),
    warn: pick('--warn', '#d9480f'),
    card: pick('--s2', '#f4f7f9'),
  }
}

/** 超宽截断加省略号 */
function clip(ctx, text, maxWidth) {
  let out = String(text || '')
  if (ctx.measureText(out).width <= maxWidth) return out
  while (out.length > 1 && ctx.measureText(`${out}…`).width > maxWidth) out = out.slice(0, -1)
  return `${out}…`
}

function drawChart(ctx, series, x, y, width, height, c) {
  if (!series || series.length < 2) {
    ctx.fillStyle = c.dim
    ctx.font = `20px ${FONT}`
    ctx.fillText('暂无走势数据', x, y + height / 2)
    return
  }
  const times = series.map((point) => Date.parse(point.t))
  const t0 = Math.min(...times)
  const t1 = Math.max(...times)
  const values = series.flatMap((point) => [point.min, point.median])
  const low = Math.min(...values)
  const high = Math.max(...values)
  const pad = (high - low) * 0.12 || 1
  const lo = low - pad
  const hi = high + pad
  const px = (t) => x + ((t - t0) / Math.max(1, t1 - t0)) * width
  const py = (v) => y + height - ((v - lo) / Math.max(1, hi - lo)) * height

  ctx.font = `18px ${FONT}`
  for (let i = 0; i <= 3; i += 1) {
    const value = lo + ((hi - lo) * i) / 3
    const gy = py(value)
    ctx.strokeStyle = c.line
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(x, gy)
    ctx.lineTo(x + width, gy)
    ctx.stroke()
    ctx.fillStyle = c.dim
    ctx.textAlign = 'right'
    ctx.fillText(price(value), x - 12, gy + 6)
  }
  ctx.textAlign = 'left'
  for (let i = 0; i <= 3; i += 1) {
    const stamp = t0 + ((t1 - t0) * i) / 3
    const label = shortDate(new Date(stamp).toISOString()).slice(0, 5)
    ctx.fillStyle = c.dim
    ctx.fillText(label, Math.min(x + (width * i) / 3, x + width - 46), y + height + 26)
  }

  const line = (key, color, dash, widthPx) => {
    ctx.beginPath()
    series.forEach((point, index) => {
      const cx = px(Date.parse(point.t))
      const cy = py(point[key])
      if (index === 0) ctx.moveTo(cx, cy)
      else ctx.lineTo(cx, cy)
    })
    ctx.strokeStyle = color
    ctx.lineWidth = widthPx
    ctx.setLineDash(dash)
    ctx.lineJoin = 'round'
    ctx.stroke()
    ctx.setLineDash([])
  }
  line('median', c.dim, [8, 6], 2)
  line('min', c.acc, [], 3)
}

/** items: [{ title, price, seller, location, attrs, original_price, promo_price, list_price }] */
export function renderSnapshot({ name, items, series }) {
  const c = themeColors()
  const rows = items.slice(0, 80)
  const tableTop = HEADER_H + CHART_H + 64
  const height = tableTop + 40 + rows.length * ROW_H + 56

  const scale = 2
  const canvas = document.createElement('canvas')
  canvas.width = WIDTH * scale
  canvas.height = height * scale
  const ctx = canvas.getContext('2d')
  ctx.scale(scale, scale)
  ctx.textBaseline = 'alphabetic'

  ctx.fillStyle = c.bg
  ctx.fillRect(0, 0, WIDTH, height)

  // 标题
  ctx.fillStyle = c.fg
  ctx.font = `bold 34px ${FONT}`
  ctx.fillText(clip(ctx, name || '行情快照', WIDTH - PAD * 2), PAD, PAD + 28)
  ctx.font = `19px ${FONT}`
  ctx.fillStyle = c.dim
  ctx.fillText(`导出时间 ${shortDate(new Date().toISOString())}`, PAD, PAD + 60)

  // 统计
  const prices = items.map((item) => item.price).filter((v) => Number.isFinite(v))
  if (prices.length) {
    const sorted = [...prices].sort((a, b) => a - b)
    const median = sorted[Math.floor(sorted.length / 2)]
    const soldCount = items.filter((item) => item.dead).length
    const stats = [
      soldCount ? ['在售', `${items.length - soldCount} 件`] : ['在售', `${items.length} 件`],
      ['最低', price(Math.min(...prices))],
      ['中位', price(median)],
      ['最高', price(Math.max(...prices))],
    ]
    let sx = PAD
    if (soldCount) stats.splice(1, 0, ['已售出', `${soldCount} 件`])
    stats.forEach(([label, value]) => {
      ctx.font = `19px ${FONT}`
      ctx.fillStyle = c.dim
      ctx.fillText(label, sx, PAD + 98)
      sx += ctx.measureText(label).width + 8
      ctx.font = `bold 22px ${FONT}`
      ctx.fillStyle = c.fg
      ctx.fillText(value, sx, PAD + 98)
      sx += ctx.measureText(value).width + 40
    })
  }

  // 走势
  drawChart(ctx, series, PAD + 96, HEADER_H, WIDTH - PAD * 2 - 96, CHART_H, c)

  // 表头
  ctx.fillStyle = c.fg
  ctx.font = `bold 24px ${FONT}`
  ctx.fillText('商品', PAD, tableTop)

  const cols = [
    { label: '价格', width: 150, align: 'right' },
    { label: '标题', width: 560, align: 'left' },
    { label: '卖家', width: 180, align: 'left' },
    { label: '地区', width: 100, align: 'left' },
    { label: '属性', width: 220, align: 'left' },
    { label: '状态', width: 130, align: 'left' },
  ]
  const columnX = []
  let cursor = PAD
  cols.forEach((col) => { columnX.push(cursor); cursor += col.width + GAP })

  let y = tableTop + 34
  ctx.font = `18px ${FONT}`
  ctx.fillStyle = c.dim
  cols.forEach((col, index) => {
    ctx.textAlign = col.align
    ctx.fillText(col.label, col.align === 'right' ? columnX[index] + col.width : columnX[index], y)
  })
  ctx.textAlign = 'left'
  y += 12
  ctx.strokeStyle = c.line
  ctx.beginPath()
  ctx.moveTo(PAD, y)
  ctx.lineTo(WIDTH - PAD, y)
  ctx.stroke()

  // 行
  rows.forEach((item, index) => {
    const rowY = y + 32 + index * ROW_H
    if (index % 2 === 1) {
      ctx.fillStyle = c.card
      ctx.fillRect(PAD - 10, rowY - 28, WIDTH - PAD * 2 + 20, ROW_H)
    }
    ctx.font = `bold 22px ${FONT}`
    ctx.fillStyle = c.fg
    ctx.textAlign = 'right'
    ctx.fillText(price(item.price), columnX[0] + cols[0].width, rowY)
    ctx.textAlign = 'left'

    ctx.font = `20px ${FONT}`
    ctx.fillText(clip(ctx, item.title, cols[1].width), columnX[1], rowY)

    ctx.font = `19px ${FONT}`
    ctx.fillStyle = c.dim
    ctx.fillText(clip(ctx, item.seller || '—', cols[2].width), columnX[2], rowY)
    ctx.fillText(clip(ctx, item.location || '', cols[3].width), columnX[3], rowY)

    const tags = []

    if (item.promo_price && item.list_price > item.promo_price) tags.push(`平台优惠 ${price(item.promo_price)}`)
    else if (item.original_price > item.price) tags.push(`已降 ${price(item.original_price - item.price)}`)
    if (item.attrs?.seat && item.attrs.seat !== '未知') tags.push(item.attrs.seat)
    if (item.attrs?.qty > 1) tags.push(`${item.attrs.qty} 张`)
    if (item.attrs?.bundle) tags.push('捆绑')
    if (item.attrs?.deposit) tags.push('定金')
    ctx.fillStyle = tags.length && /^(平台优惠|已降)/.test(tags[0]) ? c.warn : c.dim
    ctx.fillText(clip(ctx, tags.join(' · '), cols[4].width), columnX[4], rowY)

    // 状态: 售出的写售出时间, 一眼能看到
    if (item.dead) {
      ctx.fillStyle = c.warn
      ctx.fillText(clip(ctx, `${item.dead_reason || '已失效'} ${shortDate(item.dead_at).slice(0, 5)}`, cols[5].width), columnX[5], rowY)
    }
  })

  // 页脚
  ctx.fillStyle = c.dim
  ctx.font = `17px ${FONT}`
  ctx.fillText('都是挂牌价，不是成交价；平台优惠按实付价统计。', PAD, height - 24)

  return canvas.toDataURL('image/png')
}
