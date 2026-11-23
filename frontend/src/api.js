const authListeners = new Set()

export const onAuthExpired = (fn) => {
  authListeners.add(fn)
  return () => authListeners.delete(fn)
}

const notifyAuthExpired = (message) => {
  const err = new Error(message || '登录已过期，请刷新页面重新登录')
  err.authExpired = true
  authListeners.forEach((fn) => {
    try {
      fn(err.message)
    } catch {
      /* ignore listener errors */
    }
  })
  return err
}

const J = async (response) => {
  if (response.status === 401) {
    throw notifyAuthExpired('登录已过期，请刷新页面重新登录')
  }
  const ct = (response.headers.get('content-type') || '').toLowerCase()
  if (!ct.includes('application/json')) {
    if (response.redirected || ct.includes('text/html')) {
      throw notifyAuthExpired('登录已过期，请刷新页面重新登录')
    }
    throw new Error(response.ok ? '服务响应格式异常' : `请求失败（${response.status}）`)
  }
  const data = await response.json()
  if (!response.ok) {
    throw new Error(typeof data.detail === 'string' ? data.detail : '操作失败')
  }
  return data
}
const post = (url, body) =>
  fetch(url, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  }).then(J)

export const api = {
  access: () => fetch('/api/access').then(J),
  folders: () => fetch('/api/watch-folders').then(J),
  createFolder: (name) => post('/api/watch-folders', { name }),
  renameFolder: (id, name) =>
    fetch(`/api/watch-folders/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }).then(J),
  deleteFolder: (id) => fetch(`/api/watch-folders/${id}`, { method: 'DELETE' }).then(J),
  shared: () => fetch('/api/shared').then(J),
  prices: (item, folder) => fetch(folder
    ? `/api/shared/${encodeURIComponent(folder)}/${encodeURIComponent(item)}/prices`
    : `/api/items/${encodeURIComponent(item)}/prices`).then(J),
  priceTrend: (watchIds, mode, tz, minPrice, seat) =>
    fetch(`/api/price-trend?watch_ids=${encodeURIComponent(watchIds)}&mode=${mode}&tz=${tz}`
      + (minPrice ? `&min_price=${encodeURIComponent(minPrice)}` : '')
      + (seat ? `&seat=${encodeURIComponent(seat)}` : '')).then(J),
  digest: (watchIds, useLlm = true) => post('/api/digest', { watch_ids: watchIds || null, use_llm: useLlm }),
  addManualFavorite: (urlOrId) => post('/api/favorites/manual', { url_or_id: urlOrId }),
  favoriteShared: (folder, item) => post(`/api/shared/${encodeURIComponent(folder)}/${encodeURIComponent(item)}/favorite`),
  watches: () => fetch('/api/watches').then(J),
  createWatch: (b) => post('/api/watches', b),
  updateWatch: (id, b) =>
    fetch(`/api/watches/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(b),
    }).then(J),
  deleteWatch: (id) => fetch(`/api/watches/${id}`, { method: 'DELETE' }).then(J),

  config: () => fetch('/api/config').then(J),
  saveConfig: (b) =>
    fetch('/api/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(b),
    }).then(J),

  recommendations: (status = 'new') => fetch(`/api/recommendations?status=${status}`).then(J),
  reviewPending: () => post('/api/recommendations/review'),
  approve: (id) => post(`/api/recommendations/${id}/approve`),
  reject: (id) => post(`/api/recommendations/${id}/reject`),
  unfavorite: (id) => fetch(`/api/favorites/${id}`, { method: 'DELETE' }).then(J),
  mute: (id, days) => post(`/api/recommendations/${id}/mute?days=${days}`),

  favorites: () => fetch('/api/favorites').then(J),
  stats: () => fetch('/api/stats').then(J),
  events: () => fetch('/api/events').then(J),
  testEmail: () => post('/api/test-email'),
  testReview: () => post('/api/test-review'),
  loginStart: () => post('/api/login/start'),
  loginStatus: () => fetch('/api/login/status').then(J),
  logout: () => post('/api/login/logout'),
  run: (watch) => post('/api/run' + (watch ? `?watch=${encodeURIComponent(watch)}` : '')),
  status: () => fetch('/api/status').then(J),
}
