export function cls(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(' ')
}

export function fmtTime(iso?: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function fmtDate(iso?: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString([], { day: '2-digit', month: 'short' })
}

export function fmtDateTime(iso?: string | null) {
  if (!iso) return '—'
  const d = new Date(iso)
  return `${d.toLocaleDateString([], { day: '2-digit', month: 'short' })} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
}

export function ago(iso?: string | null) {
  if (!iso) return '—'
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return `${Math.floor(s / 86400)} d ago`
}

export const pct = (v: number, digits = 0) => `${(v * 100).toFixed(digits)}%`

export type Tone = 'slate' | 'green' | 'red' | 'amber' | 'blue' | 'violet' | 'teal' | 'orange' | 'sky' | 'rose' | 'indigo' | 'emerald' | 'yellow'

export const STATUS_TONE: Record<string, Tone> = {
  available: 'green', occupied: 'red', reserved: 'violet', cleaning: 'amber', maintenance: 'slate',
  in_use: 'blue', scheduled: 'sky', checked_in: 'amber', in_progress: 'blue', completed: 'green', cancelled: 'slate', no_show: 'slate',
  ordered: 'slate', pending: 'amber', verified: 'sky', dispensed: 'green', rejected: 'red', executed: 'green', failed: 'red', approved: 'green',
  triage: 'amber', awaiting_bed: 'orange', in_treatment: 'blue', admitted: 'violet', discharged: 'slate', registered: 'slate',
  waiting: 'amber', in_consultation: 'blue', icu: 'red', emergency: 'orange', active: 'blue',
  received: 'slate', understanding: 'sky', planning: 'sky', running: 'blue', awaiting_approval: 'amber',
  low: 'green', medium: 'amber', high: 'orange', critical: 'red', 'low-medium': 'yellow',
  info: 'sky', success: 'green', warning: 'amber', done: 'green', blocked: 'red',
  routine: 'slate', urgent: 'orange', stat: 'red',
  incoming: 'violet', to_scene: 'orange', on_scene: 'red', to_hospital: 'blue', arrived: 'green', returning: 'sky',
  submitted: 'amber', settled: 'green', open: 'sky', final: 'violet', signed: 'green', draft: 'amber',
}

const INR = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
export const inr = (v?: number | null) => (v === null || v === undefined ? '—' : INR.format(v))

export const PAYER_TONE: Record<string, Tone> = { self: 'slate', pmjay: 'emerald', private: 'indigo' }

export const TRIAGE_COLORS: Record<number, { bg: string; text: string; ring: string; label: string }> = {
  1: { bg: 'bg-red-600', text: 'text-red-700', ring: 'ring-red-200', label: 'Resuscitation' },
  2: { bg: 'bg-orange-500', text: 'text-orange-700', ring: 'ring-orange-200', label: 'Emergent' },
  3: { bg: 'bg-yellow-400', text: 'text-yellow-700', ring: 'ring-yellow-200', label: 'Urgent' },
  4: { bg: 'bg-green-500', text: 'text-green-700', ring: 'ring-green-200', label: 'Less urgent' },
  5: { bg: 'bg-sky-500', text: 'text-sky-700', ring: 'ring-sky-200', label: 'Non-urgent' },
}

export const label = (s?: string | null) => (s ? s.replace(/_/g, ' ') : '—')

/** Colour for a NEWS2 score following the RCP response thresholds. */
export const newsClass = (s?: number | null) =>
  s === null || s === undefined ? 'bg-slate-100 text-slate-400'
    : s >= 7 ? 'bg-red-600 text-white' : s >= 5 ? 'bg-orange-500 text-white' : s >= 1 ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'

export function agentLink(text: string, patientId?: number | null) {
  const p = new URLSearchParams({ text })
  if (patientId) p.set('patient', String(patientId))
  return `/agents?${p.toString()}`
}

export function downloadCsv(filename: string, rows: Record<string, unknown>[]) {
  if (!rows.length) return
  const cols = Object.keys(rows[0])
  const esc = (v: unknown) => {
    const s = v === null || v === undefined ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const csv = [cols.join(','), ...rows.map((r) => cols.map((c) => esc(r[c])).join(','))].join('\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
