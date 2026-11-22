import { useEffect, useRef, useState } from 'react'

/**
 * 站内统一下拉框: 原生 <select> 的弹层跟网站样式完全脱节, 所以自己画一个。
 * options: [{ value, label }]; value 必须能在 options 里找到。
 */
export default function Select({ value, options, onChange, ariaLabel, align = 'left', className = '', disabled = false }) {
  const [open, setOpen] = useState(false)
  const box = useRef(null)
  const current = options.find((option) => option.value === value) ?? options[0]

  useEffect(() => {
    if (!open) return undefined
    const onPointer = (event) => {
      if (!box.current?.contains(event.target)) setOpen(false)
    }
    const onKey = (event) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const pick = (next) => {
    onChange(next)
    setOpen(false)
  }

  return (
    <div className={`select${align === 'right' ? ' select-right' : ''}${className ? ` ${className}` : ''}`} ref={box}>
      <button type="button" className="select-btn" aria-haspopup="listbox" aria-expanded={open}
        aria-label={ariaLabel} disabled={disabled} onClick={() => setOpen((value) => !value)}>
        <span className="select-value">{current?.label}</span>
        <i className="ti ti-chevron-down" aria-hidden="true" />
      </button>
      {open && (
        <div className="select-menu" role="listbox" aria-label={ariaLabel}>
          {options.map((option) => (
            <button key={option.value} type="button" role="option"
              aria-selected={option.value === current?.value}
              className={option.value === current?.value ? 'on' : ''}
              onClick={() => pick(option.value)}>
              <span>{option.label}</span>
              {option.value === current?.value && <i className="ti ti-check" aria-hidden="true" />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
