import { useEffect, useState } from 'react'
import { api } from '../api'

export function useFolders(refreshKey, visibility) {
  const [data, setData] = useState({ watches: [], folders: [], shared: [] })
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    const refresh = () => Promise.all([api.watches(), api.folders(), api.shared()])
      .then(([watches, folders, shared]) => {
        if (active) {
          setData({ watches, folders, shared })
          setError('')
        }
      })
      .catch((error) => {
        if (active) {
          setData({ watches: [], folders: [], shared: [] })
          setError(error.message)
        }
      })
    refresh()
    const timer = setInterval(refresh, 15_000)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [refreshKey, visibility])
  return { ...data, error }
}

export function ownFolders(watches, folders, visibility) {
  const grouped = new Map()
  for (const watch of watches) {
    if (visibility === 'private' && watch.public) continue
    const folder = folders.find((item) => item.id === watch.folder_id)
    const id = folder ? `folder:${folder.id}` : `watch:${watch.id}`
    if (!grouped.has(id)) grouped.set(id, { id, name: folder?.name ?? watch.name, watches: [] })
    grouped.get(id).watches.push(watch.id)
  }
  return [...grouped.values(), { id: 'ungrouped', name: '未归档', watches: [] }]
}

export default function Folders({ choices, selected, onSelect, visibility, onVisibility, counts = {} }) {
  return (
    <aside className="folder-nav" aria-label="监控文件夹">
      <div className="folder-filters">
        {[
          ['mine', '我的'],
          ['public', '公开'],
          ['private', '私密'],
        ].map(([value, label]) => (
          <button key={value} type="button" aria-pressed={visibility === value}
            onClick={() => onVisibility(value)}>{label}</button>
        ))}
      </div>
      <div className="folder-list">
        {choices.map((folder) => (
          <button key={folder.id} type="button" aria-pressed={selected === folder.id}
            onClick={() => onSelect(folder.id)}>
            <i className="ti ti-folder" aria-hidden="true" />
            {folder.name}
            {counts[folder.id] ? <b className="folder-count">{counts[folder.id]}</b> : null}
          </button>
        ))}
      </div>
    </aside>
  )
}
