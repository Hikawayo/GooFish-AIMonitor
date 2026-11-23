import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { fmtDateTime } from '../util'
import Select from '../components/Select'
import { Card, Button, Spinner, EmptyState, Toggle, Field, ConfirmDialog } from '../components/ui'

const NUM_FIELDS = [
  ['schedule_minutes', '推荐抓取间隔'],
  ['favorites_minutes', '收藏刷新间隔'],
  ['min_drop_pct', '降价阈值（%）'],
  ['min_drop_abs', '降价阈值（¥）'],
  ['search_max_pages', '搜索翻页上限'],
  ['favorites_max_pages', '收藏翻页上限'],
  ['review_timeout', 'AI 审核超时'],
  ['review_temperature', '模型温度'],
  ['review_max_tokens', '最大 tokens'],
  ['action_delay_min', '操作延迟下限'],
  ['action_delay_max', '操作延迟上限'],
  ['liveness_max_checks', '死链核活上限'],
]

export default function Settings({ status }) {
  const [cfg, setCfg] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [access, setAccess] = useState(null)
  const [saveError, setSaveError] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [pwd, setPwd] = useState('') // SMTP 密码单独管理: 只在用户输入时才提交
  const [token, setToken] = useState('') // LLM token 同理(只写)
  const [testMsg, setTestMsg] = useState(null)
  const [testing, setTesting] = useState(false)
  const [llmMsg, setLlmMsg] = useState(null) // LLM 测试结果
  const [llmTesting, setLlmTesting] = useState(false)
  const [login, setLogin] = useState({ status: 'idle', has_state: false })
  const [confirmLogout, setConfirmLogout] = useState(false)
  const loginTimer = useRef(null)

  const loadAll = () => {
    setLoadError('')
    api.config()
      .then((c) => {
        setLoadError('')
        setCfg(c)
      })
      .catch((error) => setLoadError(error.message || '加载设置失败'))
    api.access().then(setAccess).catch((error) => setSaveError(error.message))
    api.loginStatus().then(setLogin).catch(() => {})
  }

  useEffect(() => {
    loadAll()
    return () => clearInterval(loginTimer.current)
  }, [])

  const startLogin = async () => {
    setLogin((l) => ({ ...l, status: 'starting', qr: null, message: '正在打开登录页…' }))
    try {
      const first = await api.loginStart()
      if (first?.status === 'busy') {
        setLogin((l) => ({ ...l, status: 'busy', message: first.message || '已有用户正在扫码，请稍后再试' }))
        return
      }
      clearInterval(loginTimer.current)
      loginTimer.current = setInterval(async () => {
        try {
          const st = await api.loginStatus()
          setLogin(st)
          if (['success', 'expired', 'failed', 'idle', 'busy'].includes(st.status)) {
            clearInterval(loginTimer.current)
          }
        } catch (error) {
          clearInterval(loginTimer.current)
          setLogin((l) => ({ ...l, status: 'failed', message: error.message || '获取扫码状态失败' }))
        }
      }, 2000)
    } catch (error) {
      setLogin((l) => ({ ...l, status: 'failed', message: error.message || '启动扫码失败，请重试' }))
    }
  }

  const set = (k, v) => setCfg((c) => ({ ...c, [k]: v }))

  // 密码/token 留空 → 发 null(不修改); 数值字段统一校验非空且为有效数字
  const buildPayload = () => {
    const out = { ...cfg }
    for (const [key, label] of NUM_FIELDS) {
      const raw = out[key]
      if (raw === '' || raw === null || raw === undefined) {
        throw new Error(`请填写「${label}」`)
      }
      const num = Number(raw)
      if (!Number.isFinite(num)) {
        throw new Error(`「${label}」必须是有效数字`)
      }
      out[key] = num
    }
    if (!access?.member && out.smtp_port !== '' && out.smtp_port !== null && out.smtp_port !== undefined) {
      const port = Number(out.smtp_port)
      if (!Number.isFinite(port)) throw new Error('「SMTP 端口」必须是有效数字')
      out.smtp_port = port
    } else if (!access?.member && out.smtp_port === '') {
      out.smtp_port = null
    }
    return {
      ...out,
      smtp_pass: pwd.trim() || null,
      review_api_token: token.trim() || null,
    }
  }

  const save = async () => {
    if (saving) return
    setSaving(true)
    try {
      const next = await api.saveConfig(buildPayload())
      setCfg(next)
      setPwd('')
      setToken('')
      setSaved(true)
      setSaveError('')
      setTimeout(() => setSaved(false), 2000)
    } catch (error) {
      setSaveError(error.message)
    } finally {
      setSaving(false)
    }
  }

  const test = async () => {
    setTesting(true)
    setTestMsg(null)
    try {
      await api.saveConfig(buildPayload()) // 先存最新配置再测
      setPwd('')
      const r = await api.testEmail()
      setTestMsg(r.ok ? { ok: true, text: `已发送到 ${r.to}` } : { ok: false, text: r.error })
      if (r.ok) api.config().then(setCfg).catch(() => {})
    } catch (error) {
      setTestMsg({ ok: false, text: error.message || '发送测试邮件失败' })
    } finally {
      setTesting(false)
    }
  }

  // 测试 LLM: 先存最新配置(含刚填的 token), 再用它对一条样例做一次真实调用
  const testLLM = async () => {
    setLlmTesting(true)
    setLlmMsg(null)
    try {
      await api.saveConfig(buildPayload())
      setToken('')
      const r = await api.testReview()
      setLlmMsg(
        r.ok
          ? { ok: true, text: `AI 审核可用 · 模型 ${r.model}` }
          : { ok: false, text: r.error },
      )
      api.config().then(setCfg).catch(() => {})
    } catch (error) {
      setLlmMsg({ ok: false, text: error.message })
    } finally {
      setLlmTesting(false)
    }
  }

  const logout = async () => {
    setConfirmLogout(false)
    clearInterval(loginTimer.current)
    try {
      setLogin(await api.logout())
    } catch (error) {
      setSaveError(error.message || '退出登录失败')
    }
  }

  // 「登录中」: 已扫码等手机确认 / 刚启动还没出二维码
  const loggingIn =
    ['starting', 'scanned'].includes(login.status) ||
    (login.status === 'waiting' && !login.qr)

  if (!cfg) {
    return loadError ? (
      <EmptyState
        title="加载设置失败"
        sub={loadError}
        action={<Button onClick={loadAll}>重试</Button>}
      />
    ) : <Spinner />
  }

  return (
    <section>
      <div className="settings-header">
        <h1 className="page-title">设置</h1>
        {saved && <span className="saved-hint" role="status">已保存</span>}
        <Button onClick={save} disabled={saving}>{saving ? '保存中…' : '保存设置'}</Button>
      </div>
      {saveError && <p role="alert" className="test-err">{saveError}</p>}

      <Card className="form-card">
        <h2 className="form-title">闲鱼登录</h2>
        {loggingIn ? (
          <div className="qr-wrap">
            <div className="spinner" />
            <div className="qr-tip">{login.message || '登录中…'}</div>
          </div>
        ) : login.qr ? (
          <div className="qr-wrap">
            <img className="qr-img" src={login.qr} alt="登录二维码" />
            <div className="qr-tip">{login.message || '用闲鱼 App 扫一扫，扫完在手机点确认'}</div>
          </div>
        ) : login.status === 'success' ? (
          <div className="login-row">
            <span className="test-ok">✓ {login.message || '登录成功'}</span>
            <div className="grow" />
            <Button variant="ghost" onClick={() => setConfirmLogout(true)}>
              退出登录
            </Button>
          </div>
        ) : (
          <div className="login-row">
            <span className={'login-state' + (login.expired ? ' err' : login.has_state ? ' on' : '')}>
              {login.expired
                ? `● 登录已过期${login.account ? '（' + login.account + '）' : ''}，请重新扫码`
                : login.has_state
                  ? `● 已登录${login.account ? '：' + login.account : ''}`
                  : '○ 未登录'}
            </span>
            {['expired', 'failed', 'busy'].includes(login.status) && (
              <span className="test-err">{login.message}</span>
            )}
            <div className="grow" />
            {(login.has_state || login.expired) && (
              <Button variant="ghost" onClick={() => setConfirmLogout(true)}>
                退出 / 换号
              </Button>
            )}
            <Button onClick={startLogin} disabled={['waiting'].includes(login.status)}>
              {login.has_state || login.expired ? '重新扫码登录' : '扫码登录'}
            </Button>
          </div>
        )}
      </Card>

      <Card className="form-card">
        <h2 className="form-title">定时与阈值</h2>
        <div className="form-grid">
          <Field label="推荐抓取间隔（分钟）">
            <input
              type="number"
              value={cfg.schedule_minutes ?? ''}
              onChange={(e) => set('schedule_minutes', e.target.value)}
            />
          </Field>
          <Field label="收藏刷新间隔（分钟）">
            <input
              type="number"
              value={cfg.favorites_minutes ?? ''}
              onChange={(e) => set('favorites_minutes', e.target.value)}
            />
          </Field>
          <Field label="降价阈值（%）">
            <input
              type="number"
              value={cfg.min_drop_pct ?? ''}
              onChange={(e) => set('min_drop_pct', e.target.value)}
            />
          </Field>
          <Field label="降价阈值（¥）">
            <input
              type="number"
              value={cfg.min_drop_abs ?? ''}
              onChange={(e) => set('min_drop_abs', e.target.value)}
            />
          </Field>
          <Field label="搜索翻页上限">
            <input
              type="number"
              value={cfg.search_max_pages ?? ''}
              onChange={(e) => set('search_max_pages', e.target.value)}
            />
          </Field>
          <Field label="收藏翻页上限">
            <input
              type="number"
              value={cfg.favorites_max_pages ?? ''}
              onChange={(e) => set('favorites_max_pages', e.target.value)}
            />
          </Field>
        </div>
        <div className="form-row">
          <Toggle checked={cfg.paused} onChange={(v) => set('paused', v)} label="暂停定时任务" />
          {!access?.member && <Toggle checked={cfg.headless} onChange={(v) => set('headless', v)} label="无头浏览器" />}
        </div>
      </Card>

      <Card className="form-card">
        <h2 className="form-title">{access?.member ? '邮件通知' : '邮件通知（SMTP）'}</h2>
        <div className="form-grid">
          <Field
            label="收件邮箱"
            hint={access?.member ? '留空则发往管理员默认邮箱；填写后发到你自己的邮箱' : undefined}
          >
            <input
              value={cfg.notify_to}
              onChange={(e) => set('notify_to', e.target.value)}
              placeholder={access?.member ? '留空使用管理员默认邮箱' : ''}
            />
          </Field>
          {!access?.member && (
            <>
              <Field label="SMTP 服务器">
                <input
                  value={cfg.smtp_host || ''}
                  onChange={(e) => set('smtp_host', e.target.value)}
                  placeholder="smtp.exmail.qq.com"
                />
              </Field>
              <Field label="端口">
                <input
                  type="number"
                  value={cfg.smtp_port ?? ''}
                  onChange={(e) => set('smtp_port', e.target.value)}
                  placeholder="465"
                />
              </Field>
              <Field label="发件账号">
                <input
                  value={cfg.smtp_user || ''}
                  onChange={(e) => set('smtp_user', e.target.value)}
                  placeholder="you@example.com"
                />
              </Field>
              <Field label="密码 / 授权码" hint={cfg.smtp_pass_set ? '已设置，留空则不修改' : '邮箱 SMTP 授权码'}>
                <input
                  type="password"
                  value={pwd}
                  onChange={(e) => setPwd(e.target.value)}
                  placeholder={cfg.smtp_pass_set ? '••••••（已设置）' : ''}
                />
              </Field>
            </>
          )}
        </div>
        <div className="req-field">
          <div className="form-row">
            <Toggle checked={cfg.notify_on_new} onChange={(v) => set('notify_on_new', v)} label="发现新推荐" />
            <Toggle checked={cfg.notify_on_drop} onChange={(v) => set('notify_on_drop', v)} label="收藏降价" />
            <Toggle checked={cfg.notify_on_sold} onChange={(v) => set('notify_on_sold', v)} label="已售出·下架" />
            <Toggle checked={cfg.notify_on_login} onChange={(v) => set('notify_on_login', v)} label="登录失效" />
          </div>
        </div>
        <div className="form-row">
          {testMsg && (
            <span className={testMsg.ok ? 'test-ok' : 'test-err'}>
              {testMsg.ok ? '✓ ' : '✗ '}
              {testMsg.text}
            </span>
          )}
          <div className="grow" />
          <Button variant="ghost" onClick={test} disabled={testing}>
            {testing ? '发送中…' : '发送测试邮件'}
          </Button>
        </div>
      </Card>

      <Card className="form-card">
        <h2 className="form-title">AI 审核</h2>
        <div className="form-grid">
          <Field label="接口地址" hint="OpenAI 兼容地址，留空读取服务器配置">
            {access?.member ? (
              <Select value={cfg.review_base_url || ''} onChange={(value) => set('review_base_url', value)}
                options={access.review_urls.map((url) => ({ value: url, label: url }))} />
            ) : <input
              value={cfg.review_base_url || ''}
              onChange={(e) => set('review_base_url', e.target.value)}
              placeholder="https://api.openai.com/v1"
            />}
          </Field>
          <Field label="模型">
            <input
              value={cfg.review_model || ''}
              onChange={(e) => set('review_model', e.target.value)}
              placeholder="doubao-seed-2.0-pro"
            />
          </Field>
          <Field
            label="API Token"
            hint={cfg.review_token_set ? '已设置，留空则不修改' : '无鉴权可留空'}
          >
            <input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder={cfg.review_token_set ? '••••••（已设置）' : ''}
            />
          </Field>
          <Field label="超时（秒）">
            <input
              type="number"
              value={cfg.review_timeout ?? ''}
              onChange={(e) => set('review_timeout', e.target.value)}
            />
          </Field>
          <Field label="温度">
            <input
              type="number"
              step="0.1"
              value={cfg.review_temperature ?? ''}
              onChange={(e) => set('review_temperature', e.target.value)}
            />
          </Field>
          <Field label="最大 tokens">
            <input
              type="number"
              value={cfg.review_max_tokens ?? ''}
              onChange={(e) => set('review_max_tokens', e.target.value)}
            />
          </Field>
        </div>
        <div className="req-field">
          <Field label="系统提示词" hint="留空恢复默认">
            <textarea
              className="req-input"
              rows={4}
              value={cfg.review_system_prompt || ''}
              onChange={(e) => set('review_system_prompt', e.target.value)}
            />
          </Field>
        </div>
        <div className="form-row">
          <Toggle
            checked={cfg.review_enabled}
            onChange={(v) => set('review_enabled', v)}
            label="启用 AI 审核"
          />
          <span className="field-hint">关闭后不调用模型，候选全部留给本人审核，也不需要 API Key</span>
          {llmMsg && (
            <span className={llmMsg.ok ? 'test-ok' : 'test-err'}>
              {llmMsg.ok ? '✓ ' : '✗ '}
              {llmMsg.text}
            </span>
          )}
          <div className="grow" />
          <Button variant="ghost" onClick={testLLM} disabled={llmTesting}>
            {llmTesting ? '测试中…' : '测试 AI 审核'}
          </Button>
        </div>
      </Card>

      {!access?.member && <Card className="form-card">
        <h2 className="form-title">高级抓取设置</h2>
        <div className="form-grid">
          <Field label="操作延迟下限（秒）">
            <input
              type="number"
              step="0.5"
              value={cfg.action_delay_min ?? ''}
              onChange={(e) => set('action_delay_min', e.target.value)}
            />
          </Field>
          <Field label="操作延迟上限（秒）">
            <input
              type="number"
              step="0.5"
              value={cfg.action_delay_max ?? ''}
              onChange={(e) => set('action_delay_max', e.target.value)}
            />
          </Field>
          <Field label="死链核活上限（条/轮）">
            <input
              type="number"
              value={cfg.liveness_max_checks ?? ''}
              onChange={(e) => set('liveness_max_checks', e.target.value)}
            />
          </Field>
          <Field label="搜索页 URL">
            <input value={cfg.search_url || ''} onChange={(e) => set('search_url', e.target.value)} />
          </Field>
          <Field label="收藏页 URL">
            <input
              value={cfg.favorites_url || ''}
              onChange={(e) => set('favorites_url', e.target.value)}
            />
          </Field>
        </div>
      </Card>}

      <Card className="form-card">
        <h2 className="form-title">运行状态</h2>
        <div className="status-grid">
          <div>
            <span className="status-k">当前</span>
            <span className="status-v">{status?.running ? '运行中' : '空闲'}</span>
          </div>
          <div>
            <span className="status-k">间隔</span>
            <span className="status-v">{status?.schedule_minutes ?? cfg.schedule_minutes} 分钟</span>
          </div>
          <div>
            <span className="status-k">定时</span>
            <span className="status-v">{cfg.paused ? '已暂停' : '运行中'}</span>
          </div>
          <div>
            <span className="status-k">版本</span>
            <span className="status-v" title={status?.build_time ? fmtDateTime(status.build_time) : ''}>
              {status?.version || 'dev'}
            </span>
          </div>
        </div>
        {status?.last && (
          <div className="last-run">
            上轮：{status.last.error
              ? `出错 — ${status.last.error}`
              : `搜索 ${status.last.raw ?? 0} · 命中 ${status.last.scanned ?? 0} · 新推荐 ${status.last.recommendations ?? 0} · 降价 ${status.last.drops ?? 0} · 已通知 ${status.last.notified ?? 0}`}
          </div>
        )}
      </Card>

      <ConfirmDialog
        open={confirmLogout}
        danger
        title="退出登录 / 换号"
        message="确定退出并清除本地登录态？下次需要重新扫码登录。"
        confirmText="退出"
        onConfirm={logout}
        onCancel={() => setConfirmLogout(false)}
      />
    </section>
  )
}
