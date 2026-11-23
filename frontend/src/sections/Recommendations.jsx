import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import FolderLayout from '../components/FolderLayout'
import { Attrs, Card, Button, Badge, Spinner, EmptyState, Thumb, TimeMeta, Seller } from '../components/ui'
import { yuan, fmtDate, fmtDateTime, ago } from '../util'
import Folders, { ownFolders, useFolders } from '../components/Folders'
import SnapshotButton from '../components/SnapshotButton'
import ItemSort, { DEFAULT_SORT, sortItems } from '../components/ItemSort'
import PriceHistory from '../components/PriceHistory'
import PriceTrend from '../components/PriceTrend'

const REVIEW_NOT_RUN = "(审核未运行)"

export default function Recommendations({ refreshKey, onToast }) {
  const [items, setItems] = useState(null)
  const [busy, setBusy] = useState({})
  const [muteOpen, setMuteOpen] = useState(null)
  const [onlyPassed, setOnlyPassed] = useState(true) // 默认只看 LLM 通过的
  const [reviewing, setReviewing] = useState(false)
  const [cfg, setCfg] = useState(null)               // 人工审核模式(关闭 AI 审核)没有 AI 筛选项
  const [visibility, setVisibility] = useState('mine')
  const [folderId, setFolderId] = useState('')
  const [sortOrder, setSortOrder] = useState(DEFAULT_SORT)
  const shotRef = useRef(null)   // 快照范围: 标题 + 总趋势图 + 商品卡
  const sortTouched = useRef(false)
  const [savedShared, setSavedShared] = useState({})
  const { watches, folders, shared, error } = useFolders(refreshKey, visibility)

  // 自己还没有条件时先打开公开组: 否则新成员第一次进来只看到空列表, 不知道有别人的组可看
  const autoShared = useRef(false)
  useEffect(() => {
    if (autoShared.current || watches.length || !shared.length) return
    autoShared.current = true
    setVisibility('public')
  }, [watches.length, shared.length])

  const load = () => api.recommendations('new').then(setItems)

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
    load().catch((error) => onToast?.(error.message))
  }, [refreshKey])
  useEffect(() => {
    api.config().then(setCfg).catch(() => {})
  }, [])

  // 一键 AI 审核: 用当前 LLM 配置对已入库的待审推荐补审(不重新抓取)
  const reviewAll = async () => {
    setReviewing(true)
    try {
      const r = await api.reviewPending()
      if (r.ok === false) {
        onToast?.(r.error || 'AI 审核未运行')
      } else {
        const parts = [`已审核 ${r.reviewed} 条`, `通过 ${r.passed}`, `未过 ${r.rejected}`]
        if (r.not_run) parts.push(`${r.not_run} 条没跑通（用「测试 LLM」查接口）`)
        if (r.skipped_no_requirement) parts.push(`${r.skipped_no_requirement} 条无审核要求已跳过`)
        onToast?.(parts.join(' · '))
        await load()
      }
    } catch (error) {
      onToast?.(error.message)
    } finally {
      setReviewing(false)
    }
  }

  const act = async (id, fn) => {
    setBusy((b) => ({ ...b, [id]: true }))
    try {
      const r = await fn(id)
      if (r && r.ok === false) {                 // 收藏没真成功 → 保留卡片 + 提示, 不再假装成功
        onToast?.('操作失败，商品已保留，可稍后重试')
        return
      }
      setItems((xs) => xs.filter((x) => x.item_id !== id))
    } catch (error) {
      onToast?.(error.message)
    } finally {
      setBusy((b) => ({ ...b, [id]: false }))
    }
  }

  const mute = (id, days) => {
    setMuteOpen(null)
    act(id, () => api.mute(id, days))
  }

  const renderCard = (it) => {
    const failed = it.rec_ok === false
    const notRun = it.reason === REVIEW_NOT_RUN
    return (
    <Card key={it.item_id} className={`rec${it.dead ? ' dead' : ''}${failed ? ' failed' : ''}`}>
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
        <div className="rec-meta">
          <Seller nick={it.seller_nick} />
          {it.free_shipping && <Badge>包邮</Badge>}
          {it.location && <span>{it.location}</span>}
          {it.condition && <span>{it.condition}</span>}
        </div>
        <Attrs attrs={it.attrs} />
        {(it.browse_count != null || it.want_count != null || it.collect_count != null) && (
          <div className="rec-stats">
            {it.browse_count != null && <span title="浏览次数">👁 浏览 {it.browse_count}</span>}
            {it.want_count != null && <span title="想要次数">🙋 想要 {it.want_count}</span>}
            {it.collect_count != null && <span title="收藏次数">⭐ 收藏 {it.collect_count}</span>}
          </div>
        )}
        {it.reason && (
          <div className={`rec-reason${notRun ? ' pending' : failed ? ' rejected' : ''}`}>
            {notRun ? 'AI 审核未完成' : it.reason}
          </div>
        )}
        <TimeMeta
          items={[
            ['上架', ago(it.publish_time)],
            ['推荐', fmtDateTime(it.rec_created_at)],
            ['调价', fmtDate(it.price_changed_at)],
          ]}
        />
        <div className="rec-actions">
          {!it.dead && (
            <Button disabled={busy[it.item_id]} onClick={() => act(it.item_id, api.approve)}>
              {busy[it.item_id] ? '收藏中…' : '站内收藏'}
            </Button>
          )}
          <Button
            variant="ghost"
            disabled={busy[it.item_id]}
            onClick={() => act(it.item_id, api.reject)}
          >
            {it.dead ? '移除' : '忽略'}
          </Button>
        </div>
        {!it.dead && (
          <div className="mute-row">
            <button
              className="mute-trigger"
              disabled={busy[it.item_id]}
              onClick={() => setMuteOpen(muteOpen === it.item_id ? null : it.item_id)}
            >
              近期不看 ▾
            </button>
            {muteOpen === it.item_id && (
              <div className="mute-menu">
                <button onClick={() => mute(it.item_id, 1)}>1 天内不看</button>
                <button onClick={() => mute(it.item_id, 7)}>7 天内不看</button>
                <button onClick={() => mute(it.item_id, 0)}>永远不看</button>
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
    )
  }

  if (items === null) return <Spinner />

  const isPublic = visibility === 'public'
  const manual = cfg?.review_enabled === false     // 关掉 AI 审核 → 全部候选都由本人裁决
  const choices = isPublic ? shared : ownFolders(watches, folders, visibility)
  const selected = choices.find((folder) => folder.id === folderId) ?? choices[0]

  const itemIn = (item, folder) => {
    const matches = item.watch_matches ?? []
    if (folder?.id === 'ungrouped') return matches.length ? null : item
    const inside = matches.filter((match) => folder?.watches.includes(match.watch_id))
    if (!inside.length) return null
    const match = inside.find((entry) => entry.rec_ok === true && entry.reason !== REVIEW_NOT_RUN)
      ?? inside[0]
    return { ...item, ...match }
  }
  const listIn = (folder) => (isPublic ? [] : items.map((item) => itemIn(item, folder)).filter(Boolean))
  const passedIn = (folder) => listIn(folder).filter((item) => item.rec_ok === true && item.reason !== REVIEW_NOT_RUN)
  const source = listIn(selected)
  const passed = passedIn(selected)
  const shown = sortItems(manual || !onlyPassed ? source : passed, sortOrder)
  // 各文件夹的数字: 侧栏计数是全账号的, 不标这里会以为有商品没加载出来
  const counts = Object.fromEntries(choices.map((folder) => [folder.id, isPublic
    ? (folder.items?.length ?? 0)
    : (manual || !onlyPassed ? listIn(folder) : passedIn(folder)).length]))

  const sharedFavorite = async (item) => {
    const key = `shared:${item.item_id}`
    setBusy((state) => ({ ...state, [key]: true }))
    try {
      const r = await api.favoriteShared(selected.id, item.item_id)
      onToast?.(r.ok ? '已站内收藏' : '收藏失败，请稍后重试')
      if (r.ok) setSavedShared((state) => ({ ...state, [item.item_id]: true }))
    } catch (error) {
      onToast?.(error.message)
    } finally {
      setBusy((state) => ({ ...state, [key]: false }))
    }
  }

  return (
    <section>
      <h1 className="page-title">{isPublic ? '公开行情' : '待审推荐'}</h1>
      {error && <p role="alert" className="test-err">{error}</p>}
      <FolderLayout folders={<Folders choices={choices} selected={selected?.id} onSelect={setFolderId}
        visibility={visibility} onVisibility={setVisibility} counts={counts} />}>
        <div className="folder-results" ref={shotRef}>
      {selected && <div className="folder-heading">
        <h2>{selected.name}</h2>
        <div className="folder-tools">
          <ItemSort value={sortOrder} onChange={changeSort} onMakeDefault={makeSortDefault} />
          {!isPublic && (
            <SnapshotButton target={shotRef} name={selected.name} onToast={onToast} />
          )}
        </div>
      </div>}
      {!isPublic && selected?.watches?.length > 0 && (
        <PriceTrend watches={selected.watches} refreshKey={refreshKey} />
      )}
      {!isPublic && !manual && source.length > 0 && (
        <div className="rec-toolbar">
          <div className="rec-filter">
            <button className={`seg${onlyPassed ? ' on' : ''}`} aria-pressed={onlyPassed} onClick={() => setOnlyPassed(true)}>
              AI 通过 <b>{passed.length}</b>
            </button>
            <button className={`seg${!onlyPassed ? ' on' : ''}`} aria-pressed={!onlyPassed} onClick={() => setOnlyPassed(false)}>
              全部 <b>{source.length}</b>
            </button>
          </div>
          <Button variant="ghost" disabled={reviewing} onClick={reviewAll}>
            {reviewing ? 'AI 审核中…' : '一键 AI 审核'}
          </Button>
        </div>
      )}
      {isPublic ? (
        selected?.items.length ? (
          <div className="grid">
            {sortItems(selected.items, sortOrder).map((item) => (
              <Card key={item.item_id} className="rec">
                <Thumb url={item.pic_url} />
                <div className="rec-body">
                  <a className="rec-title" href={item.url} target="_blank" rel="noreferrer">{item.title}</a>
                  <div className="rec-price-row"><div className="rec-price">{yuan(item.price)}</div>
                    <PriceHistory item={item} folder={selected.id} onChange={load} />
                  </div>
                  {item.seller_nick && <div className="rec-meta"><Seller nick={item.seller_nick} /></div>}
                  <Attrs attrs={item.attrs} />
                  <TimeMeta items={[['上架', ago(item.publish_time)], ['观测', fmtDateTime(item.observed_at)]]} />
                  <Button
                    disabled={busy[`shared:${item.item_id}`] || savedShared[item.item_id]}
                    onClick={() => sharedFavorite(item)}
                  >
                    {savedShared[item.item_id] ? '已收藏' : '站内收藏'}
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        ) : <EmptyState title="暂无公开商品" />
      ) : shown.length === 0 ? (
        <EmptyState
          title={!manual && onlyPassed && source.length > 0 ? '暂无 AI 通过的推荐' : '暂无新推荐'}
        />
      ) : (
        <div className="grid">{shown.map(renderCard)}</div>
      )}
        </div>
      </FolderLayout>
    </section>
  )
}
