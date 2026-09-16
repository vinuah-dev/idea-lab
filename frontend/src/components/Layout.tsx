import { useEffect, useMemo, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  Activity, Ambulance, BarChart3, BedDouble, Bell, Bot, Boxes, Brain, CalendarClock, ClipboardCheck, ClipboardList, Download, ExternalLink, FlaskConical,
  HeartPulse, KeyRound, LayoutDashboard, LogOut, Menu, MonitorDot, Pill, Receipt, Scale, Scissors, ScrollText, Search, Settings, ShieldCheck, Siren,
  UserCog, Users, X, Zap,
} from 'lucide-react'
import { api } from '../api'
import { useAuth, type Role } from '../auth'
import { useApi, useLive, useLiveStatus } from '../live'
import { ago, cls } from '../utils'
import CommandPalette, { type PaletteItem } from './CommandPalette'
import Copilot from './Copilot'
import { Badge, Button, Field, Modal, useToast } from './ui'

interface NavItem { to: string; label: string; icon: any; roles?: Role[]; badge?: 'approvals' }

const NAV: { group: string; items: NavItem[] }[] = [
  { group: 'Operations', items: [
    { to: '/', label: 'Command Center', icon: LayoutDashboard },
    { to: '/agents', label: 'AI Agent Console', icon: Bot },
    { to: '/approvals', label: 'Approvals (HITL)', icon: ClipboardCheck, badge: 'approvals' },
  ] },
  { group: 'Clinical', items: [
    { to: '/emergency', label: 'Emergency', icon: Siren, roles: ['admin', 'doctor', 'nurse', 'receptionist'] },
    { to: '/ambulance', label: 'Ambulance & 108', icon: Ambulance, roles: ['admin', 'doctor', 'nurse', 'receptionist'] },
    { to: '/monitor', label: 'ICU Central Monitor', icon: MonitorDot, roles: ['admin', 'doctor', 'nurse'] },
    { to: '/inpatients', label: 'Inpatients & Early Warning', icon: Activity },
    { to: '/handover', label: 'Shift Handover (SBAR)', icon: ClipboardList, roles: ['admin', 'doctor', 'nurse'] },
    { to: '/patients', label: 'Patients', icon: HeartPulse },
    { to: '/opd', label: 'OPD & Queue', icon: CalendarClock },
    { to: '/diagnostics', label: 'Diagnostics', icon: FlaskConical },
    { to: '/pharmacy', label: 'Pharmacy', icon: Pill },
  ] },
  { group: 'Resources & finance', items: [
    { to: '/beds', label: 'Beds & Equipment', icon: BedDouble },
    { to: '/theatres', label: 'Operation Theatres', icon: Scissors },
    { to: '/staff', label: 'Staff & Rosters', icon: Users },
    { to: '/billing', label: 'Billing & Insurance', icon: Receipt, roles: ['admin', 'receptionist', 'doctor'] },
  ] },
  { group: 'Insights & admin', items: [
    { to: '/analytics', label: 'Analytics & Forecast', icon: BarChart3 },
    { to: '/twin', label: 'Digital Twin (what-if)', icon: Boxes, roles: ['admin', 'doctor', 'nurse'] },
    { to: '/governance', label: 'AI Governance', icon: Scale, roles: ['admin', 'doctor'] },
    { to: '/audit', label: 'Audit Log', icon: ScrollText, roles: ['admin'] },
    { to: '/users', label: 'Users & Access', icon: UserCog, roles: ['admin'] },
    { to: '/system', label: 'System & Policy', icon: Settings },
  ] },
]

const PATIENT_NAV: NavItem[] = [
  { to: '/portal', label: 'My Health', icon: HeartPulse },
  { to: '/notifications', label: 'Notifications', icon: Bell },
]

