import { useEffect, useState } from 'react'
import { Ambulance, ArrowRight, BedDouble, BellRing, CalendarClock, Cpu, ExternalLink, HeartPulse, Loader2, Microscope, Pill, Receipt, ShieldCheck, Siren, Users } from 'lucide-react'
import { api } from '../api'
import { useAuth } from '../auth'

const AGENTS = [
  { icon: BedDouble, label: 'Bed Management' }, { icon: CalendarClock, label: 'Appointment & Queue' },
  { icon: Users, label: 'Staff Scheduling' }, { icon: Microscope, label: 'Diagnostics' },
  { icon: Pill, label: 'Pharmacy' }, { icon: HeartPulse, label: 'Patient Care' },
  { icon: Siren, label: 'Emergency Support' }, { icon: Cpu, label: 'Resource Optimizer' },
  { icon: Ambulance, label: 'Ambulance Dispatch' }, { icon: Receipt, label: 'Billing & Insurance' },
  { icon: BellRing, label: 'Notifications' },
]

export default function Login() {
  const { login } = useAuth()
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('admin123')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [accounts, setAccounts] = useState<any[]>([])

  useEffect(() => {
    api<any[]>('/api/auth/demo-accounts').then((list) => {
      setAccounts(list)
      const demo = new URLSearchParams(window.location.search).get('demo')  // e.g. /?demo=nurse — one-click demo links
      const acc = demo && list.find((a) => a.username === demo)
      if (acc) submit(acc.username, acc.password)
    }).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const submit = async (u = username, p = password) => {
    setBusy(true)
    setError(null)
    try { await login(u, p) } catch (e: any) { setError(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="grid min-h-full lg:grid-cols-2">
      <div className="relative hidden overflow-hidden bg-slate-900 p-12 text-white lg:flex lg:flex-col">
        <div className="absolute -right-24 -top-24 h-96 w-96 rounded-full bg-teal-500/20 blur-3xl" />
        <div className="absolute -bottom-32 -left-16 h-96 w-96 rounded-full bg-sky-500/10 blur-3xl" />
        <div className="relative flex items-center gap-3">
          <img src="/icon.svg" className="h-11 w-11" alt="" />
          <div>
            <div className="text-lg font-semibold">MedOrchestra</div>
            <div className="text-xs text-teal-300">Multi-Agent AI for Hospital Management</div>
          </div>
        </div>
        <div className="relative mt-auto">
          <h1 className="text-4xl font-semibold leading-tight tracking-tight">
            Eleven specialised AI agents.<br /><span className="text-teal-300">One coordinated hospital.</span>
          </h1>
          <p className="mt-4 max-w-lg text-slate-300">
            Resource optimisation, clinical workflow automation and patient-care coordination — orchestrated by a central
            AI layer with explainable recommendations and human-in-the-loop approval for every safety-critical action.
          </p>
          <div className="mt-8 grid max-w-lg grid-cols-2 gap-2">
            {AGENTS.map((a) => (
              <div key={a.label} className="flex items-center gap-2 rounded-lg bg-white/5 px-3 py-2 text-sm ring-1 ring-white/10">
                <a.icon className="h-4 w-4 text-teal-300" />{a.label}
              </div>
            ))}
          </div>
          <div className="mt-6 flex items-center gap-2 text-xs text-slate-400"><ShieldCheck className="h-4 w-4 text-teal-400" />Decision support only — clinical decisions remain with qualified professionals.</div>
        </div>
      </div>

      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-md">
          <div className="mb-8 lg:hidden"><img src="/icon.svg" className="h-10 w-10" alt="" /></div>
          <h2 className="text-2xl font-semibold tracking-tight text-slate-900">Sign in</h2>
          <p className="mt-1 text-sm text-slate-500">Role-based access for administrators, clinicians, support staff and patients.</p>
          <form className="mt-6 space-y-4" onSubmit={(e) => { e.preventDefault(); submit() }}>
            <label className="block"><span className="label">Username</span><input className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" /></label>
            <label className="block"><span className="label">Password</span><input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></label>
            {error && <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
            <button disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-lg bg-teal-600 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-teal-700 disabled:opacity-60">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}Sign in
            </button>
          </form>
          <div className="mt-8">
            <div className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-400">Demo accounts — one click</div>
            <div className="grid grid-cols-2 gap-2">
              {accounts.map((a) => (
                <button key={a.username} onClick={() => { setUsername(a.username); setPassword(a.password); submit(a.username, a.password) }}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-left shadow-sm transition hover:border-teal-400 hover:bg-teal-50/40">
                  <div className="text-sm font-medium text-slate-800">{a.label}</div>
                  <div className="font-mono text-[11px] text-slate-500">{a.username} / {a.password}</div>
                </button>
              ))}
            </div>
          </div>
          <div className="mt-6 flex gap-2 text-xs">
            <a href="/display" target="_blank" rel="noreferrer" className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-slate-200 py-2 text-slate-600 hover:border-teal-400 hover:text-teal-800"><ExternalLink className="h-3.5 w-3.5" />Waiting-room TV display</a>
            <a href="/kiosk" target="_blank" rel="noreferrer" className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-slate-200 py-2 text-slate-600 hover:border-teal-400 hover:text-teal-800"><ExternalLink className="h-3.5 w-3.5" />Self check-in kiosk</a>
          </div>
        </div>
      </div>
    </div>
  )
}
