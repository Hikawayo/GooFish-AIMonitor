import { useEffect, useRef, useState } from 'react'

const KEY_W = 'xy-folder-w'
const KEY_C = 'xy-folder-collapsed'
const MIN = 200
const MAX = 460
const DEFAULT = 280

const read = (key) => {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

const write = (key, value) => {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* 隐私模式下记不住, 只在本次生效 */
  }
}

/**
 * 右侧文件夹栏: 拖动分割条调宽度, 点一下收起/展开。宽度与收起状态只记在本机。
 * 手机宽度下直接变成上方一行横向滚动, 不出现分割条。
 */
export default function FolderLayout({ folders, children }) {
  const [width, setWidth] = useState(() => Number(read(KEY_W)) || DEFAULT)
  const [collapsed, setCollapsed] = useState(() => read(KEY_C) === '1')
  const [dragging, setDragging] = useState(false)
  const drag = useRef(null)

  useEffect(() => write(KEY_W, String(width)), [width])
  useEffect(() => write(KEY_C, collapsed ? '1' : '0'), [collapsed])

  useEffect(() => {
    if (!dragging) return undefined
    const move = (event) => {
      const state = drag.current
      if (!state) return
      const dx = event.clientX - state.x
      if (Math.abs(dx) > 3) state.moved = true
      setWidth(Math.min(MAX, Math.max(MIN, state.width - dx)))
    }
    const up = () => {
      if (drag.current && !drag.current.moved) setCollapsed((value) => !value)
      drag.current = null
      setDragging(false)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', up)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', up)
    }
  }, [dragging])

  const start = (event) => {
    event.preventDefault()
    drag.current = { x: event.clientX, width: collapsed ? 0 : width, moved: false }
    setDragging(true)
  }

  return (
    <div className="folder-layout" data-collapsed={collapsed ? '1' : '0'}
      style={{ '--folder-w': `${collapsed ? 0 : width}px` }}>
      <div className="folder-results">{children}</div>
      <div
        className="folder-split"
        role="separator"
        aria-label={collapsed ? '展开文件夹' : '调整文件夹宽度'}
        aria-orientation="vertical"
        title={collapsed ? '展开文件夹' : '拖动调整宽度 · 点击收起'}
        data-drag={dragging ? '1' : '0'}
        onPointerDown={start}
      >
        <i className={`ti ${collapsed ? 'ti-layout-sidebar-right-expand' : 'ti-grip-vertical'}`} />
      </div>
      {folders}
    </div>
  )
}
