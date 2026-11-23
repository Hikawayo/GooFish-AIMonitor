import { useState } from 'react'
import { toPng } from 'html-to-image'

const pad = (value) => String(value).padStart(2, '0')

function stamp() {
  const d = new Date()
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}`
}

const safeName = (name) => (name || '快照').replace(/[\\/:*?"<>|]/g, '-').slice(0, 60)

/**
 * 把指定容器(总趋势图 + 商品卡)导出成一张 PNG。
 * 用的是浏览器自己的渲染(html-to-image), 所以和当前主题、字体、图表完全一致。
 */
export default function SnapshotButton({ target, name, onToast }) {
  const [busy, setBusy] = useState(false)

  const shoot = async () => {
    const node = target?.current
    if (!node) return
    setBusy(true)
    // 类要加在快照节点上: 克隆的是这棵子树, 挂在 body 上的规则进不去\n    node.classList.add('snapping')
    // 主题色是挂在 #app 上的 CSS 变量; 克隆出去的子树里没有它们, 图表会掉色/丢线
    const themeVars = []
    const app = document.getElementById('app')
    if (app) {
      for (const name of Array.from(app.style)) {
        if (!name.startsWith('--')) continue
        const value = app.style.getPropertyValue(name)
        themeVars.push([name, value])
        node.style.setProperty(name, value)
      }
    }
    // 图表内容包在 <g clip-path="url(#...)"> 里; 克隆成 SVG 后这个引用会失效,
    // 整组被裁掉 → 截图里只剩坐标文字。截之前临时摘掉, 截完还原。
    const clipped = Array.from(node.querySelectorAll('g[clip-path]'))
      .map((group) => [group, group.getAttribute('clip-path')])
    clipped.forEach(([group]) => group.removeAttribute('clip-path'))
    try {
      const dataUrl = await toPng(node, {
        cacheBust: true,
        pixelRatio: 2,
        backgroundColor: app ? getComputedStyle(app).backgroundColor : undefined,
      })
      const link = document.createElement('a')
      link.download = `${safeName(name)}-${stamp()}.png`
      link.href = dataUrl
      link.click()
      onToast?.('快照已导出')
    } catch (error) {
      onToast?.(`快照失败：${error.message || error}`)
    } finally {
      clipped.forEach(([group, attr]) => { if (attr) group.setAttribute('clip-path', attr) })
      for (const [key] of themeVars) node.style.removeProperty(key)
      node.classList.remove('snapping')
      setBusy(false)
    }
  }

  return (
    <button type="button" className="icon-btn snapshot-btn" disabled={busy}
      title={busy ? '正在生成快照…' : '导出快照（趋势图 + 商品）'} aria-label="导出快照" onClick={shoot}>
      <i className={`ti ${busy ? 'ti-loader-2' : 'ti-camera'}`} />
    </button>
  )
}
