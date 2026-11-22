import Select from './Select'

export const SORT_OPTIONS = [
  { value: 'price-desc', label: '价格：从高到低' },
  { value: 'price-asc', label: '价格：从低到高' },
  { value: 'published-desc', label: '发布日期：从新到旧' },
  { value: 'published-asc', label: '发布日期：从旧到新' },
]

export const DEFAULT_SORT = 'price-desc'

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

/** onMakeDefault: 再选一次当前排序 = 把这个排序设为本账号默认。 */
export default function ItemSort({ value, onChange, onMakeDefault }) {
  const pick = (next) => {
    if (next === value) onMakeDefault?.(next)
    else onChange(next)
  }
  return (
    <Select className="item-sort" align="right" ariaLabel="商品排序" value={value}
      options={SORT_OPTIONS} onChange={pick} />
  )
}
