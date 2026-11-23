import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import FolderLayout from '../components/FolderLayout'
import { Attrs, Card, Badge, Spinner, EmptyState, Thumb, TimeMeta, Seller } from '../components/ui'
import { yuan, fmtDate, ago } from '../util'
import Folders, { ownFolders, useFolders } from '../components/Folders'
import SnapshotButton from '../components/SnapshotButton'
import ItemSort, { DEFAULT_SORT, sortItems } from '../components/ItemSort'
import PriceHistory from '../components/PriceHistory'
import PriceTrend from '../components/PriceTrend'

export default function Drops({ refreshKey, onToast }) {
  const [items, setItems] = useState(null)
  const [visibility, setVisibility] = useState('mine')
  const [folderId, setFolderId] = useState('')
  const [sortOrder, setSortOrder] = useState(DEFAULT_SORT)
  const shotRef = useRef(null)   // 快照范围: 标题 + 总趋势图 + 商品卡
  const sortTouched = useRef(false)
  const [cfg, setCfg] = useState(null)
  const [loadError, setLoadError] = useState('')
  const { watches, folders, shared, error } = useFolders(refreshKey, visibility)

  const load = () => api.favorites().then(setItems).catch((error) => setLoadError(error.message))

  // 本账号默认排序: 加载配置时套用, 用户手动选过就不再覆盖
  useEffect(() => {
    if (!sortTouched.current && cfg?.default_sort) setSortOrder(cfg.default_sort)
  }, [cfg])
  const changeSort = (value) => {
    sortTouched.current = true
    setSortOrder(value)
  }
  const makeSortDefault = async (value) => {
    try {
      await api.saveConfig({ default_sort: value })
      onToast?.('已设为默认排序')
    } catch (error) {
      onToast?.(error.message)
    }
  }

  useEffect(() => {
    load()
    api.config().then(setCfg).catch(() => {})
  }, [refreshKey])

  if (items === null) return loadError ? <p role="alert">{loadError}</p> : <Spinner />
  const publicChoices = shared.filter((folder) => items.some((item) =>
    item.shared_folder_key === folder.id || item.watch_ids?.some((id) => folder.watches.includes(id))))
  const choices = visibility === 'public'
    ? publicChoices
    : [...ownFolders(watches, folders, visibility), ...(visibility === 'mine' ? publicChoices.filter(
      (folder) => items.some((item) => item.shared_folder_key === folder.id)
    ) : [])]
  const inFolder = (item, folder) => {
    if (folder?.id === 'ungrouped') {
      return !item.watch_ids?.length && !publicChoices.some((f) => f.id === item.shared_folder_key)
    }
    return folder != null && (item.shared_folder_key === folder.id ||
      item.watch_ids?.some((id) => folder.watches.includes(id)))
  }
  // 默认落在真正有收藏的组: 只按顺序取第一个的话, 站内收藏的公开商品会藏在「未归档」下面看不见
  const selected = choices.find((folder) => folder.id === folderId)
    ?? choices.find((folder) => items.some((item) => inFolder(item, folder)))
    ?? choices[0]
  const shown = items.filter((item) => inFolder(item, selected))
  const counts = Object.fromEntries(choices.map((folder) => [
    folder.id, items.filter((item) => inFolder(item, folder)).length,
  ]))

  return (
    <section>
      <h1 className="page-title">收藏监控</h1>
      {error && <p role="alert" className="test-err">{error}</p>}
      <FolderLayout folders={<Folders choices={choices} selected={selected?.id} onSelect={setFolderId}
        visibility={visibility} onVisibility={setVisibility} counts={counts} />}>
        <div className="folder-results" ref={shotRef}>
      {selected && <div className="folder-heading">
        <h2>{selected.name}</h2>
        <div className="folder-tools">
          <ItemSort value={sortOrder} onChange={changeSort} onMakeDefault={makeSortDefault} />
          <SnapshotButton target={shotRef} name={selected.name} onToast={onToast} />
        </div>
      </div>}
      {selected?.watches?.length > 0 && (
        <PriceTrend watches={selected.watches} refreshKey={refreshKey} />
      )}
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
                <div className="rec-price-row">
                  <div className="rec-price">
                    {yuan(it.price)}
                    {it.original_price > it.price && (
                      <span className="rec-drop">已降 {yuan(it.original_price - it.price)}</span>
                    )}
                    {it.promo_price && it.list_price > it.promo_price && (
                      <span className="rec-promo">平台优惠 · 挂牌 {yuan(it.list_price)}</span>
                    )}
                  </div>
                  <PriceHistory item={it} onChange={load} />
                </div>
                {!it.dead && it.reduce_price > 0 && (
                  <Badge tone="drop">降 ¥{Math.round(it.reduce_price).toLocaleString('zh-CN')}</Badge>
                )}
                <div className="rec-meta">
                  <Seller nick={it.seller_nick} />
                  {it.free_shipping && <Badge>包邮</Badge>}
                  {it.location && <span>{it.location}</span>}
                  {it.condition && <span>{it.condition}</span>}
                </div>
                <Attrs attrs={it.attrs} />
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
      </FolderLayout>
    </section>
  )
}
