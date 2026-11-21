export function sortItems(items, order) {
  const key = order.startsWith('price') ? 'price' : 'publish_time'
  const direction = order.endsWith('-asc') ? 1 : -1
  const value = key === 'price'
    ? (item) => item.price ?? NaN
    : (item) => Date.parse(item.publish_time)
  return [...items].sort((a, b) => {
    const first = value(a)
    const second = value(b)
    if (!Number.isFinite(first)) return Number.isFinite(second) ? 1 : 0
    if (!Number.isFinite(second)) return -1
    return direction * (first - second)
  })
}

export default function ItemSort({ value, onChange }) {
  return (
    <select className="item-sort" aria-label="商品排序" value={value}
      onChange={(event) => onChange(event.target.value)}>
      <option value="published-desc">发布日期：从新到旧</option>
      <option value="published-asc">发布日期：从旧到新</option>
      <option value="price-asc">价格：从低到高</option>
      <option value="price-desc">价格：从高到低</option>
    </select>
  )
}
