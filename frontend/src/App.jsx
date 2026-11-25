import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { api, onAuthExpired } from './api'
import { yuan, fmtDateTime } from './util'
import Recommendations from './sections/Recommendations'
import Drops from './sections/Drops'
import Watches from './sections/Watches'
import Settings from './sections/Settings'
import ThemeEditor from './components/ThemeEditor'
import Notice, { NOTICE_VERSION } from './components/Notice'
import { QUICK_PRESETS, loadTheme, paletteOf, saveTheme, themeVars } from './theme'

const NAV = [
  ['/recommendations', '推荐', 'ti-sparkles', 'pending'],
  ['/favorites', '收藏', 'ti-bookmark', 'favorites'],
  ['/watches', '条件', 'ti-target', 'watches'],
  ['/settings', '设置', 'ti-settings', null],
]

// 实时事件按类型分 tab(全部 + 各事件类型)
const EVENT_TABS = [
  { key: 'all', label: '全部', types: null },
  { key: 'new_recommendation', label: '新推荐', types: ['new_recommendation'] },
  { key: 'price_drop', label: '降价', types: ['price_drop', 'target_price'] },
  { key: 'sold', label: '售出', types: ['sold'] },
]

const ZERO = { pending: 0, passed: 0, watches: 0, favorites: 0, dead: 0, drops_today: 0 }

function EventRow({ e }) {
  const p = e.payload || {}
  let warn = false
  let icon = 'ti-bell'
  let main = e.type
  let sub = ''
  if (e.type === 'target_price') {
    warn = true
    icon = 'ti-target'
    main = (
      <>
        <b>命中目标价 {yuan(p.price)}</b> · {p.title || ''}
      </>
    )
    sub = `${p.watch ? `${p.watch} · ` : ''}目标 ≤ ${yuan(p.target_price)}`
  } else if (e.type === 'price_drop') {
    warn = true
    icon = 'ti-trending-down'
    main = (
      <>
        <b>{p.public ? '公开组降价' : '降价'} ¥{Math.round(p.drop_abs || 0).toLocaleString('zh-CN')}</b> · {p.title || ''}
      </>
    )
    sub = p.prev_price ? `${yuan(p.prev_price)} → ${yuan(p.curr_price)}` : p.curr_price ? yuan(p.curr_price) : ''
  } else if (e.type === 'new_recommendation') {
    icon = 'ti-sparkles'
    main = (
      <>
        发现新推荐 · <b>{p.title || ''}</b>
      </>
    )
    sub = p.watch ? p.watch : p.price ? yuan(p.price) : ''
  } else if (e.type === 'sold') {
    warn = true
    icon = 'ti-circle-x'
    main = (
      <>
        已售出 / 下架 · <b>{p.title || ''}</b>
      </>
    )
    sub = p.reason || ''
  } else if (e.type === 'favorited') {
    icon = 'ti-bookmark'
    main = (
      <>
        已收藏 · <b>{p.title || ''}</b>
      </>
    )
  }
  const open = () => p.url && window.open(p.url, '_blank', 'noreferrer')
  return (
    <div className={'ev' + (warn ? ' warn' : '')} onClick={open}>
      <div className="ic">
        <i className={'ti ' + icon} />
      </div>
      <div>
        <div className="tx">{main}</div>
        <div className="et">
          {fmtDateTime(e.created_at)}
          {sub && ` · ${sub}`}
        </div>
      </div>
    </div>
  )
}

