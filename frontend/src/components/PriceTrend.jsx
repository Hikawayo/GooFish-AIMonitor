import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { fmtDateTime, yuan } from '../util'

const MODES = [
  ['all', '全部时间'],
  ['day', '按天'],
  ['week', '按周'],
  ['month', '按月'],
]

const PAD = { left: 50, right: 16, top: 14, bottom: 26 }
const HEIGHT = 210
const pad2 = (n) => String(n).padStart(2, '0')
const pad4 = (n) => String(n).padStart(4, '0')
const clamp = (value, low, high) => Math.min(high, Math.max(low, value))

function tickLabel(ms, mode, spanMs) {
  const d = new Date(ms)
  if (mode === 'month') return `${pad4(d.getFullYear())}-${pad2(d.getMonth() + 1)}`
  if (mode === 'all' && spanMs < 2 * 86400000) {
    return `${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`
  }
  return `${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

function Chart({ data, width, mode, base, range, onRange, hover, onHover, colors }) {
  const svg = useRef(null)
  const drag = useRef(null)
  const plotW = width - PAD.left - PAD.right
  const plotH = HEIGHT - PAD.top - PAD.bottom
  const { t0, t1, pLow, pHigh } = range

  const x = (ms) => PAD.left + ((ms - t0) / Math.max(1, t1 - t0)) * plotW
  const y = (price) => PAD.top + (1 - (price - pLow) / Math.max(1e-9, pHigh - pLow)) * plotH
  const xIso = (iso) => x(Date.parse(iso))
  const line = (points, key) => points
    .map((point) => `${xIso(point.t).toFixed(1)},${y(point[key]).toFixed(1)}`).join(' ')

  const visible = data.series.filter((point) => {
    const ms = Date.parse(point.t)
    return ms >= t0 && ms <= t1
  })
  const xTicks = [0, 0.25, 0.5, 0.75, 1].map((ratio) => t0 + (t1 - t0) * ratio)
  const yTicks = [pLow, (pLow + pHigh) / 2, pHigh]

  const begin = (edge) => (event) => {
    event.preventDefault()
    svg.current?.setPointerCapture(event.pointerId)
    drag.current = { edge, x: event.clientX, y: event.clientY, start: range }
  }

  const move = (event) => {
    const box = svg.current?.getBoundingClientRect()
    if (!box) return
    const scale = box.width / width || 1
    const current = drag.current
    if (!current) {                       // 没在拖 → 更新悬停读数
      if (!visible.length) return
      // 按 X 距离找最近的观测点: 时间桶不是等间距的, 用下标比例会落后于鼠标
      const localX = (event.clientX - box.left) / scale
      let nearest = 0
      visible.forEach((point, index) => {
        if (Math.abs(xIso(point.t) - localX) < Math.abs(xIso(visible[nearest].t) - localX)) nearest = index
      })
      onHover(visible[nearest])
      return
    }
    const dx = (event.clientX - current.x) / scale
    const dy = (event.clientY - current.y) / scale
    const start = current.start
    const perPxPrice = (start.pHigh - start.pLow) / plotH
    const perPxTime = (start.t1 - start.t0) / plotW
    const minPrice = (base.pHigh - base.pLow) * 0.05
    const minTime = (base.t1 - base.t0) * 0.02
    const next = { ...start }
    if (current.edge === 'bottom') {
      next.pLow = clamp(start.pLow - dy * perPxPrice, base.pLow, start.pHigh - minPrice)
    } else if (current.edge === 'top') {
      next.pHigh = clamp(start.pHigh - dy * perPxPrice, start.pLow + minPrice, base.pHigh)
    } else if (current.edge === 'left') {
      next.t0 = clamp(start.t0 + dx * perPxTime, base.t0, start.t1 - minTime)
    } else {
      next.t1 = clamp(start.t1 + dx * perPxTime, start.t0 + minTime, base.t1)
    }
    onRange(next)
  }

  const end = (event) => {
    if (!drag.current) return
    svg.current?.releasePointerCapture(event.pointerId)
    drag.current = null
  }

  // fill 用属性写死: 截图时克隆进 SVG 会丢 CSS 类的透明填充, 变成黑色粗边
  const hit = (edge, cursor) => ({
    className: 'trend-hit',
    fill: 'transparent',
    style: { cursor },
    onPointerDown: begin(edge),
  })

  return (
    <svg ref={svg} className="trend-svg" viewBox={`0 0 ${width} ${HEIGHT}`}
      role="img" aria-label="价格趋势：每件商品与最低价、中位数，拖边可缩放范围"
      onPointerMove={move} onPointerUp={end} onPointerCancel={end}
      onPointerLeave={() => { if (!drag.current) onHover(null) }}
      onDoubleClick={() => onRange(null)}>
      <defs>
        <clipPath id="trend-clip">
          <rect x={PAD.left} y={PAD.top} width={plotW} height={plotH} />
        </clipPath>
      </defs>

      {/* 透明底: 没有它的话, 指针落在空白处不触发事件, 悬浮要扫到线上才有反应 */}
      <rect x="0" y="0" width={width} height={HEIGHT} fill="transparent" className="trend-bg" />

      {yTicks.map((value) => (
        <g key={`y${value}`}>
          <line x1={PAD.left} x2={width - PAD.right} y1={y(value)} y2={y(value)}
            className="trend-grid" stroke={colors.grid} />
          <text x={PAD.left - 8} y={y(value) + 3.5} className="trend-axis" textAnchor="end">{yuan(value)}</text>
        </g>
      ))}
      {xTicks.map((stamp, index) => (
        <text key={`x${index}`} x={x(stamp)} y={HEIGHT - 8} className="trend-axis"
          textAnchor={index === 0 ? 'start' : index === xTicks.length - 1 ? 'end' : 'middle'}>
          {tickLabel(stamp, mode, t1 - t0)}
        </text>
      ))}

      <g clipPath="url(#trend-clip)">
        {data.items.map((item) => (
          <polyline key={item.item_id} points={line(item.points, 'price')}
            className="trend-item-line" fill="none" stroke={colors.item}>
            <title>{item.title}</title>
          </polyline>
        ))}
        <polyline points={line(data.series, 'median')} className="trend-median-line"
          fill="none" stroke={colors.median} strokeDasharray="6 5" />
        <polyline points={line(data.series, 'min')} className="trend-min-line"
          fill="none" stroke={colors.min} strokeWidth="2.2" />
        {hover && (
          <>
            <line x1={xIso(hover.t)} x2={xIso(hover.t)} y1={PAD.top}
              y2={HEIGHT - PAD.bottom} className="trend-cursor" stroke={colors.grid} />
            <circle cx={xIso(hover.t)} cy={y(hover.min)} r="3.2" className="trend-dot" fill={colors.min} />
            <circle cx={xIso(hover.t)} cy={y(hover.median)} r="2.6"
                className="trend-dot trend-dot-soft" fill={colors.median} />
          </>
        )}
      </g>

      {/* 价格标在观测点上: 跟着鼠标所在的那个时间桶 */}
      {hover && (() => {
        const px = xIso(hover.t)
        const tipW = 154
        const tipH = 38
        const tipX = clamp(px - tipW / 2, PAD.left, width - PAD.right - tipW)
        const tipY = Math.max(PAD.top, y(hover.min) - tipH - 10)
        return (
          <g className="trend-tip" pointerEvents="none">
            <rect x={tipX} y={tipY} width={tipW} height={tipH} rx="6" />
            <text x={tipX + 9} y={tipY + 14}>{fmtDateTime(hover.t)}</text>
            <text x={tipX + 9} y={tipY + 28} className="trend-tip-main">
              最低 {yuan(hover.min)} · 中位 {yuan(hover.median)}
            </text>
          </g>
        )
      })()}

      {/* 四条可拖的边: 上下调价格范围, 左右调日期范围 */}
      <line x1={PAD.left} x2={width - PAD.right} y1={y(pLow)} y2={y(pLow)} className="trend-handle" stroke={colors.min} strokeDasharray="5 4" />
      <line x1={PAD.left} x2={width - PAD.right} y1={y(pHigh)} y2={y(pHigh)} className="trend-handle" stroke={colors.min} strokeDasharray="5 4" />
      <line x1={x(t0)} x2={x(t0)} y1={PAD.top} y2={HEIGHT - PAD.bottom} className="trend-handle" stroke={colors.min} strokeDasharray="5 4" />
      <line x1={x(t1)} x2={x(t1)} y1={PAD.top} y2={HEIGHT - PAD.bottom} className="trend-handle" stroke={colors.min} strokeDasharray="5 4" />
      <rect className="trend-grip" x={PAD.left + plotW / 2 - 14} y={y(pLow) - 3} width={28} height={6} rx={3} fill={colors.min} />
      <rect className="trend-grip" x={PAD.left + plotW / 2 - 14} y={y(pHigh) - 3} width={28} height={6} rx={3} fill={colors.min} />
      <rect className="trend-grip" x={x(t0) - 3} y={PAD.top + plotH / 2 - 14} width={6} height={28} rx={3} fill={colors.min} />
      <rect className="trend-grip" x={x(t1) - 3} y={PAD.top + plotH / 2 - 14} width={6} height={28} rx={3} fill={colors.min} />

      <rect x={PAD.left} y={y(pLow) - 9} width={plotW} height={18} {...hit('bottom', 'ns-resize')} />
      <rect x={PAD.left} y={y(pHigh) - 9} width={plotW} height={18} {...hit('top', 'ns-resize')} />
      <rect x={x(t0) - 9} y={PAD.top} width={18} height={plotH} {...hit('left', 'ew-resize')} />
      <rect x={x(t1) - 9} y={PAD.top} width={18} height={plotH} {...hit('right', 'ew-resize')} />
    </svg>
  )
}

function chartColors() {
  const style = getComputedStyle(document.getElementById('app') || document.documentElement)
  const pick = (name, fallback) => (style.getPropertyValue(name) || '').trim() || fallback
  return {
    min: pick('--acc', '#00aabb'),
    median: pick('--dim', '#5b6b7a'),
    item: pick('--line2', '#c9d3dc'),
    grid: pick('--line', '#e3e9ee'),
  }
}

export default function PriceTrend({ watches, refreshKey }) {
  const colors = chartColors()
  const [mode, setMode] = useState('all')
  const [seat, setSeat] = useState('')
  const [open, setOpen] = useState(() => localStorage.getItem('xy-trend') !== '0')
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [digest, setDigest] = useState(null)
  const [digestBusy, setDigestBusy] = useState(false)
  const [hover, setHover] = useState(null)
  const [view, setView] = useState(null)
  const [width, setWidth] = useState(680)
  const box = useRef(null)
  const key = (watches || []).join(',')

  useEffect(() => {
    setSeat('')
    setDigest(null)
  }, [key])

  useEffect(() => {
    if (!key) {
      setData(null)
      return
    }
    let active = true
    api.priceTrend(key, mode, -new Date().getTimezoneOffset(), undefined, seat || undefined)
      .then((result) => {
        if (!active) return
        setData(result)
        setError('')
      })
      .catch((err) => { if (active) setError(err.message) })
    return () => { active = false }
  }, [key, mode, seat, refreshKey])

  const loadDigest = async () => {
    if (digestBusy) return
    setDigestBusy(true)
    try {
      const res = await api.digest(watches)
      setDigest(res)
    } catch (err) {
      setError(err.message)
    } finally {
      setDigestBusy(false)
    }
  }

  useEffect(() => {
    if (!open || !box.current) return
    const observer = new ResizeObserver(([entry]) => {
      setWidth(Math.max(320, Math.round(entry.contentRect.width)))
    })
    observer.observe(box.current)
    return () => observer.disconnect()
  }, [open])

  // 每次拿到新数据都回到「看全部」，缩放只在本次浏览内有效
  useEffect(() => {
    setView(null)
    setHover(null)
  }, [data])

  const base = useMemo(() => {
    if (!data || !data.series.length) return null
    const prices = [
      ...data.series.flatMap((point) => [point.min, point.median]),
      ...data.items.flatMap((item) => item.points.map((point) => point.price)),
    ]
    const low = Math.min(...prices)
    const high = Math.max(...prices)
    const room = Math.max(1, high - low)
    return {
      t0: Date.parse(data.from),
      t1: Date.parse(data.to),
      pLow: low - room * 0.08,
      pHigh: high + room * 0.08,
    }
  }, [data])

  if (!key) return null

  const toggle = () => {
    setOpen((current) => {
      localStorage.setItem('xy-trend', current ? '0' : '1')
      return !current
    })
  }

  const series = data?.series ?? []
  const range = view ?? base
  const shown = range ? series.filter((point) => {
    const ms = Date.parse(point.t)
    return ms >= range.t0 && ms <= range.t1
  }) : []
  const last = shown.length ? shown[shown.length - 1] : null
  const peak = shown.length ? Math.max(...shown.map((point) => point.min)) : null
  const change = peak && last ? Math.round((last.min - peak) / peak * 100) : 0
  const active = last

  return (
    <div className="trend">
      <div className="trend-head">
        <h2>价格总览</h2>
        <div className="trend-modes" role="group" aria-label="时间粒度">
          {MODES.map(([value, label]) => (
            <button key={value} type="button" aria-pressed={mode === value}
              onClick={() => setMode(value)}>{label}</button>
          ))}
        </div>
        {data?.seats?.length > 0 && (
          <div className="trend-modes" role="group" aria-label="席种筛选">
            <button type="button" aria-pressed={!seat} onClick={() => setSeat('')}>全部席种</button>
            {data.seats.map((s) => (
              <button key={s} type="button" aria-pressed={seat === s} onClick={() => setSeat(s)}>{s}</button>
            ))}
          </div>
        )}
        <button type="button" className="btn btn-ghost btn-sm" onClick={loadDigest} disabled={digestBusy}>
          {digestBusy ? '生成中…' : '趋势简报'}
        </button>
        <button type="button" className="trend-toggle" onClick={toggle}
          aria-expanded={open} aria-label={open ? '收起价格总览' : '展开价格总览'}>
          <i className={'ti ' + (open ? 'ti-chevron-up' : 'ti-chevron-down')} />
        </button>
      </div>

      {error && <p role="alert" className="test-err">{error}</p>}
      {digest && (
        <div className="trend-note" style={{ marginBottom: 10 }}>
          {digest.summary}
          {digest.warn && <span className="test-err">（{digest.warn}）</span>}
        </div>
      )}

      {open && (data === null
        ? <div className="trend-empty">加载中…</div>
        : series.length === 0
          ? <div className="trend-empty">这个条件还没有价格记录，跑一轮抓取后就有了</div>
          : series.length === 1
            ? <div className="trend-empty">
              {MODES.find(([value]) => value === mode)?.[1]}只有一个时间段，换「按周」或「按天」会更细
            </div>
            : <>
              <div className="trend-readout">
                {active
                  ? <>
                    {fmtDateTime(active.t)} · 最低 {yuan(active.min)}
                    {active.p25 != null ? ` · P25 ${yuan(active.p25)}` : ''}
                    {' · '}中位 {yuan(active.median)} · {active.count} 件在售
                  </>
                  : null}
                <span className="trend-sum">
                  {peak ? `最高 ${yuan(peak)} → 现 ${yuan(last.min)}` : ''}
                  {change === 0 ? '（持平）' : `（${change > 0 ? '+' : '−'}${Math.abs(change)}%）`}
                  {' · '}共 {data.items_total} 件
                  {(data.summary?.dropped > 0 || data.summary?.raised > 0) && (
                    `（降 ${data.summary.dropped} / 涨 ${data.summary.raised}）`
                  )}
                </span>
              </div>
              <div ref={box}>
                <Chart data={data} width={width} mode={mode} base={base} range={range} colors={colors}
                  onRange={setView} hover={hover} onHover={setHover} />
              </div>
              <div className="trend-legend">
                <span><i className="trend-key-min" />最低价</span>
                <span><i className="trend-key-median" />中位数</span>
                <span><i className="trend-key-item" />每件商品</span>
              </div>
              {data.groups?.length > 1 && (
                <div className="trend-note">
                  跨组对比：{data.groups.map((g) => `${g.name} 最低 ${yuan(g.min)} / 中位 ${yuan(g.median)}（${g.count}件）`).join(' · ')}
                </div>
              )}
              {data.stats_excluded > 0 && (
                <div className="trend-note">另 {data.stats_excluded} 件捆绑/定金未计入最低价与中位数</div>
              )}
            </>)}
    </div>
  )
}
