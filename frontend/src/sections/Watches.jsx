import { useEffect, useState } from 'react'
import { api } from '../api'
import Select from '../components/Select'
import { Card, Button, Badge, Spinner, EmptyState, Toggle, Field, ConfirmDialog } from '../components/ui'
import { splitCsv } from '../util'

const blank = () => ({
  id: null,
  name: '',
  keywordsText: '',
  price_min: '',
  price_max: '',
  target_price: '',
  city: '',
  conditionText: '',
  requirement: '',
  kind: 'general',
  free_shipping: false,
  enabled: true,
  archived: false,
  public: false,
  folderId: '',
})

export default function Watches() {
  const [list, setList] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [form, setForm] = useState(blank())
  const [saving, setSaving] = useState(false)
  const [folders, setFolders] = useState([])
  const [folderName, setFolderName] = useState('')
  const [renamingFolder, setRenamingFolder] = useState(null) // { id, name }
  const [confirmDeleteWatch, setConfirmDeleteWatch] = useState(null) // watch row
  const [confirmDeleteFolder, setConfirmDeleteFolder] = useState(null) // folder row
  const [error, setError] = useState('')

  const load = () =>
    api.watches()
      .then((data) => {
        setLoadError('')
        setList(data)
      })
      .catch((err) => setLoadError(err.message || '加载条件失败'))

  const loadFolders = () =>
    api.folders().then(setFolders).catch((err) => setError(err.message))

  useEffect(() => {
    load()
    loadFolders()
  }, [])

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const save = async () => {
    if (saving || !form.name.trim() || !form.keywordsText.trim()) return
    const pMin = form.price_min === '' ? null : Number(form.price_min)
    const pMax = form.price_max === '' ? null : Number(form.price_max)
    const targetPrice = form.target_price === '' ? null : Number(form.target_price)
    if (pMin !== null && pMax !== null && pMin > pMax) {
      setError('最低价不能大于最高价')
      return
    }
    const body = {
      name: form.name.trim(),
      keywords: splitCsv(form.keywordsText),
      price_min: pMin,
      price_max: pMax,
      target_price: targetPrice,
      city: form.city.trim() || null,
      condition: form.conditionText.trim() ? splitCsv(form.conditionText) : null,
      requirement: form.requirement.trim() || null,
      kind: form.kind,
      free_shipping: form.free_shipping || null,
      enabled: form.enabled,
      archived: form.archived,
      public: form.public,
      folder_id: form.folderId === '' ? null : Number(form.folderId),
    }
    setSaving(true)
    try {
      if (form.id) await api.updateWatch(form.id, body)
      else await api.createWatch(body)
      setForm(blank())
      setError('')
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const createFolder = async () => {
    if (!folderName.trim()) return
    try {
      const folder = await api.createFolder(folderName)
      setFolders(await api.folders())
      set('folderId', String(folder.id))
      setFolderName('')
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }

  const saveFolderRename = async () => {
    if (!renamingFolder || !renamingFolder.name.trim()) return
    try {
      await api.renameFolder(renamingFolder.id, renamingFolder.name)
      setRenamingFolder(null)
      setError('')
      await loadFolders()
    } catch (err) {
      setError(err.message)
    }
  }

  const removeFolder = async () => {
    if (!confirmDeleteFolder) return
    const target = confirmDeleteFolder
    setConfirmDeleteFolder(null)
    try {
      await api.deleteFolder(target.id)
      if (form.folderId === String(target.id)) set('folderId', '')
      setError('')
      await Promise.all([loadFolders(), load()])
    } catch (err) {
      setError(err.message)
    }
  }

  const edit = (w) =>
    setForm({
      id: w.id,
      name: w.name,
      keywordsText: (w.keywords || []).join(', '),
      price_min: w.price_min ?? '',
      price_max: w.price_max ?? '',
      target_price: w.target_price ?? '',
      city: w.city ?? '',
      conditionText: (w.condition || []).join(', '),
      requirement: w.requirement ?? '',
      kind: w.kind ?? 'general',
      free_shipping: !!w.free_shipping,
      enabled: w.enabled,
      archived: !!w.archived,
      public: w.public,
      folderId: w.folder_id == null ? '' : String(w.folder_id),
    })

  const toggleEnabled = async (w) => {
    try {
      await api.updateWatch(w.id, {
        name: w.name,
        keywords: w.keywords,
        price_min: w.price_min,
        price_max: w.price_max,
        target_price: w.target_price,
        city: w.city,
        condition: w.condition,
        requirement: w.requirement,
        kind: w.kind,
        free_shipping: w.free_shipping,
        enabled: !w.enabled,
        archived: !!w.archived,
        public: w.public,
        folder_id: w.folder_id,
      })
      setError('')
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  const toggleArchived = async (w) => {
    try {
      await api.updateWatch(w.id, {
        name: w.name,
        keywords: w.keywords,
        price_min: w.price_min,
        price_max: w.price_max,
        target_price: w.target_price,
        city: w.city,
        condition: w.condition,
        requirement: w.requirement,
        kind: w.kind,
        free_shipping: w.free_shipping,
        enabled: w.archived ? true : false,
        archived: !w.archived,
        public: w.public,
        folder_id: w.folder_id,
      })
      setError('')
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  const remove = async () => {
    if (!confirmDeleteWatch) return
    const target = confirmDeleteWatch
    setConfirmDeleteWatch(null)
    try {
      await api.deleteWatch(target.id)
      if (form.id === target.id) setForm(blank())
      setError('')
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  if (list === null) {
    return loadError ? (
      <EmptyState
        title="加载条件失败"
        sub={loadError}
        action={<Button onClick={load}>重试</Button>}
      />
    ) : <Spinner />
  }

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
          <Field label="目标价提醒（可选）" hint="命中该价格及以下立即提醒">
            <input type="number" value={form.target_price} onChange={(e) => set('target_price', e.target.value)} placeholder="如 1000" />
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
          <Button onClick={save} disabled={saving || !form.name.trim() || !form.keywordsText.trim()}>
            {saving ? '保存中…' : form.id ? '保存' : '添加'}
          </Button>
        </div>
      </Card>

      {folders.length > 0 && (
        <Card className="form-card">
          <div className="form-title">文件夹管理</div>
          <div className="watch-list">
            {folders.map((folder) => (
              <div key={folder.id} className="form-row">
                {renamingFolder?.id === folder.id ? (
                  <>
                    <input
                      className="text-input"
                      style={{ flex: 1, minWidth: 160 }}
                      value={renamingFolder.name}
                      maxLength={80}
                      onChange={(e) => setRenamingFolder({ ...renamingFolder, name: e.target.value })}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && renamingFolder.name.trim()) saveFolderRename()
                        if (e.key === 'Escape') setRenamingFolder(null)
                      }}
                    />
                    <Button className="btn-sm" onClick={saveFolderRename} disabled={!renamingFolder.name.trim()}>
                      保存
                    </Button>
                    <Button variant="ghost" className="btn-sm" onClick={() => setRenamingFolder(null)}>
                      取消
                    </Button>
                  </>
                ) : (
                  <>
                    <span className="watch-name">{folder.name}</span>
                    <div className="grow" />
                    <Button
                      variant="ghost"
                      className="btn-sm"
                      onClick={() => setRenamingFolder({ id: folder.id, name: folder.name })}
                    >
                      改名
                    </Button>
                    <Button
                      variant="ghost"
                      className="btn-sm btn-danger"
                      onClick={() => setConfirmDeleteFolder(folder)}
                    >
                      删除
                    </Button>
                  </>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

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
                  {w.target_price != null && <Badge tone="drop">目标 ≤ ¥{w.target_price}</Badge>}
                  {w.archived && <Badge>已归档</Badge>}
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
                <Button variant="ghost" className="btn-sm" onClick={() => toggleArchived(w)}>
                  {w.archived ? '恢复' : '归档'}
                </Button>
                <Button variant="ghost" className="btn-sm" onClick={() => edit(w)}>
                  编辑
                </Button>
                <Button variant="ghost" className="btn-sm btn-danger" onClick={() => setConfirmDeleteWatch(w)}>
                  删除
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={!!confirmDeleteWatch}
        danger
        title="删除监控条件"
        message={confirmDeleteWatch ? `确定删除条件「${confirmDeleteWatch.name}」？` : ''}
        confirmText="删除"
        onConfirm={remove}
        onCancel={() => setConfirmDeleteWatch(null)}
      />
      <ConfirmDialog
        open={!!confirmDeleteFolder}
        danger
        title="删除文件夹"
        message={confirmDeleteFolder ? `确定删除文件夹「${confirmDeleteFolder.name}」？该文件夹下的条件会保留并转为未归档。` : ''}
        confirmText="删除"
        onConfirm={removeFolder}
        onCancel={() => setConfirmDeleteFolder(null)}
      />
    </section>
  )
}
