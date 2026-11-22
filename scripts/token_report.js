// 本会话用量报告: 轮次/步数/估算 token 去向, 输出 ≤ 7 行
// 用法: node scripts/token_report.js [session.v4.jsonl.zstd]
const fs = require('fs')
const os = require('os')
const path = require('path')
const zlib = require('zlib')

const CJK = /[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]/
const tok = (text) => {
  if (!text) return 0
  let cjk = 0
  for (const ch of text) if (CJK.test(ch)) cjk += 1
  return cjk + (text.length - cjk) / 4
}

function newestSession() {
  const root = path.join(os.homedir(), '.dsh', 'sessions')
  const found = []
  const walk = (dir, depth) => {
    if (depth > 3) return
    let names = []
    try { names = fs.readdirSync(dir) } catch { return }
    for (const name of names) {
      const full = path.join(dir, name)
      let st
      try { st = fs.statSync(full) } catch { continue }
      if (st.isDirectory()) walk(full, depth + 1)
      else if (name === 'session.v4.jsonl.zstd') found.push([full, st.mtimeMs])
    }
  }
  walk(root, 0)
  found.sort((a, b) => b[1] - a[1])
  return found[0] ? found[0][0] : null
}

// 会话文件是多帧 zstd(每次写入一帧): 逐个魔数起点解压再拼接
function decode(file) {
  const buf = fs.readFileSync(file)
  const MAGIC = Buffer.from([0x28, 0xb5, 0x2f, 0xfd])
  const parts = []
  for (let i = buf.indexOf(MAGIC); i !== -1; i = buf.indexOf(MAGIC, i + 4)) {
    try {
      const text = zlib.zstdDecompressSync(buf.subarray(i)).toString('utf8')
      if (text) parts.push(text)
    } catch { /* 压缩数据里的假魔数, 跳过 */ }
  }
  return parts.join('')
}

const file = process.argv[2] || newestSession()
if (!file) {
  console.log('token-report: 没找到会话日志')
  process.exit(1)
}
const raw = decode(file)
const events = []
for (const line of raw.split('\n')) {
  if (!line.startsWith('{')) continue
  try { events.push(JSON.parse(line)) } catch { /* 截断行 */ }
}
events.sort((a, b) => (a.seq || 0) - (b.seq || 0))

let reason = 0
let assistant = 0
let history = 0
let peak = 0
const toolOut = new Map()
const toolCalls = new Map()
const callName = new Map()
let turns = 0
let steps = 0
const contexts = []

for (const e of events) {
  const d = e.data || {}
  if (e.type === 'turn/start') turns += 1
  else if (e.type === 'step/start') { steps += 1; contexts.push(history / 4) }
  else if (e.type === 'assistant/message') {
    for (const b of (d.message && d.message.content) || []) {
      if (b.type === 'reasoning') { reason += tok(b.text); history += (b.text || '').length }
      else if (b.type === 'text') { assistant += tok(b.text); history += (b.text || '').length }
      else if (b.type === 'tool-call') {
        callName.set(b.id, b.name)
        toolCalls.set(b.name, (toolCalls.get(b.name) || 0) + 1)
        history += ((b.arguments || '').length) / 4
      }
    }
  } else if (e.type === 'tool/result') {
    const msg = d.message || {}
    const text = (msg.content || []).map((b) => b.text || '').join('')
    const name = callName.get(msg.toolCallId) || '?'
    toolOut.set(name, (toolOut.get(name) || 0) + tok(text))
    history += text.length
    peak = Math.max(peak, Math.round(history / 4))
  }
}

const totalOut = [...toolOut.values()].reduce((a, b) => a + b, 0) || 1
const top = [...toolOut.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3)
const calls = [...toolCalls.values()].reduce((a, b) => a + b, 0)

console.log(`session: ${path.basename(path.dirname(file))} | ${(raw.length / 1048576).toFixed(1)} MB 日志`)
console.log(`轮次 ${turns} | 模型调用 ${steps} | 工具调用 ${calls}`)
console.log(`估算累计输入 ≈ ${(contexts.reduce((a, b) => a + b, 0) / 1e6).toFixed(0)}M token（峰值上下文 ${(peak / 1000).toFixed(0)}k）`)
console.log(`输出: 思考 ${(reason / 1000).toFixed(0)}k + 正文 ${(assistant / 1000).toFixed(0)}k`)
console.log(`工具输出 ${(totalOut / 1000).toFixed(0)}k token: ${top.map(([n, v]) => `${n} ${Math.round(v / totalOut * 100)}%`).join(' / ')}`)
console.log(`每次调用平均携带 ≈ ${(contexts.reduce((a, b) => a + b, 0) / Math.max(1, contexts.length) / 1000).toFixed(0)}k token`)
