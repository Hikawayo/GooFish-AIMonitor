import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { fmtDateTime } from '../util'
import { Button, Spinner } from './ui'

const price = (value) => `¥${value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`

function PricePlot({ points }) {
  const width = 540
  const height = 148
  const pad = 12
  const [hover, setHover] = useState(null)
  const svg = useRef(null)
  const first = Date.parse(points[0].observed_at)
  const last = Date.parse(points.at(-1).observed_at)
  const prices = points.map((point) => point.price)
  const low = Math.min(...prices)
  const high = Math.max(...prices)
  const coords = points.map((point, index) => {
    const time = last > first ? (Date.parse(point.observed_at) - first) / (last - first) : index / Math.max(1, points.length - 1)
    const amount = high > low ? (point.price - low) / (high - low) : 0.5
    return [pad + time * (width - 2 * pad), height - pad - amount * (height - 2 * pad)]
  })

  // 鼠标落在哪个观测点: 按 X 方向找最近的点, 价格标在那个点上
  const move = (event) => {
    const box = svg.current?.getBoundingClientRect()
    if (!box) return
    const localX = ((event.clientX - box.left) / box.width) * width
    let best = 0
    coords.forEach(([x], index) => { if (Math.abs(x - localX) < Math.abs(coords[best][0] - localX)) best = index })
    setHover(best)
  }

  const [endX, endY] = coords.at(-1)
  const active = hover == null ? null : { point: points[hover], at: coords[hover] }
  const tipWidth = 108
  const tipX = active ? Math.min(Math.max(active.at[0] - tipWidth / 2, pad), width - pad - tipWidth) : 0
  const tipY = active ? Math.max(pad, active.at[1] - 34) : 0

  return (
    <figure className="price-plot">
      <svg ref={svg} viewBox={`0 0 ${width} ${height}`} role="img"
        aria-label={`挂牌价格趋势，最低 ${price(low)}，最高 ${price(high)}`}
        onMouseMove={move} onMouseLeave={() => setHover(null)}>
        <line x1={pad} x2={width - pad} y1={height - pad} y2={height - pad} className="plot-axis" />
        <polyline points={coords.map(([x, y]) => `${x},${y}`).join(' ')} className="plot-line" />
        <circle cx={endX} cy={endY} r="4" className="plot-point" />
        {active && (
          <>
            <line x1={active.at[0]} x2={active.at[0]} y1={pad} y2={height - pad} className="plot-cursor" />
            <circle cx={active.at[0]} cy={active.at[1]} r="4" className="plot-point" />
            <g className="plot-tip" pointerEvents="none">
              <rect x={tipX} y={tipY} width={tipWidth} height={30} rx="6" />
              <text x={tipX + 8} y={tipY + 13}>{fmtDateTime(active.point.observed_at)}</text>
              <text x={tipX + 8} y={tipY + 25} className="plot-tip-price">{price(active.point.price)}</text>
            </g>
          </>
        )}
      </svg>
      <figcaption><time>{fmtDateTime(points[0].observed_at)}</time><time>{fmtDateTime(points.at(-1).observed_at)}</time></figcaption>
    </figure>
  )
}

function PriceDialog({ item, folder, close }) {
  const dialog = useRef(null)
  const [points, setPoints] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    dialog.current.showModal()
    let active = true
    api.prices(item.item_id, folder)
      .then((result) => { if (active) setPoints(result) })
      .catch((error) => { if (active) setError(error.message) })
    return () => { active = false }
  }, [item.item_id, folder])
  const latest = points?.at(-1)
  return (
    <dialog ref={dialog} className="history-dialog" aria-label="价格记录" onClose={close}>
      <div className="history-heading">
        <h2>价格记录</h2>
        <Button variant="ghost" onClick={() => dialog.current.close()}>关闭</Button>
      </div>
      <p className="history-title">{item.title}</p>
      {error ? <p role="alert" className="test-err">{error}</p>
        : points === null ? <Spinner />
          : latest ? <>
            <div className="history-metrics">
              <div><span>最近挂牌价</span><strong>{price(latest.price)}</strong></div>
              {points.length > 1 && <div>
                <span>记录最低</span><strong>{price(Math.min(...points.map((point) => point.price)))}</strong>
              </div>}
            </div>
            {points.length > 1 ? <PricePlot points={points} />
              : <p className="history-note">目前只有一次观测，等下一次复检或发现新价格后再看变化。</p>}
            <details className="history-rows" open={points.length < 8}>
              <summary>观测明细</summary>
              <table>
                <thead><tr><th scope="col">观测时间</th><th scope="col">挂牌价</th></tr></thead>
                <tbody>{[...points].reverse().map((point, index) => (
                  <tr key={index}><td>{fmtDateTime(point.observed_at)}</td><td>{price(point.price)}</td></tr>
                ))}</tbody>
              </table>
            </details>
          </> : <p className="history-note">暂无价格记录</p>}
      <div className="history-actions">
        <a className="btn btn-ghost" href={item.url} target="_blank" rel="noreferrer">打开闲鱼原帖</a>
      </div>
    </dialog>
  )
}

export default function PriceHistory({ item, folder }) {
  const [open, setOpen] = useState(false)
  return <>
    <Button variant="ghost" className="btn-sm history-trigger" onClick={() => setOpen(true)}>价格记录</Button>
    {open && <PriceDialog item={item} folder={folder} close={() => setOpen(false)} />}
  </>
}
