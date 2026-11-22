import { useEffect, useRef, useState } from 'react'
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

function tickLabel(iso, mode, spanMs) {
  const d = new Date(iso)
  if (mode === 'month') return `${pad4(d.getFullYear())}-${pad2(d.getMonth() + 1)}`
  if (mode === 'all' && spanMs < 2 * 86400000) {
    return `${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`
  }
  return `${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

function Chart({ data, width, mode, onHover, hover }) {
  const t0 = Date.parse(data.from)
  const t1 = Date.parse(data.to)
  const span = Math.max(1, t1 - t0)

  const prices = [
    ...data.series.flatMap((point) => [point.min, point.median]),
    ...data.items.flatMap((item) => item.points.map((point) => point.price)),
  ]
  const low = Math.min(...prices)
  const high = Math.max(...prices)
  const room = Math.max(1, high - low)
  const bottom = low - room * 0.08
  const top = high + room * 0.08

  const x = (ms) => PAD.left + ((ms - t0) / span) * (width - PAD.left - PAD.right)
  const xIso = (iso) => x(Date.parse(iso))
  const y = (value) => PAD.top + (1 - (value - bottom) / (top - bottom)) * (HEIGHT - PAD.top - PAD.bottom)
  const path = (points, key) => points
    .map((point) => `${xIso(point.t).toFixed(1)},${y(point[key]).toFixed(1)}`).join(' ')

  const xTicks = [0, 0.25, 0.5, 0.75, 1].map((ratio) => t0 + span * ratio)
  const yTicks = [low, (low + high) / 2, high]

  const move = (event) => {
    if (!onHover || !data.series.length) return
    const rect = event.currentTarget.getBoundingClientRect()
    const scale = rect.width / width || 1            // viewBox 可能被等比缩放
    const localX = (event.clientX - rect.left) / scale
    const ratio = (localX - PAD.left) / Math.max(1, width - PAD.left - PAD.right)
    const index = Math.round(ratio * (data.series.length - 1))
    onHover(Math.min(data.series.length - 1, Math.max(0, index)))
  }

  const hoverPoint = hover == null ? null : data.series[hover]

  return (
    <svg className="trend-svg" viewBox={`0 0 ${width} ${HEIGHT}`}
      role="img" aria-label="价格趋势：每件商品与最低价、中位数"
      onMouseMove={move} onMouseLeave={() => onHover?.(null)}>
      {yTicks.map((value) => (
        <g key={`y${value}`}>
          <line x1={PAD.left} x2={width - PAD.right} y1={y(value)} y2={y(value)} className="trend-grid" />
          <text x={PAD.left - 8} y={y(value) + 3.5} className="trend-axis" textAnchor="end">{yuan(value)}</text>
        </g>
      ))}
      {xTicks.map((stamp, index) => (
        <text key={`x${index}`} x={x(stamp)} y={HEIGHT - 8} className="trend-axis"
          textAnchor={index === 0 ? 'start' : index === xTicks.length - 1 ? 'end' : 'middle'}>
          {tickLabel(stamp, mode, span)}
        </text>
      ))}

      {data.items.map((item) => (
        <polyline key={item.item_id} points={path(item.points, 'price')}
          className="trend-item-line" fill="none">
          <title>{item.title}</title>
        </polyline>
      ))}
      <polyline points={path(data.series, 'median')} className="trend-median-line" fill="none" />
      <polyline points={path(data.series, 'min')} className="trend-min-line" fill="none" />

      {hoverPoint && (
        <>
          <line x1={xIso(hoverPoint.t)} x2={xIso(hoverPoint.t)} y1={PAD.top}
            y2={HEIGHT - PAD.bottom} className="trend-cursor" />
          <circle cx={xIso(hoverPoint.t)} cy={y(hoverPoint.min)} r="3.2" className="trend-dot" />
        </>
      )}
    </svg>
  )
}

export default function PriceTrend({ watches, refreshKey }) {
  const [mode, setMode] = useState('all')
  const [open, setOpen] = useState(() => localStorage.getItem('xy-trend') !== '0')
  const [floorText, setFloorText] = useState(() => localStorage.getItem('xy-trend-floor') || '')
  const [floor, setFloor] = useState(() => localStorage.getItem('xy-trend-floor') || '')
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [hover, setHover] = useState(null)
  const [width, setWidth] = useState(680)
  const box = useRef(null)
  const key = (watches || []).join(',')

  // 输入价格下限时等手停 400ms 再请求, 免得每敲一位打一次接口
  useEffect(() => {
    const timer = setTimeout(() => {
      setFloor(floorText)
      localStorage.setItem('xy-trend-floor', floorText)
    }, 400)
    return () => clearTimeout(timer)
  }, [floorText])

  useEffect(() => {
    if (!key) {
      setData(null)
      return
    }
    let active = true
    api.priceTrend(key, mode, -new Date().getTimezoneOffset(), floor)
      .then((result) => {
        if (!active) return
        setData(result)
        setError('')
      })
      .catch((err) => { if (active) setError(err.message) })
    return () => { active = false }
  }, [key, mode, floor, refreshKey])

  useEffect(() => {
    if (!open || !box.current) return
    const observer = new ResizeObserver(([entry]) => {
      setWidth(Math.max(320, Math.round(entry.contentRect.width)))
    })
    observer.observe(box.current)
    return () => observer.disconnect()
  }, [open])

  if (!key) return null

  const toggle = () => {
    setOpen((current) => {
      localStorage.setItem('xy-trend', current ? '0' : '1')
      return !current
    })
  }

  const series = data?.series ?? []
  const latest = series[series.length - 1]
  const lowest = series.length ? Math.min(...series.map((point) => point.min)) : null
  const active = hover == null ? latest : series[hover]

  return (
    <div className="trend">
      <div className="trend-head">
        <h2>价格总览</h2>
        <input className="trend-floor" type="number" min="0" step="10" inputMode="numeric"
          placeholder="¥ 以上" aria-label="只看这个价格以上的商品"
          value={floorText} onChange={(event) => setFloorText(event.target.value)} />
        <div className="trend-modes" role="group" aria-label="时间粒度">
          {MODES.map(([value, label]) => (
            <button key={value} type="button" aria-pressed={mode === value}
              onClick={() => setMode(value)}>{label}</button>
          ))}
        </div>
        <button type="button" className="trend-toggle" onClick={toggle}
          aria-expanded={open} aria-label={open ? '收起价格总览' : '展开价格总览'}>
          <i className={'ti ' + (open ? 'ti-chevron-up' : 'ti-chevron-down')} />
        </button>
      </div>

      {error && <p role="alert" className="test-err">{error}</p>}

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
                    {fmtDateTime(active.t)} · 最低 {yuan(active.min)} · 中位 {yuan(active.median)} · {active.count} 件在售
                  </>
                  : null}
                <span className="trend-sum">
                  区间最低 {yuan(lowest)} · 共 {data.items_total} 件
                  {data.items.length < data.items_total ? `（画了 ${data.items.length} 条）` : ''}
                  {' · '}{data.observations} 次观测
                </span>
              </div>
              <div ref={box}>
                <Chart data={data} width={width} mode={mode} onHover={setHover}
                  hover={hover} />
              </div>
              <div className="trend-legend">
                <span><i className="trend-key-min" />最低价</span>
                <span><i className="trend-key-median" />中位数</span>
                <span><i className="trend-key-item" />每件商品</span>
              </div>
            </>
      )}
    </div>
  )
}
