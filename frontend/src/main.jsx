import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import './styles.css'

// 兜底: 渲染抛错时给出可操作的提示, 而不是整页白屏
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('页面渲染出错', error, info?.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="crash">
        <h1>页面出错了</h1>
        <p>刷新一下通常就好；如果反复出现，把下面这行发给维护者。</p>
        <code>{String(this.state.error?.message || this.state.error)}</code>
        <button type="button" onClick={() => window.location.reload()}>刷新页面</button>
      </div>
    )
  }
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ErrorBoundary>
  </React.StrictMode>
)
