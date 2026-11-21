import { useEffect, useState } from 'react'
import { api } from '../api'
import { Card, Badge, Spinner, EmptyState, Thumb, TimeMeta } from '../components/ui'
import { yuan, fmtDate, ago } from '../util'
import Folders, { ownFolders, useFolders } from '../components/Folders'
import ItemSort, { sortItems } from '../components/ItemSort'
import PriceHistory from '../components/PriceHistory'

export default function Drops({ refreshKey }) {
  const [items, setItems] = useState(null)
  const [visibility, setVisibility] = useState('mine')
  const [folderId, setFolderId] = useState('')
  const [sortOrder, setSortOrder] = useState('published-desc')
  const [loadError, setLoadError] = useState('')
  const { watches, folders, shared, error } = useFolders(refreshKey, visibility)

  useEffect(() => {
    api.favorites().then(setItems).catch((error) => setLoadError(error.message))
  }, [refreshKey])

  if (items === null) return loadError ? <p role="alert">{loadError}</p> : <Spinner />
  const publicChoices = shared.filter((folder) => items.some((item) =>
    item.shared_folder_key === folder.id || item.watch_ids?.some((id) => folder.watches.includes(id))))
  const choices = visibility === 'public'
    ? publicChoices
    : [...ownFolders(watches, folders, visibility), ...(visibility === 'mine' ? publicChoices.filter(
      (folder) => items.some((item) => item.shared_folder_key === folder.id)
    ) : [])]
  const selected = choices.find((folder) => folder.id === folderId) ?? choices[0]
  const shown = items.filter((item) => {
    if (selected?.id === 'ungrouped') {
      return !item.watch_ids?.length && !publicChoices.some((folder) => folder.id === item.shared_folder_key)
    }
    return selected != null && (item.shared_folder_key === selected.id ||
      item.watch_ids?.some((id) => selected.watches.includes(id)))
  })

  return (
    <section>
      <h1 className="page-title">收藏监控</h1>
      {error && <p role="alert" className="test-err">{error}</p>}
      <div className="folder-layout">
        <Folders choices={choices} selected={selected?.id} onSelect={setFolderId}
          visibility={visibility} onVisibility={setVisibility} />
        <div className="folder-results">
      {selected && <div className="folder-heading">
        <h2>{selected.name}</h2>
        <ItemSort value={sortOrder} onChange={setSortOrder} />
      </div>}
      {shown.length === 0 ? (
        <EmptyState title="还没有收藏" />
      ) : (
        <div className="grid">
          {sortItems(shown, sortOrder).map((it) => (
            <Card key={it.item_id} className={`rec${it.dead ? ' dead' : ''}`}>
              <Thumb url={it.pic_url} dead={it.dead} deadReason={it.dead_reason} />
              <div className="rec-body">
                <a className="rec-title" href={it.url} target="_blank" rel="noreferrer">
                  {it.title}
                </a>
                <div className="rec-price-row"><div className="rec-price">{yuan(it.price)}</div><PriceHistory item={it} /></div>
                {!it.dead && it.reduce_price > 0 && (
                  <Badge tone="drop">降 ¥{Math.round(it.reduce_price).toLocaleString('zh-CN')}</Badge>
                )}
                <div className="rec-meta">
                  {it.location && <span>{it.location}</span>}
                  {it.condition && <span>{it.condition}</span>}
                  {it.free_shipping && <Badge>包邮</Badge>}
                  {it.seller_nick && <span>卖家 {it.seller_nick}</span>}
                </div>
                <TimeMeta
                  items={[
                    ['上架', ago(it.publish_time)],
                    ['收藏', fmtDate(it.favorited_at)],
                    ['调价', fmtDate(it.price_changed_at)],
                  ]}
                />
              </div>
            </Card>
          ))}
        </div>
      )}
        </div>
      </div>
    </section>
  )
}