export default function App() {
  const { pathname } = useLocation()
  const [theme, setTheme] = useState(loadTheme)
  const [themeOpen, setThemeOpen] = useState(false)
  // 公告: 没看过(或版本更新了)就自动弹一次, 之后从顶栏入口再打开
  const [noticeOpen, setNoticeOpen] = useState(() => {
    try {
      return localStorage.getItem('xy-notice') !== NOTICE_VERSION
    } catch {
      return true
    }
  })
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('xy-side') === '1')
  const [status, setStatus] = useState(null)
  const [stats, setStats] = useState(ZERO)
  const [events, setEvents] = useState(null)
  const [login, setLogin] = useState({ has_state: false, expired: false })
  const [authExpired, setAuthExpired] = useState('')
  const [netOffline, setNetOffline] = useState(false)
  const netFailCount = useRef(0)
  const [toast, setToast] = useState(null)
  // 失败提示条: 关掉后只在下一轮新失败时再出现
  const [dismissedError, setDismissedError] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)
  // 手机上实时事件是底部抽屉: 默认收起, 桌面上默认展开
  const [railOpen, setRailOpen] = useState(() => {
    const saved = localStorage.getItem('xy-rail')
    if (saved === '0') return false
    if (saved === '1') return true
    return window.innerWidth > 1180
  })
  const [eventTab, setEventTab] = useState('all')
  const [watchList, setWatchList] = useState([])
  const [runMenu, setRunMenu] = useState(false)
  const [triggering, setTriggering] = useState(false)
  const wasRunning = useRef(false)

  const palette = paletteOf(theme.key, theme.custom)

  const chooseTheme = (key) => {
    const next = { key, custom: theme.custom }
    setTheme(next)
    saveTheme(next.key, next.custom)
  }
  const saveCustomTheme = (colors) => {
    const custom = { bg: colors.bg, fg: colors.fg, acc: colors.acc }
    setTheme({ key: 'custom', custom })
    saveTheme('custom', custom)
    setThemeOpen(false)
  }
  const closeNotice = () => {
    try {
      localStorage.setItem('xy-notice', NOTICE_VERSION)
    } catch {
      /* 存不了就只在本次会话记住 */
    }
    setNoticeOpen(false)
  }
  const toggleSide = () => {
    setCollapsed((c) => {
      localStorage.setItem('xy-side', c ? '0' : '1')
      return !c
    })
  }
  const toggleRail = () => {
    setRailOpen((o) => {
      localStorage.setItem('xy-rail', o ? '0' : '1')
      return !o
    })
  }

  const showToast = (msg) => {
    setToast(msg)
    setTimeout(() => setToast(null), 4500)
  }

  useEffect(() => onAuthExpired((msg) => setAuthExpired(msg)), [])

  const poll = async () => {
    try {
      const [st, sg, ev, lg] = await Promise.all([
        api.status(), api.stats(), api.events(), api.loginStatus(),
      ])
      netFailCount.current = 0
      setNetOffline(false)
      setAuthExpired('')
      setStatus(st)
      setStats(sg)
      setEvents(ev)
      setLogin(lg)
      const busyNow = !!(st.running || st.queued)
      if (wasRunning.current && !busyNow) {
        setRefreshKey((k) => k + 1)
        if (st.last?.skipped) {
          showToast(st.last.skipped === 'paused' ? '已暂停，本轮没有抓取' : '上一轮还在跑，这次跳过了')
        } else if (st.last?.error) showToast(`抓取出错：${st.last.error === 'login_expired' ? '闲鱼登录已过期，请重新扫码' : st.last.error}`)
        else if (st.last) {
          const drops = st.last.drops ?? 0
          showToast(
            `本轮完成：搜索 ${st.last.raw ?? 0} 条 · 命中 ${st.last.scanned ?? 0} 条 · 新推荐 ${st.last.recommendations ?? 0} 条`
            + (drops ? ` · 降价 ${drops}` : '')
            + (st.last.warn ? ` · ${st.last.warn}` : ''),
          )
        }
      }
      wasRunning.current = busyNow
    } catch (error) {
      if (error?.authExpired) {
        setAuthExpired(error.message)
      } else {
        netFailCount.current += 1
        if (netFailCount.current >= 2) setNetOffline(true)
      }
    }
  }

  useEffect(() => {
    poll()
    const t = setInterval(poll, 4000)
    return () => clearInterval(t)
  }, [])

  const [mobileNavHidden, setMobileNavHidden] = useState(false)
  const mainRef = useRef(null)

  useEffect(() => {
    api.watches().then(setWatchList).catch(() => {})
  }, [refreshKey, pathname])

  // 路由切换时恢复移动导航可见并回到顶部
  useEffect(() => {
    setMobileNavHidden(false)
    if (mainRef.current) mainRef.current.scrollTop = 0
  }, [pathname])

  // 仅手机端：向上滑信息流隐藏顶栏+底部浮岛，向下滑显示，停止继承当前状态
  useEffect(() => {
    const el = mainRef.current
    if (!el || typeof window === 'undefined' || !window.matchMedia) return
    const mq = window.matchMedia('(max-width: 760px)')
    let lastTop = el.scrollTop || 0
    let hidden = false
    const THRESHOLD = 10

    const onScroll = () => {
      if (!mq.matches) {
        if (hidden) { hidden = false; setMobileNavHidden(false) }
        lastTop = el.scrollTop || 0
        return
      }
      const top = Math.max(0, el.scrollTop || 0)
      if (top <= 8) {
        if (hidden) { hidden = false; setMobileNavHidden(false) }
        lastTop = top
        return
      }
      const delta = top - lastTop
      if (Math.abs(delta) < THRESHOLD) return
      if (delta > 0 && !hidden) {
        hidden = true
        setMobileNavHidden(true)
      } else if (delta < 0 && hidden) {
        hidden = false
        setMobileNavHidden(false)
      }
      lastTop = top
    }

    const onMediaChange = () => {
      if (!mq.matches && hidden) {
        hidden = false
        setMobileNavHidden(false)
      }
    }

    el.addEventListener('scroll', onScroll, { passive: true })
    mq.addEventListener?.('change', onMediaChange)
    return () => {
      el.removeEventListener('scroll', onScroll)
      mq.removeEventListener?.('change', onMediaChange)
    }
  }, [])

  const run = async (watch) => {
    setRunMenu(false)
    if (triggering) return
    if (running) {
      showToast('正在抓取中，请稍后再试')
      return
    }
    if (queued) {
      showToast(`已在排队中（第 ${queuePos} 位），无需重复触发`)
      return
    }
    setTriggering(true)
    try {
      const res = await api.run(watch)
      if (res?.deduped) {
        showToast(`已在排队中（第 ${res.position || 1} 位）`)
      } else if ((res?.position || 0) > 1) {
        showToast(`已加入队列（第 ${res.position} 位），轮到后自动开始`)
      } else {
        showToast(watch ? `已触发「${watch}」抓取…` : '已触发全部抓取，完成后自动刷新')
      }
      poll()
    } catch (error) {
      showToast(error.message)
    } finally {
      setTriggering(false)
    }
  }

  const running = status?.running
  const queued = !!status?.queued && !running
  const queuePos = status?.queue_position || 0
  const busy = !!(running || queued)
  const progress = status?.progress
  const percent = progress && progress.total > 0
    ? Math.min(100, Math.round((progress.done / progress.total) * 100))
    : null
  const step = progress?.step || ''

  // 标签页也显示进度: 切到别的页面也能看出还在跑
  useEffect(() => {
    document.title = running && percent !== null
      ? `${percent}% 抓取中 · 海鲜价格监控`
      : queued
        ? '排队中 · 海鲜价格监控'
        : '海鲜价格监控'
  }, [running, queued, percent])
  const metrics = [
    { k: '今日降价', i: 'ti-trending-down', v: stats.drops_today },
    { k: '已失效', i: 'ti-circle-x', v: stats.dead },
  ]

  const activeTab = EVENT_TABS.find((t) => t.key === eventTab) || EVENT_TABS[0]
  const shownEvents =
    events === null ? null : activeTab.types ? events.filter((e) => activeTab.types.includes(e.type)) : events

  const vars = themeVars(palette)
  useEffect(() => {
    const isDark = vars['--fg-deep'] === palette.fg
    document.documentElement.style.colorScheme = isDark ? 'dark' : 'light'
    document.documentElement.style.background = palette.bg
    document.body.style.background = palette.bg
    document.body.style.color = palette.fg
  }, [palette.bg, palette.fg, vars])

  return (
    <div
      id="app"
      style={vars}
      data-collapsed={collapsed ? '1' : '0'}
      data-rail={railOpen ? '1' : '0'}
      data-mobile-nav-hidden={mobileNavHidden ? '1' : '0'}
    >
      {/* 顶栏 */}
      <div className="top">
        <div className="logo">
          <span className="mk">
            <i className="ti ti-bolt" />
          </span>
          海鲜价格监控
        </div>
        <div className="grow" />
        <div className={'live' + (busy ? ' on' : login.expired ? ' err' : '')} role="status">
          {running
            ? (percent === null ? '抓取中…' : `抓取中 ${percent}%${step ? ` · ${step}` : ''}`)
            : queued
              ? `排队中${queuePos > 1 ? `（第 ${queuePos} 位）` : '…'}`
              : login.expired
                ? '闲鱼登录已过期'
                : login.has_state ? '' : '未登录'}
        </div>
        <div className="skins">
          <button
            className="notice-btn"
            title="使用说明与更新日志"
            aria-label="使用说明与更新日志"
            onClick={() => setNoticeOpen(true)}
          >
            <i className="ti ti-info-circle" />
          </button>
          {QUICK_PRESETS.map((preset) => (
            <button
              key={preset.key}
              className={'swatch' + (theme.key === preset.key ? ' on' : '')}
              title={preset.name}
              aria-label={`外观：${preset.name}`}
              aria-pressed={theme.key === preset.key}
              style={{ background: `linear-gradient(135deg, ${preset.bg} 0 50%, ${preset.acc} 50% 100%)` }}
              onClick={() => chooseTheme(preset.key)}
            />
          ))}
          <button
            className={'swatch swatch-add' + (theme.key === 'custom' || !QUICK_PRESETS.some((p) => p.key === theme.key) ? ' on' : '')}
            title="全部主题与自定义"
            aria-label="全部主题与自定义"
            aria-pressed={theme.key === 'custom'}
            onClick={() => setThemeOpen(true)}
          >
            <i className="ti ti-plus" />
          </button>
        </div>
        <button
          className={'icon-btn rail-toggle' + (railOpen ? ' on' : '')}
          title={railOpen ? '收起实时事件栏' : '展开实时事件栏'}
          onClick={toggleRail}
        >
          <i className="ti ti-bell" />
        </button>
        <div className="run-wrap">
          <button
            className={'run' + (busy ? ' busy' : '')}
            aria-busy={busy}
            onClick={() => {
              if (running) {
                showToast('正在抓取中，请稍后再试')
                return
              }
              if (queued) {
                showToast(`已在排队中（第 ${queuePos} 位），请稍候`)
                return
              }
              setRunMenu((o) => !o)
            }}
          >
            <i className="ti ti-player-play" />
            {queued ? '排队中' : '立即运行'}
            <i className="ti ti-chevron-down" style={{ fontSize: 14 }} />
          </button>
          {runMenu && (
            <>
              <div className="menu-backdrop" onClick={() => setRunMenu(false)} />
              <div className="run-menu">
                <button onClick={() => run(null)}>
                  <i className="ti ti-player-play" />
                  运行全部条件
                </button>
                {watchList.length > 0 && <div className="run-sep" />}
                {watchList.map((w) => (
                  <button key={w.id} onClick={() => run(w.name)} title={(w.keywords || []).join(' ')}>
                    <i className="ti ti-target" />
                    <span className="run-label">
                      <span className="run-name">{w.name}</span>
                      {w.last_run_at && (
                        <span className="run-when">最后更新 {fmtDateTime(w.last_run_at)}</span>
                      )}
                    </span>
                    {w.enabled === false && <span className="run-off">已停用</span>}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* 侧栏 */}
      <div className="side">
        {NAV.map(([path, label, icon, key]) => (
          <NavLink key={path} to={path} aria-label={label} className={({ isActive }) => 'nav' + (isActive ? ' active' : '')}>
            <i className={'ti ' + icon} />
            <span className="label">{label}</span>
            {key && <span className="cnt">{stats[key]}</span>}
          </NavLink>
        ))}
        <div className="sp" />
        <button className="collapse" onClick={toggleSide}>
          <i className={'ti ' + (collapsed ? 'ti-layout-sidebar-left-expand' : 'ti-layout-sidebar-left-collapse')} />
          <span className="label">收起侧栏</span>
        </button>
        <Link
          to="/settings"
          className="acct"
          title={login.expired ? '闲鱼登录已过期 · 点此重新扫码' : login.account ? `已登录：${login.account}` : login.has_state ? '已登录' : '未登录 · 去扫码'}
        >
          <span className="av">
            {login.account ? login.account[0].toUpperCase() : <i className="ti ti-user" />}
            {login.avatar && <img src={login.avatar} alt="" onError={(e) => e.currentTarget.remove()} />}
          </span>
          <span className="who">{login.expired ? '登录已过期' : login.account || (login.has_state ? '已登录' : '未登录')}</span>
          <span className={'dot ' + (login.expired ? 'err' : login.has_state ? 'on' : 'off')} />
        </Link>
      </div>

      {/* 主区 */}
      <div className="main" ref={mainRef}>
        {running && percent !== null && (
          <div className="run-progress" role="progressbar" aria-valuenow={percent}
            aria-valuemin={0} aria-valuemax={100} aria-label={`抓取进度 ${percent}%`}>
            <span style={{ width: `${percent}%` }} />
          </div>
        )}
        {authExpired && (
          <div className="run-alert" role="alert" data-kind="error">
            <i className="ti ti-alert-triangle" />
            <span>{authExpired}（页面数据已停止自动刷新）</span>
            <button className="btn btn-sm" onClick={() => window.location.reload()}>刷新重新登录</button>
          </div>
        )}
        {!authExpired && netOffline && (
          <div className="run-alert" role="alert" data-kind="warn">
            <i className="ti ti-alert-circle" />
            <span>暂时连不上服务器，请检查网络</span>
            <button className="btn btn-sm" onClick={() => poll()}>重试</button>
          </div>
        )}
        {!authExpired && login.expired && (
          <div className="run-alert" role="alert" data-kind="error">
            <i className="ti ti-alert-triangle" />
            <span>{login.expired_reason || '闲鱼登录已过期，搜索与收藏刷新已暂停；重新扫码即可恢复'}</span>
            <Link className="btn btn-sm" to="/settings">去重新扫码</Link>
          </div>
        )}
        {!running && (status?.last?.error || status?.last?.warn)
          && !(login.expired && status.last.error === 'login_expired')
          && dismissedError !== status.last.at && (
          <div className="run-alert" role="alert" data-kind={status.last.error ? 'error' : 'warn'}>
            <i className={'ti ' + (status.last.error ? 'ti-alert-triangle' : 'ti-alert-circle')} />
            <span>
              {status.last.error === 'login_expired'
                ? '闲鱼登录已过期，所以搜索拿不到商品；重新扫码后即可恢复'
                : status.last.error
                  ? `上一轮抓取没有跑成：${status.last.error}`
                  : `上一轮跑完了，但结果可疑：${status.last.warn}`}
              <time>{fmtDateTime(status.last.at)}</time>
            </span>
            {status.last.error === 'login_expired'
              ? <Link className="btn btn-sm" to="/settings">去登录</Link>
              : <button className="btn btn-sm" onClick={() => run(null)}>重试</button>}
            <button className="run-alert-x" aria-label="关闭提示"
              onClick={() => setDismissedError(status.last.at)}>
              <i className="ti ti-x" />
            </button>
          </div>
        )}
        <div className="strip">
          {metrics.map((m) => (
            <div className="metric" key={m.k}>
              <div className="k">
                <i className={'ti ' + m.i} />
                {m.k}
              </div>
              <div className="v">{m.v}</div>
            </div>
          ))}
        </div>

        <div className="route-stage" key={pathname}>
          <Routes>
            <Route path="/" element={<Navigate to="/recommendations" replace />} />
            <Route
              path="/recommendations"
              element={<Recommendations refreshKey={refreshKey} onToast={showToast} login={login} />}
            />
            <Route path="/favorites" element={<Drops refreshKey={refreshKey} onToast={showToast} />} />
            <Route path="/watches" element={<Watches />} />
            <Route path="/settings" element={<Settings status={status} />} />
            <Route path="*" element={<Navigate to="/recommendations" replace />} />
          </Routes>
        </div>
      </div>

      {/* 右栏 · 实时事件(可收起 + 按类型分 tab; 手机上变底部抽屉) */}
      {railOpen && <div className="rail-mask" onClick={toggleRail} aria-hidden="true" />}
      <div className="rail">
        <div className="rt">
          <i className="ti ti-activity" />
          实时事件
          <button className="rail-x" title="收起" onClick={toggleRail}>
            <i className="ti ti-chevron-right" />
          </button>
        </div>
        <div className="rail-tabs">
          {EVENT_TABS.map((t) => {
            const n = (events || []).filter((e) => !t.types || t.types.includes(e.type)).length
            return (
              <button
                key={t.key}
                className={'rtab' + (eventTab === t.key ? ' on' : '')}
                onClick={() => setEventTab(t.key)}
              >
                {t.label}
                {n > 0 && <b>{n}</b>}
              </button>
            )
          })}
        </div>
        <div className="rail-list">
          {shownEvents === null ? null : shownEvents.length === 0 ? (
            <div className="rail-empty">
              暂无事件
            </div>
          ) : (
            shownEvents.map((e, idx) => <EventRow key={`${e.item_id}-${e.created_at}-${idx}`} e={e} />)
          )}
        </div>
      </div>

      {themeOpen && (
        <ThemeEditor
          activeKey={theme.key}
          initial={theme.custom ?? palette}
          onPickPreset={chooseTheme}
          onSave={saveCustomTheme}
          onClose={() => setThemeOpen(false)}
        />
      )}

      <Notice open={noticeOpen} onClose={closeNotice} />

      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}
