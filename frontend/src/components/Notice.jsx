import { useState } from 'react'
import { Button } from './ui'

// 改动公告内容时把这个日期往后挪, 老用户下次打开会再看一次
export const NOTICE_VERSION = '2026-11-22'

const TABS = [
  ['guide', '使用说明'],
  ['log', '更新日志'],
]

const GUIDE = [
  ['扫码登录', '设置 → 闲鱼登录，用手机闲鱼扫码。登录态、API Key、收藏都只存在你自己的库里。'],
  ['建监控条件', '条件页填关键词、价格范围、城市、成色。一条条件里的多个词会合成一次搜索；同场的几条条件可以放进同一个文件夹。'],
  ['跑一轮', '右上「立即运行」，或在设置里调抓取间隔。结束时会提示「搜索 N 条 · 命中 M 条 · 新推荐 K 条」。'],
  ['审核候选', '在「推荐」页处理。开着 AI 审核时自动判定；关掉就由你自己点「站内收藏」或「忽略」，这种情况不需要 API Key。'],
  ['盯降价', '站内收藏后按设置间隔复检详情价，降价会进右栏事件流。卡片上的「价格记录」看单件走势。'],
  ['看总览', '每个文件夹上方的「价格总览」把该条件下所有商品画在同一张图里。拖上下边调价格范围，拖左右边调日期范围，双击复位。'],
  ['公开与分享', '条件可以设为公开，其他已登录用户能看到已确认匹配的行情，但看不到你的账号、条件配置和审核理由。'],
]

const LOG = [
  ['11-22', '价格总览支持拖边缩放；卡片价格旁显示「已降 ¥N」，走势补上发布价起点'],
  ['11-22', '图表悬停时把价格标在对应的观测点上'],
  ['11-22', '主题改为浅色 / 深色两套预设，另可自定义配色；全局改用微软雅黑'],
  ['11-22', '关掉 AI 审核即进入人工审核模式，不绑定 API 也能用搜索'],
  ['11-22', '单件「价格记录」与走势图；抓取中点击运行会提示进度'],
  ['11-21', '成员数据隔离、公开文件夹、按组筛选与排序'],
]

export default function Notice({ open, onClose }) {
  const [tab, setTab] = useState('guide')
  if (!open) return null

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal notice-dialog" role="dialog" aria-label="公告"
        onClick={(event) => event.stopPropagation()}>
        <div className="notice-head">
          <h2>欢迎使用闲鱼控制台</h2>
          <button type="button" className="notice-close" aria-label="关闭" onClick={onClose}>
            <i className="ti ti-x" />
          </button>
        </div>

        <div className="notice-tabs" role="tablist">
          {TABS.map(([key, label]) => (
            <button key={key} type="button" role="tab" aria-selected={tab === key}
              onClick={() => setTab(key)}>{label}</button>
          ))}
        </div>

        <div className="notice-body">
          {tab === 'guide' ? (
            <div className="notice-steps">
              {GUIDE.map(([title, text], index) => (
                <div className="notice-step" key={title}>
                  <span className="n">{index + 1}</span>
                  <div>
                    <b>{title}</b>
                    <p>{text}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="notice-log">
              {LOG.map(([date, text]) => (
                <div key={date + text}>
                  <time>{date}</time>
                  <span>{text}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="modal-actions">
          <Button onClick={onClose}>开始使用</Button>
        </div>
      </div>
    </div>
  )
}