export default function Layout() {
  const { user, logout } = useAuth()
  const live = useLiveStatus()
  const toast = useToast()
  const navigate = useNavigate()
  const location = useLocation()
  const [open, setOpen] = useState(false)
  const [bellOpen, setBellOpen] = useState(false)
  const [palette, setPalette] = useState(false)
  const [pwOpen, setPwOpen] = useState(false)
  const [installEvt, setInstallEvt] = useState<any>(null)
  const isStaff = user?.role !== 'patient'
  const notif = useApi<any>('/api/notifications?limit=15', ['notifications'])
  const approvals = useApi<any[]>(isStaff ? '/api/approvals?status=pending' : null)
  const system = useApi<any>('/api/system/status')
  const sim = useApi<any>(isStaff ? '/api/simulation' : null)
  const policy = useApi<any>(isStaff ? '/api/settings' : null, ['settings'])
  const bellRef = useRef<HTMLDivElement>(null)
  const recentToasts = useRef(new Map<string, number>())  // role broadcasts can reach an admin twice → show once

  useEffect(() => setOpen(false), [location.pathname])
  useEffect(() => {
    const onClick = (e: MouseEvent) => { if (bellRef.current && !bellRef.current.contains(e.target as Node)) setBellOpen(false) }
    const onKey = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k' && isStaff) { e.preventDefault(); setPalette(true) } }
    const onInstall = (e: any) => { e.preventDefault(); setInstallEvt(e) }
    document.addEventListener('mousedown', onClick)
    window.addEventListener('keydown', onKey)
    window.addEventListener('beforeinstallprompt', onInstall)
    return () => {
      document.removeEventListener('mousedown', onClick)
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('beforeinstallprompt', onInstall)
    }
  }, [isStaff])

  useLive('notification', (n: any) => {
    const mine = n.user_id === user?.id || n.role === user?.role || (!n.user_id && !n.role) || (user?.role === 'admin' && n.level === 'critical')
    if (mine) {
      const key = `${n.title}|${n.message}`
      const now = Date.now()
      if (now - (recentToasts.current.get(key) || 0) > 8000) toast({ title: n.title, message: n.message, level: n.level })
      recentToasts.current.set(key, now)
      notif.reload()
    }
  })
  useLive('approval', () => approvals.reload())
  useLive('simulation', () => sim.reload())

  const pending = (approvals.data || []).filter((a: any) => a.can_decide).length
  const navGroups = isStaff ? NAV : [{ group: 'Patient', items: PATIENT_NAV }]
  const pages: PaletteItem[] = useMemo(() => navGroups.flatMap((g) => g.items.filter((i) => !i.roles || i.roles.includes(user!.role))
    .map((i) => ({ type: 'page', label: i.label, sub: g.group, link: i.to }))), [user, navGroups])

  const toggleSim = async () => {
    await api(`/api/simulation/${sim.data?.running ? 'stop' : 'start'}`, { method: 'POST' })
    sim.reload()
    toast({ title: sim.data?.running ? 'Simulation paused' : 'Live simulation started', message: 'Patients, ER arrivals, observations, surgeries and lab results will now flow in automatically.', level: 'info' })
  }
  const mode = policy.data?.values?.autonomy_mode

  return (
    <div className="flex h-full">
      <aside className={cls('fixed inset-y-0 left-0 z-40 flex w-64 flex-col bg-slate-900 text-slate-300 transition-transform lg:static lg:translate-x-0 print:hidden', open ? 'translate-x-0' : '-translate-x-full')}>
        <div className="flex items-center gap-2.5 border-b border-white/10 px-5 py-4">
          <img src="/icon.svg" alt="" className="h-9 w-9" />
          <div>
            <div className="font-semibold tracking-tight text-white">MedOrchestra</div>
            <div className="text-[11px] text-teal-300">Multi-Agent Hospital AI</div>
          </div>
          <button className="ml-auto lg:hidden" onClick={() => setOpen(false)} aria-label="Close menu"><X className="h-5 w-5" /></button>
        </div>
        <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
          {navGroups.map((g) => {
            const items = g.items.filter((i) => !i.roles || i.roles.includes(user!.role))
            if (!items.length) return null
            return (
              <div key={g.group}>
                <div className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">{g.group}</div>
                {items.map((i) => (
                  <NavLink key={i.to} to={i.to} end={i.to === '/'}
                    className={({ isActive }) => cls('flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition',
                      isActive ? 'bg-teal-600/20 font-medium text-white ring-1 ring-inset ring-teal-500/30' : 'hover:bg-white/5 hover:text-white')}>
                    <i.icon className="h-4 w-4" />
                    <span className="flex-1">{i.label}</span>
                    {i.badge === 'approvals' && pending > 0 && <span className="rounded-full bg-amber-500 px-1.5 text-[10px] font-bold text-white">{pending}</span>}
                  </NavLink>
                ))}
              </div>
            )
          })}
        </nav>
        {isStaff && (
          <div className="mx-3 mb-2 flex gap-1.5 text-[11px]">
            <a href="/display" target="_blank" rel="noreferrer" className="flex flex-1 items-center justify-center gap-1 rounded-md bg-white/5 py-1.5 text-slate-400 hover:bg-white/10 hover:text-white"><ExternalLink className="h-3 w-3" />TV display</a>
            <a href="/kiosk" target="_blank" rel="noreferrer" className="flex flex-1 items-center justify-center gap-1 rounded-md bg-white/5 py-1.5 text-slate-400 hover:bg-white/10 hover:text-white"><ExternalLink className="h-3 w-3" />Kiosk</a>
          </div>
        )}
        {installEvt && (
          <button onClick={async () => { installEvt.prompt(); await installEvt.userChoice; setInstallEvt(null) }}
            className="mx-3 mb-2 flex items-center justify-center gap-2 rounded-lg bg-teal-600/20 py-2 text-xs font-medium text-teal-200 ring-1 ring-inset ring-teal-500/30 hover:bg-teal-600/30">
            <Download className="h-3.5 w-3.5" />Install MedOrchestra app
          </button>
        )}
        <div className="border-t border-white/10 p-3">
          <div className="flex items-center gap-2 rounded-lg px-2 py-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-teal-600 text-xs font-semibold text-white">
              {user?.full_name.replace('Dr. ', '').split(' ').map((s) => s[0]).slice(0, 2).join('')}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium text-white">{user?.full_name}</div>
              <div className="text-[11px] capitalize text-slate-400">{user?.role}</div>
            </div>
            <button onClick={() => setPwOpen(true)} title="Change password" className="rounded-md p-1.5 text-slate-400 hover:bg-white/10 hover:text-white"><KeyRound className="h-4 w-4" /></button>
            <button onClick={logout} title="Sign out" className="rounded-md p-1.5 text-slate-400 hover:bg-white/10 hover:text-white"><LogOut className="h-4 w-4" /></button>
          </div>
        </div>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/40 lg:hidden" onClick={() => setOpen(false)} />}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-slate-200 bg-white/85 px-4 py-2.5 backdrop-blur lg:px-6 print:hidden">
          <button className="lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu"><Menu className="h-5 w-5 text-slate-600" /></button>
          <div className="hidden min-w-0 sm:block">
            <div className="truncate text-sm font-semibold text-slate-800">{system.data?.hospital || 'Hospital'}</div>
            <div className="text-[11px] text-slate-500">{new Date().toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</div>
          </div>
          {isStaff && (
            <button onClick={() => setPalette(true)} className="ml-2 hidden w-64 items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-400 transition hover:border-teal-300 hover:bg-white md:flex xl:w-80">
              <Search className="h-3.5 w-3.5" />Search patients, beds, staff…<kbd className="ml-auto rounded border border-slate-200 bg-white px-1 text-[10px]">Ctrl K</kbd>
            </button>
          )}
          <div className="ml-auto flex items-center gap-2">
            <span className={cls('hidden items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium md:inline-flex', live ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500')}>
              <span className={cls('h-1.5 w-1.5 rounded-full', live ? 'bg-emerald-500 blink' : 'bg-slate-400')} />{live ? 'Live' : 'Offline'}
            </span>
            {system.data && (
              <span className="hidden items-center gap-1 rounded-full bg-violet-50 px-2.5 py-1 text-[11px] font-medium text-violet-700 xl:inline-flex" title="Natural-language understanding engine">
                <Brain className="h-3 w-3" />{system.data.llm.enabled ? system.data.llm.model : 'Local NLP'}
              </span>
            )}
            {mode && (
              <button onClick={() => navigate('/system')} className="hidden items-center gap-1 rounded-full bg-sky-50 px-2.5 py-1 text-[11px] font-medium capitalize text-sky-700 xl:inline-flex" title="Human-in-the-loop autonomy policy">
                <ShieldCheck className="h-3 w-3" />HITL: {mode}
              </button>
            )}
            {user?.role === 'admin' && sim.data && (
              <button onClick={toggleSim} className={cls('inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 ring-inset transition',
                sim.data.running ? 'bg-amber-50 text-amber-700 ring-amber-200' : 'bg-white text-slate-600 ring-slate-200 hover:bg-slate-50')}>
                <Zap className="h-3 w-3" />{sim.data.running ? 'Simulation ON' : 'Simulate'}
              </button>
            )}
            {isStaff && <button onClick={() => setPalette(true)} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 md:hidden" aria-label="Search"><Search className="h-5 w-5" /></button>}
            <div className="relative" ref={bellRef}>
              <button onClick={() => setBellOpen((o) => !o)} className="relative rounded-lg p-2 text-slate-500 hover:bg-slate-100" aria-label="Notifications">
                <Bell className="h-5 w-5" />
                {notif.data?.unread > 0 && <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[9px] font-bold text-white">{notif.data.unread > 99 ? '99+' : notif.data.unread}</span>}
              </button>
              {bellOpen && (
                <div className="fade-in absolute right-0 mt-2 w-96 max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl">
                  <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
                    <span className="text-sm font-semibold">Notifications</span>
                    <button className="text-xs text-teal-700 hover:underline" onClick={async () => { await api('/api/notifications/read-all', { method: 'POST' }); notif.reload() }}>Mark all read</button>
                  </div>
                  <div className="max-h-96 overflow-y-auto">
                    {(notif.data?.items || []).map((n: any) => (
                      <button key={n.id} onClick={() => { setBellOpen(false); if (n.link) navigate(n.link) }}
                        className={cls('block w-full border-b border-slate-50 px-4 py-2.5 text-left hover:bg-slate-50', !n.read && 'bg-teal-50/40')}>
                        <div className="flex items-center gap-2">
                          <Badge tone={n.level === 'critical' ? 'red' : n.level === 'warning' ? 'amber' : n.level === 'success' ? 'green' : 'sky'}>{n.category}</Badge>
                          {n.channel !== 'in-app' && <Badge tone="violet">{n.channel}</Badge>}
                          <span className="ml-auto text-[10px] text-slate-400">{ago(n.created_at)}</span>
                        </div>
                        <div className="mt-1 text-sm font-medium text-slate-800">{n.title}</div>
                        <div className="line-clamp-2 text-xs text-slate-500">{n.message}</div>
                      </button>
                    ))}
                  </div>
                  <button onClick={() => { setBellOpen(false); navigate('/notifications') }} className="block w-full py-2 text-center text-xs font-medium text-teal-700 hover:bg-slate-50">View all</button>
                </div>
              )}
            </div>
            {isStaff && (
              <button onClick={() => navigate('/agents')} className="hidden items-center gap-1.5 rounded-lg bg-teal-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-teal-700 sm:inline-flex">
                <Bot className="h-3.5 w-3.5" />Ask the agents
              </button>
            )}
          </div>
        </header>
        <main className="flex-1 overflow-y-auto px-4 py-5 lg:px-6">
          <Outlet />
        </main>
      </div>
      <CommandPalette open={palette} onClose={() => setPalette(false)} pages={pages} />
      <PasswordModal open={pwOpen} onClose={() => setPwOpen(false)} />
      {isStaff && <Copilot />}
    </div>
  )
}

function PasswordModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast()
  const [cur, setCur] = useState('')
  const [next, setNext] = useState('')
  const [busy, setBusy] = useState(false)
  const save = async () => {
    setBusy(true)
    try {
      await api('/api/auth/change-password', { body: { current_password: cur, new_password: next } })
      toast({ title: 'Password changed', level: 'success' })
      setCur(''); setNext(''); onClose()
    } catch (e: any) { toast({ title: 'Could not change password', message: e.message, level: 'critical' }) } finally { setBusy(false) }
  }
  return (
    <Modal open={open} onClose={onClose} title="Change password" footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={busy} disabled={!cur || next.length < 8} onClick={save}>Update</Button></>}>
      <div className="space-y-3">
        <Field label="Current password"><input className="input" type="password" value={cur} onChange={(e) => setCur(e.target.value)} /></Field>
        <Field label="New password (min 8 characters, letters + digits)"><input className="input" type="password" value={next} onChange={(e) => setNext(e.target.value)} /></Field>
      </div>
    </Modal>
  )
}
