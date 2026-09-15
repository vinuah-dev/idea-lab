import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, BedDouble, CornerDownLeft, HeartPulse, Pill, Search, Stethoscope } from 'lucide-react'
import { api } from '../api'
import { cls } from '../utils'

export interface PaletteItem { label: string; sub?: string; link: string; type: string }

const TYPE_ICON: Record<string, any> = { patient: HeartPulse, staff: Stethoscope, bed: BedDouble, medicine: Pill, page: ArrowRight, action: ArrowRight }

/** Global search & navigation (Ctrl/⌘ + K). */
export default function CommandPalette({ open, onClose, pages }: { open: boolean; onClose: () => void; pages: PaletteItem[] }) {
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<PaletteItem[]>([])
  const [idx, setIdx] = useState(0)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => { if (open) { setQ(''); setHits([]); setIdx(0); setTimeout(() => input.current?.focus(), 10) } }, [open])
  useEffect(() => {
    if (q.trim().length < 2) { setHits([]); return }
    const id = setTimeout(() => api<PaletteItem[]>(`/api/search?q=${encodeURIComponent(q)}`).then(setHits).catch(() => setHits([])), 180)
    return () => clearTimeout(id)
  }, [q])

  const items = useMemo(() => {
    const t = q.toLowerCase()
    const pageHits = pages.filter((p) => !t || p.label.toLowerCase().includes(t))
    const ask: PaletteItem[] = q.trim().length > 3 ? [{ type: 'action', label: `Ask the agents: “${q.trim()}”`, sub: 'Run in the AI Agent Console', link: `/agents?text=${encodeURIComponent(q.trim())}` }] : []
    return [...hits, ...ask, ...pageHits.slice(0, t ? 8 : 12)]
  }, [q, hits, pages])

  const go = (it?: PaletteItem) => { if (!it) return; onClose(); nav(it.link) }
  if (!open) return null
  return (
    <div className="fixed inset-0 z-[70] flex items-start justify-center bg-slate-900/40 p-4 pt-[12vh] backdrop-blur-sm" onMouseDown={onClose}>
      <div className="fade-in w-full max-w-xl overflow-hidden rounded-xl bg-white shadow-2xl" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-3 border-b border-slate-100 px-4">
          <Search className="h-4 w-4 text-slate-400" />
          <input ref={input} value={q} onChange={(e) => { setQ(e.target.value); setIdx(0) }} placeholder="Search patients, staff, beds, medicines, pages…"
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown') { e.preventDefault(); setIdx((i) => Math.min(i + 1, items.length - 1)) }
              if (e.key === 'ArrowUp') { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)) }
              if (e.key === 'Enter') go(items[idx])
              if (e.key === 'Escape') onClose()
            }}
            className="w-full py-3.5 text-sm outline-none placeholder:text-slate-400" />
          <kbd className="rounded border border-slate-200 px-1.5 text-[10px] text-slate-400">Esc</kbd>
        </div>
        <div className="max-h-96 overflow-y-auto py-1">
          {items.length === 0 && <div className="px-4 py-6 text-center text-sm text-slate-400">No matches</div>}
          {items.map((it, i) => {
            const Icon = TYPE_ICON[it.type] || ArrowRight
            return (
              <button key={`${it.type}-${it.link}-${i}`} onMouseEnter={() => setIdx(i)} onClick={() => go(it)}
                className={cls('flex w-full items-center gap-3 px-4 py-2 text-left', i === idx ? 'bg-teal-50' : '')}>
                <Icon className={cls('h-4 w-4', it.type === 'action' ? 'text-violet-500' : 'text-teal-600')} />
                <div className="min-w-0 flex-1"><div className="truncate text-sm text-slate-800">{it.label}</div>{it.sub && <div className="truncate text-[11px] text-slate-500">{it.sub}</div>}</div>
                <span className="text-[10px] uppercase text-slate-400">{it.type}</span>
                {i === idx && <CornerDownLeft className="h-3.5 w-3.5 text-slate-400" />}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
