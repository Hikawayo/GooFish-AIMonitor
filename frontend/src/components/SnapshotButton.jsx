import { useState } from 'react'
import { toPng } from 'html-to-image'

const pad = (value) => String(value).padStart(2, '0')

function stamp() {
  const d = new Date()
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}`
}

const safeName = (name) => (name || '快照').replace(/[\\/:*?"<>|]/g, '-').slice(0, 60)

// 快照按桌面宽度排版: 卡片一行 4 个, 而不是照搬手机上的单列长图
const SNAP_WIDTH = 1180

/**
 * 把指定容器(总趋势图 + 商品卡)导出成一张 PNG。
 * 用浏览器自己的渲染(html-to-image), 所以和当前主题、字体、图表一致。
 */
export default function SnapshotButton({ target, name, onToast }) {
  const [busy, setBusy] = useState(false)

  const shoot = async () => {
    const node = target?.current
    if (!node) return
    setBusy(true)

    const previous = { width: node.style.width, maxWidth: node.style.maxWidth }
    const themeVars = []
    const app = document.getElementById('app')
    if (app) {
      // 主题色是挂在 #app 上的 CSS 变量; 克隆出去的子树里没有它们, 图表会掉色/丢线
      for (const varName of Array.from(app.style)) {
        if (!varName.startsWith('--')) continue
        const value = app.style.getPropertyValue(varName)
        themeVars.push([varName, value])
        node.style.setProperty(varName, value)
      }
    }
    node.style.width = `${SNAP_WIDTH}px`
    node.style.maxWidth = 'none'
    // 类要加在快照节点上: 克隆的是这棵子树, 挂在 body 上的规则进不去
    node.classList.add('snapping')

    // 拖拽手柄用内联 display 隐藏: 只靠 CSS 类在克隆里不一定生效, 露出来就是黑色药丸
    const grips = Array.from(node.querySelectorAll('.trend-grip'))
    grips.forEach((el) => { el.style.display = 'none' })

    // 图表内容在 <g clip-path="url(#...)"> 里, 克隆成 SVG 后引用会失效 → 整组被裁掉
    const clipped = Array.from(node.querySelectorAll('g[clip-path]'))
      .map((group) => [group, group.getAttribute('clip-path')])
    clipped.forEach(([group]) => group.removeAttribute('clip-path'))

    // 图表按容器宽度重绘(ResizeObserver → setState), 等它排好再截
    await new Promise((resolve) => setTimeout(resolve, 420))

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
      grips.forEach((el) => { el.style.display = '' })
      clipped.forEach(([group, attr]) => { if (attr) group.setAttribute('clip-path', attr) })
      for (const [varName] of themeVars) node.style.removeProperty(varName)
      node.style.width = previous.width
      node.style.maxWidth = previous.maxWidth
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
