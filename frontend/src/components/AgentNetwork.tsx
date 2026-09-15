import { useEffect, useState } from 'react'
import { AGENT_META, AGENT_ORDER } from './agentMeta'

interface Msg { from: string; to: string; performative: string; at: number }

/** Live visualisation of the orchestrator and the specialised agents exchanging messages. */
export default function AgentNetwork({ active, used, done, messages, busy }: {
  active: Set<string>; used: Set<string>; done: Set<string>; messages: Msg[]; busy: boolean
}) {
  const [, tick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => tick((t) => t + 1), 400)
    return () => clearInterval(id)
  }, [])
  const W = 560, H = 380, cx = W / 2, cy = H / 2, rx = 205, ry = 140
  const pos: Record<string, { x: number; y: number }> = { orchestrator: { x: cx, y: cy } }
  AGENT_ORDER.forEach((k, i) => {
    const a = (-Math.PI / 2) + (i * 2 * Math.PI) / AGENT_ORDER.length
    pos[k] = { x: cx + rx * Math.cos(a), y: cy + ry * Math.sin(a) }
  })
  const now = Date.now()
  const recent = messages.filter((m) => now - m.at < 3500 && pos[m.from] && pos[m.to])
  const orch = AGENT_META.orchestrator

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-full w-full">
      <defs>
        <radialGradient id="glow"><stop offset="0%" stopColor="#14b8a6" stopOpacity="0.25" /><stop offset="100%" stopColor="#14b8a6" stopOpacity="0" /></radialGradient>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b" /></marker>
      </defs>
      <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill="none" stroke="#e2e8f0" strokeDasharray="4 6" />
      {busy && <circle cx={cx} cy={cy} r={90} fill="url(#glow)" />}
      {AGENT_ORDER.map((k) => {
        const p = pos[k]
        const isActive = active.has(k)
        const isUsed = used.has(k)
        return <line key={`e-${k}`} x1={cx} y1={cy} x2={p.x} y2={p.y} stroke={isActive ? AGENT_META[k].color : isUsed ? '#94a3b8' : '#e2e8f0'}
          strokeWidth={isActive ? 2.5 : 1.2} className={isActive ? 'flow' : undefined} />
      })}
      {recent.map((m, i) => {
        const a = pos[m.from], b = pos[m.to]
        const opacity = 1 - (now - m.at) / 3500
        const mx = (a.x + b.x) / 2 + (b.y - a.y) * 0.15, my = (a.y + b.y) / 2 - (b.x - a.x) * 0.15
        return (
          <g key={`m-${i}-${m.at}`} opacity={opacity}>
            <path d={`M ${a.x} ${a.y} Q ${mx} ${my} ${b.x} ${b.y}`} fill="none" stroke={AGENT_META[m.from]?.color || '#64748b'} strokeWidth={2} className="flow" markerEnd="url(#arrow)" />
            <text x={mx} y={my} textAnchor="middle" className="fill-slate-600 text-[9px] font-semibold">{m.performative}</text>
          </g>
        )
      })}
      {/* orchestrator */}
      <g>
        {busy && <circle cx={cx} cy={cy} r={30} fill="none" stroke="#14b8a6" strokeWidth={2} className="pulse-ring" />}
        <circle cx={cx} cy={cy} r={34} fill="#0f766e" />
        <orch.icon x={cx - 13} y={cy - 17} width={26} height={26} color="#fff" />
        <text x={cx} y={cy + 20} textAnchor="middle" className="fill-teal-50 text-[8px] font-semibold">ORCHESTRATOR</text>
      </g>
      {AGENT_ORDER.map((k) => {
        const m = AGENT_META[k]
        const p = pos[k]
        const isActive = active.has(k)
        const isDone = done.has(k)
        const isUsed = used.has(k)
        const Icon = m.icon
        return (
          <g key={k} opacity={isUsed || isActive ? 1 : 0.45}>
            {isActive && <circle cx={p.x} cy={p.y} r={30} fill="none" stroke={m.color} strokeWidth={2} className="pulse-ring" />}
            <circle cx={p.x} cy={p.y} r={24} fill={isActive ? m.color : '#fff'} stroke={m.color} strokeWidth={isUsed ? 2.5 : 1.2} />
            <Icon x={p.x - 10} y={p.y - 10} width={20} height={20} color={isActive ? '#fff' : m.color} />
            {isDone && !isActive && <g><circle cx={p.x + 17} cy={p.y - 17} r={7} fill="#10b981" /><path d={`M ${p.x + 13.5} ${p.y - 17} l 2.5 2.5 l 4.5 -4.5`} stroke="#fff" strokeWidth={1.8} fill="none" /></g>}
            <text x={p.x} y={p.y + 38} textAnchor="middle" className="fill-slate-700 text-[10px] font-medium">{m.short}</text>
          </g>
        )
      })}
    </svg>
  )
}
