import { useEffect, useState } from 'react'
import { api } from '../api'
import Select from '../components/Select'
import { Card, Button, Badge, Spinner, EmptyState, Toggle, Field } from '../components/ui'
import { splitCsv } from '../util'

const blank = () => ({
  id: null,
  name: '',
  keywordsText: '',
  price_min: '',
  price_max: '',
  city: '',
  conditionText: '',
  requirement: '',
  kind: 'general',
  free_shipping: false,
  enabled: true,
  public: false,
  folderId: '',
})

export default function Watches() {
  const [list, setList] = useState(null)
  const [form, setForm] = useState(blank())
  const [folders, setFolders] = useState([])
  const [folderName, setFolderName] = useState('')
  const [error, setError] = useState('')

  const load = () => api.watches().then(setList)
  useEffect(() => {
    load().catch((error) => setError(error.message))
    api.folders().then(setFolders).catch((error) => setError(error.message))
  }, [])

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const save = async () => {
    if (!form.name.trim() || !form.keywordsText.trim()) return
    const body = {
      name: form.name.trim(),
      keywords: splitCsv(form.keywordsText),
      price_min: form.price_min === '' ? null : Number(form.price_min),
      price_max: form.price_max === '' ? null : Number(form.price_max),
      city: form.city.trim() || null,
      condition: form.conditionText.trim() ? splitCsv(form.conditionText) : null,
      requirement: form.requirement.trim() || null,
      kind: form.kind,
      free_shipping: form.free_shipping || null,
      enabled: form.enabled,
      public: form.public,
      folder_id: form.folderId === '' ? null : Number(form.folderId),
    }
    try {
      if (form.id) await api.updateWatch(form.id, body)
      else await api.createWatch(body)
      setForm(blank())
      setError('')
      await load()
    } catch (error) {
      setError(error.message)
    }
  }

  const createFolder = async () => {
    try {
      const folder = await api.createFolder(folderName)
      setFolders(await api.folders())
      set('folderId', String(folder.id))
      setFolderName('')
      setError('')
    } catch (error) {
      setError(error.message)
    }
  }

  const edit = (w) =>
    setForm({
      id: w.id,
      name: w.name,
      keywordsText: (w.keywords || []).join(', '),
      price_min: w.price_min ?? '',
      price_max: w.price_max ?? '',
      city: w.city ?? '',
      conditionText: (w.condition || []).join(', '),
      requirement: w.requirement ?? '',
      kind: w.kind ?? 'general',
      free_shipping: !!w.free_shipping,
      enabled: w.enabled,
      public: w.public,
      folderId: w.folder_id == null ? '' : String(w.folder_id),
    })

  const toggleEnabled = async (w) => {
    await api.updateWatch(w.id, {
      name: w.name,
      keywords: w.keywords,
      price_min: w.price_min,
      price_max: w.price_max,
      city: w.city,
      condition: w.condition,
      requirement: w.requirement,
      kind: w.kind,
      free_shipping: w.free_shipping,
      enabled: !w.enabled,
      public: w.public,
      folder_id: w.folder_id,
    })
    load()
  }

  const remove = async (id) => {
    await api.deleteWatch(id)
    load()
  }

  if (list === null) return <Spinner />

  return (
    <section>
      <h1 className="page-title">监控条件</h1>
      {error && <p role="alert" className="test-err">{error}</p>}

      <Card className="form-card">
        <div className="form-title">{form.id ? '编辑条件' : '新增条件'}</div>
        <div className="form-grid">
          <Field label="名称">
            <input value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="iPhone15Pro" />
          </Field>
          <Field label="搜索词" hint="所有词会合成一次搜索">
            <input
              value={form.keywordsText}
              onChange={(e) => set('keywordsText', e.target.value)}
              placeholder="MacBook Pro M1 Pro 16寸 32G 1T"
            />
          </Field>
          <Field label="模板" hint="票务才抽取席种/张数，通用不做额外字段">
            <Select value={form.kind} onChange={(value) => set('kind', value)}
              options={[{ value: 'general', label: '通用商品' }, { value: 'ticket', label: '票务' }]} />
          </Field>
          <Field label="最低价">
            <input type="number" value={form.price_min} onChange={(e) => set('price_min', e.target.value)} />
          </Field>
          <Field label="最高价">
            <input type="number" value={form.price_max} onChange={(e) => set('price_max', e.target.value)} />
          </Field>
          <Field label="城市（可选）">
            <input value={form.city} onChange={(e) => set('city', e.target.value)} placeholder="上海" />
          </Field>
          <Field label="文件夹">
            <Select value={form.folderId} onChange={(value) => set('folderId', value)}
              options={[{ value: '', label: '使用条件名称' },
                ...folders.map((folder) => ({ value: String(folder.id), label: folder.name }))]} />
          </Field>
          <Field label="可见性">
            <Select value={form.public ? 'public' : 'private'} onChange={(value) => set('public', value === 'public')}
              options={[{ value: 'private', label: '私密 · 仅自己' },
                { value: 'public', label: '公开 · 本站登录用户' }]} />
          </Field>
          <Field label="成色（用逗号分隔）">
            <input
              value={form.conditionText}
              onChange={(e) => set('conditionText', e.target.value)}
              placeholder="99新, 几乎全新"
            />
          </Field>
        </div>
        <div className="form-row">
          <Field label="新建文件夹">
            <input value={folderName} maxLength={80} onChange={(e) => setFolderName(e.target.value)} />
          </Field>
          <Button variant="ghost" disabled={!folderName.trim()} onClick={createFolder}>添加文件夹</Button>
        </div>
        <div className="req-field">
          <Field label="AI 审核要求（可选）">
            <textarea
              className="req-input"
              rows={3}
              value={form.requirement}
              onChange={(e) => set('requirement', e.target.value)}
              placeholder="例如：只要 14 寸 M5 Pro 本机，排除配件"
            />
          </Field>
        </div>
        <div className="form-row">
          <Toggle checked={form.free_shipping} onChange={(v) => set('free_shipping', v)} label="仅包邮" />
          <Toggle checked={form.enabled} onChange={(v) => set('enabled', v)} label="启用" />
          <div className="grow" />
          {form.id && (
            <Button variant="ghost" onClick={() => setForm(blank())}>
              取消
            </Button>
          )}
          <Button onClick={save}>{form.id ? '保存' : '添加'}</Button>
        </div>
      </Card>

      {list.length === 0 ? (
        <EmptyState title="还没有监控条件" />
      ) : (
        <div className="watch-list">
          {list.map((w) => (
            <Card key={w.id} className="watch-row">
              <div className="watch-main">
                <div className="watch-name">{w.name}</div>
                <div className="watch-kw">{(w.keywords || []).join(' · ')}</div>
                <div className="rec-meta">
                  {folders.find((folder) => folder.id === w.folder_id)?.name}
                  <span>{w.public ? '公开' : '私密'}</span>
                  {(w.price_min || w.price_max) && (
                    <span>
                      ¥{w.price_min ?? 0} – {w.price_max ?? '∞'}
                    </span>
                  )}
                  {w.city && <span>{w.city}</span>}
                  {w.free_shipping && <Badge>包邮</Badge>}
                  {(w.condition || []).map((c) => (
                    <span key={c}>{c}</span>
                  ))}
                </div>
                {w.requirement && (
                  <details className="watch-req">
                    <summary>AI 审核要求</summary>
                    <p>{w.requirement}</p>
                  </details>
                )}
              </div>
              <div className="watch-actions">
                <Toggle checked={w.enabled} onChange={() => toggleEnabled(w)} ariaLabel={`启用 ${w.name}`} />
                <Button variant="ghost" className="btn-sm" onClick={() => edit(w)}>
                  编辑
                </Button>
                <Button variant="ghost" className="btn-sm btn-danger" onClick={() => remove(w.id)}>
                  删除
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </section>
  )
}
