import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { api } from './api'
import { yuan, fmtDateTime } from './util'
import Recommendations from './sections/Recommendations'
import Drops from './sections/Drops'
import Watches from './sections/Watches'
import Settings from './sections/Settings'
import ThemeEditor from './components/ThemeEditor'
import { PRESETS, loadTheme, paletteOf, saveTheme, themeVars } from './theme'

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
  { key: 'price_drop', label: '降价', types: ['price_drop'] },
  { key: 'sold', label: '售出', types: ['sold'] },
]

const ZERO = { pending: 0, passed: 0, watches: 0, favorites: 0, dead: 0, drops_today: 0 }

function EventRow({ e }) {
  const p = e.payload || {}
  let warn = false
  let icon = 'ti-bell'
  let main = e.type
  let sub = ''
  if (e.type === 'price_drop') {
    warn = true
    icon = 'ti-trending-down'
    main = (
      <>
        <b>降价 ¥{Math.round(p.drop_abs || 0).toLocaleString('zh-CN')}</b> · {p.title || ''}
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
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('xy-side') === '1')
  const [status, setStatus] = useState(null)
  const [stats, setStats] = useState(ZERO)
  const [events, setEvents] = useState(null)
  const [login, setLogin] = useState({ has_state: false })
  const [toast, setToast] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [railOpen, setRailOpen] = useState(() => localStorage.getItem('xy-rail') !== '0')
  const [eventTab, setEventTab] = useState('all')
  const [watchList, setWatchList] = useState([])
  const [runMenu, setRunMenu] = useState(false)
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

  const poll = async () => {
    try {
      const [st, sg, ev, lg] = await Promise.all([
        api.status(), api.stats(), api.events(), api.loginStatus(),
      ])
      setStatus(st)
      setStats(sg)
      setEvents(ev)
      setLogin(lg)
      if (wasRunning.current && !st.running) {
        setRefreshKey((k) => k + 1)
        if (st.last?.error) showToast(`抓取出错：${st.last.error}`)
        else if (st.last) {
          const drops = st.last.drops ?? 0
          showToast(
            `本轮完成：搜索 ${st.last.raw ?? 0} 条 · 命中 ${st.last.scanned ?? 0} 条 · 新推荐 ${st.last.recommendations ?? 0} 条`
            + (drops ? ` · 降价 ${drops}` : ''),
          )
        }
      }
      wasRunning.current = st.running
    } catch {
      /* 服务未就绪, 忽略 */
    }
  }

  useEffect(() => {
    poll()
    const t = setInterval(poll, 4000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    api.watches().then(setWatchList).catch(() => {})
  }, [refreshKey, pathname])

  const run = async (watch) => {
    setRunMenu(false)
    if (running) {
      showToast('正在抓取中，请稍后再试')
      return
    }
    try {
      await api.run(watch)
      showToast(watch ? `已触发「${watch}」抓取…` : '已触发全部抓取，完成后自动刷新')
      poll()
    } catch (error) {
      showToast(error.message)
    }
  }

  const running = status?.running
  const metrics = [
    { k: '今日降价', i: 'ti-trending-down', v: stats.drops_today },
    { k: '已失效', i: 'ti-circle-x', v: stats.dead },
  ]

  const activeTab = EVENT_TABS.find((t) => t.key === eventTab) || EVENT_TABS[0]
  const shownEvents =
    events === null ? null : activeTab.types ? events.filter((e) => activeTab.types.includes(e.type)) : events

  return (
    <div id="app" style={themeVars(palette)} data-collapsed={collapsed ? '1' : '0'} data-rail={railOpen ? '1' : '0'}>
      {/* 顶栏 */}
      <div className="top">
        <div className="logo">
          <span className="mk">
            <i className="ti ti-bolt" />
          </span>
          闲鱼控制台
        </div>
        <div className="grow" />
        <div className="live" role="status">
          {running ? '抓取中…' : login.has_state ? '' : '未登录'}
        </div>
        <div className="skins">
          {PRESETS.map((preset) => (
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
            className={'swatch swatch-add' + (theme.key === 'custom' ? ' on' : '')}
            title="自定义主题"
            aria-label="自定义主题"
            aria-pressed={theme.key === 'custom'}
            onClick={() => setThemeOpen(true)}
          >
            <i className="ti ti-plus" />
          </button>
        </div>
        <button
          className={'icon-btn' + (railOpen ? ' on' : '')}
          title={railOpen ? '收起实时事件栏' : '展开实时事件栏'}
          onClick={toggleRail}
        >
          <i className="ti ti-bell" />
        </button>
        <div className="run-wrap">
          <button
            className={'run' + (running ? ' busy' : '')}
            aria-busy={running}
            onClick={() => {
              if (running) {
                showToast('正在抓取中，请稍后再试')
                return
              }
              setRunMenu((o) => !o)
            }}
          >
            <i className="ti ti-player-play" />
            立即运行
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
                    {w.name}
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
          title={login.account ? `已登录：${login.account}` : login.has_state ? '已登录' : '未登录 · 去扫码'}
        >
          <span className="av">
            {login.account ? login.account[0].toUpperCase() : <i className="ti ti-user" />}
            {login.avatar && <img src={login.avatar} alt="" onError={(e) => e.currentTarget.remove()} />}
          </span>
          <span className="who">{login.account || (login.has_state ? '已登录' : '未登录')}</span>
          <span className={'dot ' + (login.has_state ? 'on' : 'off')} />
        </Link>
      </div>

      {/* 主区 */}
      <div className="main">
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

        <Routes>
          <Route path="/" element={<Navigate to="/recommendations" replace />} />
          <Route
            path="/recommendations"
            element={<Recommendations refreshKey={refreshKey} onToast={showToast} />}
          />
          <Route path="/favorites" element={<Drops refreshKey={refreshKey} />} />
          <Route path="/watches" element={<Watches />} />
          <Route path="/settings" element={<Settings status={status} />} />
          <Route path="*" element={<Navigate to="/recommendations" replace />} />
        </Routes>
      </div>

      {/* 右栏 · 实时事件(可收起 + 按类型分 tab) */}
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
          initial={theme.custom ?? palette}
          onSave={saveCustomTheme}
          onClose={() => setThemeOpen(false)}
        />
      )}

      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}
