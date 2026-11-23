import { useState } from 'react'
import { api } from '../api'
import { renderSnapshot } from '../snapshot'

const pad = (value) => String(value).padStart(2, '0')

function stamp() {
  const d = new Date()
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}`
}

const safeName = (name) => (name || '快照').replace(/[\\/:*?"<>|]/g, '-').slice(0, 60)

const toRow = (item) => ({
  title: item.title,
  price: item.price,
  seller: item.seller_nick,
  location: item.location,
  attrs: item.attrs,
  promo_price: item.promo_price,
  list_price: item.list_price,
  original_price: item.original_price,
  publish_time: item.publish_time,
  dead: item.dead,
  dead_reason: item.dead_reason,
  dead_at: item.dead_at,
})

/**
 * 导出当前文件夹的行情图。
 * 不截图 DOM(会挤压界面、还会溢出), 直接用 canvas 按固定版式绘制, 快且可预测。
 */
export default function SnapshotButton({ name, watches, items, onToast }) {
  const [busy, setBusy] = useState(false)

  const shoot = async () => {
    if (!items?.length) {
      onToast?.('当前文件夹没有商品')
      return
    }
    setBusy(true)
    try {
      let series = null
      if (watches?.length) {
        const tz = -new Date().getTimezoneOffset()
        const data = await api.priceTrend(watches.join(','), 'all', tz)
        series = data?.series ?? null
      }
      const url = renderSnapshot({ name, items: items.map(toRow), series })
      const link = document.createElement('a')
      link.download = `${safeName(name)}-${stamp()}.png`
      link.href = url
      link.click()
      onToast?.('行情图已导出')
    } catch (error) {
      onToast?.(`导出失败：${error.message || error}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <button type="button" className="icon-btn snapshot-btn" disabled={busy}
      title={busy ? '正在生成…' : '导出行情图（趋势 + 价格表）'} aria-label="导出行情图" onClick={shoot}>
      <i className={`ti ${busy ? 'ti-loader-2' : 'ti-camera'}`} />
    </button>
  )
}
