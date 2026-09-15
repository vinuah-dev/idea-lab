import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, Info, Loader2, X, XCircle } from 'lucide-react'
import { cls, label, STATUS_TONE, type Tone } from '../utils'

const TONES: Record<Tone, string> = {
  slate: 'bg-slate-100 text-slate-700 ring-slate-200', green: 'bg-green-50 text-green-700 ring-green-200',
  red: 'bg-red-50 text-red-700 ring-red-200', amber: 'bg-amber-50 text-amber-800 ring-amber-200',
  blue: 'bg-blue-50 text-blue-700 ring-blue-200', violet: 'bg-violet-50 text-violet-700 ring-violet-200',
  teal: 'bg-teal-50 text-teal-700 ring-teal-200', orange: 'bg-orange-50 text-orange-700 ring-orange-200',
  sky: 'bg-sky-50 text-sky-700 ring-sky-200', rose: 'bg-rose-50 text-rose-700 ring-rose-200',
  indigo: 'bg-indigo-50 text-indigo-700 ring-indigo-200', emerald: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  yellow: 'bg-yellow-50 text-yellow-800 ring-yellow-200',
}

export function Badge({ tone = 'slate', children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return <span className={cls('inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset', TONES[tone], className)}>{children}</span>
}

export function StatusBadge({ status }: { status?: string | null }) {
  return <Badge tone={STATUS_TONE[status || ''] || 'slate'}>{label(status)}</Badge>
}

export function Card({ title, subtitle, actions, children, className, bodyClass, icon }: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClass?: string; icon?: ReactNode
}) {
  return (
    <section className={cls('rounded-xl border border-slate-200 bg-white shadow-sm', className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            {icon && <span className="text-teal-600">{icon}</span>}
            <div className="min-w-0">
              <h3 className="truncate text-sm font-semibold text-slate-800">{title}</h3>
              {subtitle && <p className="truncate text-xs text-slate-500">{subtitle}</p>}
            </div>
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cls('p-4', bodyClass)}>{children}</div>
    </section>
  )
}

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'success' | 'dark'
const VARIANTS: Record<Variant, string> = {
  primary: 'bg-teal-600 text-white hover:bg-teal-700 shadow-sm',
  secondary: 'bg-white text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50 shadow-sm',
  ghost: 'text-slate-600 hover:bg-slate-100',
  danger: 'bg-red-600 text-white hover:bg-red-700 shadow-sm',
  success: 'bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm',
  dark: 'bg-slate-900 text-white hover:bg-slate-800 shadow-sm',
}

export function Button({ variant = 'primary', size = 'md', icon, loading, children, className, ...rest }: {
  variant?: Variant; size?: 'sm' | 'md'; icon?: ReactNode; loading?: boolean
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={cls('inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition disabled:cursor-not-allowed disabled:opacity-50',
        size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3.5 py-2 text-sm', VARIANTS[variant], className)}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
      {children}
    </button>
  )
}

export function Modal({ open, onClose, title, children, wide, footer }: {
  open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean; footer?: ReactNode
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4 pt-[8vh] backdrop-blur-sm" onMouseDown={onClose}>
      <div className={cls('fade-in w-full rounded-xl bg-white shadow-2xl', wide ? 'max-w-3xl' : 'max-w-lg')} onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
          <h3 className="font-semibold text-slate-800">{title}</h3>
          <button onClick={onClose} className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600" aria-label="Close"><X className="h-4 w-4" /></button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto p-5">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-3">{footer}</div>}
      </div>
    </div>
  )
}

export function Stat({ label: text, value, sub, icon, tone = 'teal', onClick }: {
  label: string; value: ReactNode; sub?: ReactNode; icon?: ReactNode; tone?: 'teal' | 'red' | 'amber' | 'blue' | 'violet' | 'slate' | 'emerald' | 'orange'; onClick?: () => void
}) {
  const t = { teal: 'bg-teal-50 text-teal-600', red: 'bg-red-50 text-red-600', amber: 'bg-amber-50 text-amber-600', blue: 'bg-blue-50 text-blue-600',
    violet: 'bg-violet-50 text-violet-600', slate: 'bg-slate-100 text-slate-600', emerald: 'bg-emerald-50 text-emerald-600', orange: 'bg-orange-50 text-orange-600' }[tone]
  return (
    <div onClick={onClick} className={cls('flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm', onClick && 'cursor-pointer transition hover:border-teal-300 hover:shadow')}>
      {icon && <div className={cls('rounded-lg p-2', t)}>{icon}</div>}
      <div className="min-w-0">
        <div className="text-xs font-medium text-slate-500">{text}</div>
        <div className="mt-0.5 text-2xl font-semibold tracking-tight text-slate-900 tabular-nums">{value}</div>
        {sub && <div className="mt-0.5 truncate text-xs text-slate-500">{sub}</div>}
      </div>
    </div>
  )
}

export function Empty({ title, hint, icon }: { title: string; hint?: string; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center">
      {icon && <div className="mb-2 text-slate-300">{icon}</div>}
      <div className="text-sm font-medium text-slate-600">{title}</div>
      {hint && <div className="mt-1 text-xs text-slate-400">{hint}</div>}
    </div>
  )
}

export function Spinner({ label: text = 'Loading…' }: { label?: string }) {
  return <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin" />{text}</div>
}

export function ErrorBox({ error }: { error: string }) {
  return <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: ReactNode }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="inline-flex flex-wrap gap-1 rounded-lg bg-slate-100 p-1">
      {tabs.map((t) => (
        <button key={t.id} onClick={() => onChange(t.id)}
          className={cls('rounded-md px-3 py-1.5 text-xs font-medium transition', value === t.id ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800')}>
          {t.label}
        </button>
      ))}
    </div>
  )
}

export function Progress({ value, max = 1, tone }: { value: number; max?: number; tone?: string }) {
  const p = Math.max(0, Math.min(1, max ? value / max : 0))
  const color = tone || (p >= 0.9 ? 'bg-red-500' : p >= 0.75 ? 'bg-amber-500' : 'bg-teal-500')
  return <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100"><div className={cls('h-full rounded-full transition-all', color)} style={{ width: `${p * 100}%` }} /></div>
}

/** Explainable-AI factor breakdown (points or costs contributed by each factor). */
export function Factors({ factors }: { factors?: { factor: string; points?: number | string; cost?: number }[] }) {
  if (!factors?.length) return null
  const vals = factors.map((f) => Math.abs(Number(f.points ?? f.cost ?? 0)) || 0)
  const max = Math.max(...vals, 1)
  return (
    <div className="mt-2 space-y-1">
      {factors.map((f, i) => {
        const isCost = f.cost !== undefined
        const num = typeof (f.points ?? f.cost) === 'number' ? Number(f.points ?? f.cost) : null
        return (
          <div key={i} className="flex items-center gap-2 text-[11px]">
            <span className="w-44 shrink-0 truncate text-slate-500" title={f.factor}>{f.factor}</span>
            {num !== null ? (
              <>
                <div className="h-1.5 flex-1 rounded-full bg-slate-100">
                  <div className={cls('h-full rounded-full', isCost || num < 0 ? 'bg-rose-400' : 'bg-teal-500')} style={{ width: `${(Math.abs(num) / max) * 100}%` }} />
                </div>
                <span className={cls('w-10 text-right tabular-nums', isCost || num < 0 ? 'text-rose-600' : 'text-teal-700')}>{isCost ? `+${num}` : num > 0 ? `+${num}` : num}</span>
              </>
            ) : <Badge tone="amber">{String(f.points)}</Badge>}
          </div>
        )
      })}
    </div>
  )
}

export function Field({ label: text, children }: { label: string; children: ReactNode }) {
  return <label className="block"><span className="label">{text}</span>{children}</label>
}

// ---------------------------------------------------------------- toasts
interface Toast { id: number; title: string; message?: string; level: string }
const ToastCtx = createContext<(t: Omit<Toast, 'id'>) => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const push = useCallback((t: Omit<Toast, 'id'>) => {
    const id = Date.now() + Math.random()
    setToasts((ts) => [...ts.slice(-3), { ...t, id }])
    setTimeout(() => setToasts((ts) => ts.filter((x) => x.id !== id)), t.level === 'critical' ? 9000 : 5000)
  }, [])
  const icon = (l: string) => l === 'critical' ? <XCircle className="h-5 w-5 text-red-500" /> : l === 'warning' ? <AlertTriangle className="h-5 w-5 text-amber-500" />
    : l === 'success' ? <CheckCircle2 className="h-5 w-5 text-emerald-500" /> : <Info className="h-5 w-5 text-sky-500" />
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-96 max-w-[calc(100vw-2rem)] flex-col gap-2">
        {toasts.map((t) => (
          <div key={t.id} className={cls('fade-in pointer-events-auto flex gap-3 rounded-xl border bg-white p-3 shadow-lg', t.level === 'critical' ? 'border-red-200' : 'border-slate-200')}>
            {icon(t.level)}
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold text-slate-800">{t.title}</div>
              {t.message && <div className="mt-0.5 line-clamp-3 text-xs text-slate-600">{t.message}</div>}
            </div>
            <button onClick={() => setToasts((ts) => ts.filter((x) => x.id !== t.id))} className="self-start text-slate-400 hover:text-slate-600"><X className="h-4 w-4" /></button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

export const useToast = () => useContext(ToastCtx)
