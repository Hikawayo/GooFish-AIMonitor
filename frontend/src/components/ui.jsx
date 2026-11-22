import { imgSrc } from '../util'

export function Button({ variant = 'primary', className = '', children, ...p }) {
  return (
    <button className={`btn btn-${variant} ${className}`} {...p}>
      {children}
    </button>
  )
}

export function Card({ className = '', children }) {
  return <div className={`card ${className}`}>{children}</div>
}

export function Badge({ tone = '', children }) {
  return <span className={`badge ${tone ? `badge-${tone}` : ''}`}>{children}</span>
}

// 卖家: 首字母圆点做视觉锚点, 昵称用正常文字色; aria-label 保留「卖家」语义
export function Seller({ nick }) {  if (!nick) return null
  return (
    <span className="seller" aria-label={`卖家 ${nick}`} title={`卖家 ${nick}`}>
      <span className="seller-av" aria-hidden="true">{nick[0]}</span>
      <span className="seller-name">{nick}</span>
    </span>
  )
}

// 模板抽取到的属性: 只在有值时出现, 通用条件永远看不到这一行
export function Attrs({ attrs }) {
  if (!attrs) return null
  const tags = []
  if (attrs.seat && attrs.seat !== '未知') tags.push(attrs.seat)
  if (attrs.qty > 1) tags.push(`${attrs.qty} 张`)
  if (attrs.bundle) tags.push('捆绑')
  if (attrs.deposit) tags.push('定金')
  if (attrs.unit === '合计') tags.push('合计价')
  if (!tags.length) return null
  return <div className="rec-attrs">{tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
}

export function Spinner() {
  return (
    <div className="spinner-wrap">
      <div className="spinner" />
    </div>
  )
}

export function EmptyState({ title, sub }) {
  return (
    <div className="empty">
      <div className="empty-title">{title}</div>
      {sub && <div className="empty-sub">{sub}</div>}
    </div>
  )
}

export function Toggle({ checked, onChange, label, ariaLabel }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={!!checked} aria-label={ariaLabel} onChange={(e) => onChange(e.target.checked)} />
      <span className="track" />
      {label && <span className="tog-label">{label}</span>}
    </label>
  )
}

export function Field({ label, hint, children }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  )
}

// items: [['发布', '3天前'], ...] — 自动过滤空值
export function TimeMeta({ items }) {
  const shown = (items || []).filter(([, v]) => v)
  if (!shown.length) return null
  return (
    <div className="time-meta">
      {shown.map(([k, v]) => (
        <span key={k} className="tm-item">
          <span className="tm-k">{k}</span>
          {v}
        </span>
      ))}
    </div>
  )
}

// 统一的应用内对话框, 取代原生 window.confirm/alert(那些带 "localhost:8000 显示" 的丑框)
export function ConfirmDialog({
  open,
  title,
  message,
  confirmText = '确定',
  cancelText = '取消',
  danger = false,
  onConfirm,
  onCancel,
}) {
  if (!open) return null
  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" role="dialog" onClick={(e) => e.stopPropagation()}>
        {title && <div className="modal-title">{title}</div>}
        {message && <div className="modal-body">{message}</div>}
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onCancel}>
            {cancelText}
          </button>
          <button className={'btn ' + (danger ? 'btn-danger-solid' : 'btn-primary')} onClick={onConfirm}>
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  )
}

export function Thumb({ url, dead = false, deadReason = '' }) {
  const cls = `thumb${url ? '' : ' thumb-empty'}${dead ? ' thumb-dead' : ''}`
  return (
    <div className={cls}>
      {url && (
        <img
          src={imgSrc(url)}
          alt=""
          loading="lazy"
          onError={(e) => {
            e.currentTarget.style.display = 'none'
          }}
        />
      )}
      {dead && <span className="thumb-dead-label">{deadReason || '已下架'}</span>}
    </div>
  )
}
