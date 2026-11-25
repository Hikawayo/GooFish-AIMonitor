import { useState } from 'react'
import { Button } from './ui'
import { LIGHT, PRESETS, themeVars } from '../theme'

const FIELDS = [
  ['bg', '背景'],
  ['fg', '文字'],
  ['acc', '强调'],
]

function Preview({ palette }) {
  return (
    <div className="theme-preview" style={themeVars(palette)} aria-hidden="true">
      <div className="theme-preview-card">
        <div className="theme-preview-title">示例商品标题</div>
        <div className="theme-preview-price">¥1,280</div>
        <div className="theme-preview-actions">
          <span className="theme-preview-primary">站内收藏</span>
          <span className="theme-preview-ghost">忽略</span>
        </div>
      </div>
    </div>
  )
}

export default function ThemeEditor({ activeKey, initial, onPickPreset, onSave, onClose }) {
  const [palette, setPalette] = useState(initial ?? { ...LIGHT })
  const set = (key, value) => setPalette((current) => ({ ...current, [key]: value }))

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal theme-dialog" role="dialog" aria-label="外观主题" onClick={(e) => e.stopPropagation()}>
        <div className="modal-title">外观主题</div>
        <div className="theme-preset-grid">
          {PRESETS.map((preset) => (
            <button
              key={preset.key}
              type="button"
              className={'theme-preset-chip' + (activeKey === preset.key ? ' on' : '')}
              aria-pressed={activeKey === preset.key}
              onClick={() => {
                setPalette({ bg: preset.bg, fg: preset.fg, acc: preset.acc })
                onPickPreset?.(preset.key)
              }}
            >
              <span
                className="theme-preset-dot"
                style={{ background: `linear-gradient(135deg, ${preset.bg} 0 50%, ${preset.acc} 50% 100%)` }}
              />
              <span>{preset.name}</span>
            </button>
          ))}
        </div>
        <div className="theme-colors">
          {FIELDS.map(([key, label]) => (
            <label className="color-field" key={key}>
              <span className="field-label">{label}</span>
              <span className="color-input">
                <input type="color" value={palette[key]} aria-label={label}
                  onChange={(event) => set(key, event.target.value)} />
                <code>{palette[key]}</code>
              </span>
            </label>
          ))}
        </div>
        <Preview palette={palette} />
        <div className="modal-actions">
          <Button variant="ghost" onClick={onClose}>关闭</Button>
          <Button onClick={() => onSave(palette)}>保存自定义</Button>
        </div>
      </div>
    </div>
  )
}

