import { useNavigate } from 'react-router-dom'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Activity, AlertTriangle, BedDouble, Bot, ClipboardCheck, FlaskConical, HeartPulse, Pill, Siren, Stethoscope, Users } from 'lucide-react'
import MyWork from '../components/MyWork'
import PageHeader from '../components/PageHeader'
import { Badge, Card, Empty, Progress, Spinner, Stat, StatusBadge } from '../components/ui'
import { useAuth } from '../auth'
import { useApi } from '../live'
import { ago, cls, fmtDate, pct, TRIAGE_COLORS } from '../utils'

export default function Dashboard() {
  const { user } = useAuth()
  const nav = useNavigate()
  const { data, loading } = useApi<any>('/api/dashboard', ['beds', 'emergency', 'appointments', 'patients', 'staff', 'diagnostics', 'pharmacy', 'notifications', 'all'], 15000)
  const bottlenecks = useApi<any[]>('/api/analytics/bottlenecks', ['beds', 'emergency', 'diagnostics', 'appointments'], 30000)
  if (loading && !data) return <Spinner />
  if (!data) return null
  const k = data.kpis
  return (
    <div>
      <PageHeader title={`Good ${new Date().getHours() < 12 ? 'morning' : new Date().getHours() < 17 ? 'afternoon' : 'evening'}, ${user?.full_name.split(' (')[0]}`}
        subtitle="Real-time command center — beds, emergency, OPD flow, staff and AI agent activity" />

      <MyWork />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Bed occupancy" value={pct(k.occupancy)} sub={`${k.beds_occupied}/${k.beds_total} occupied · ${k.cleaning} cleaning`} icon={<BedDouble className="h-5 w-5" />} tone={k.occupancy > 0.85 ? 'red' : 'teal'} onClick={() => nav('/beds')} />
        <Stat label="ICU beds free" value={`${k.icu_available}/${k.icu_total}`} sub={`${k.ventilator_beds_free} ventilator-equipped free`} icon={<HeartPulse className="h-5 w-5" />} tone={k.icu_available <= 1 ? 'red' : 'violet'} onClick={() => nav('/beds')} />
        <Stat label="Emergency active" value={k.er_active} sub={`${k.er_critical} critical · ${k.er_awaiting_bed} awaiting bed`} icon={<Siren className="h-5 w-5" />} tone="red" onClick={() => nav('/emergency')} />
        <Stat label="OPD waiting" value={k.opd_waiting} sub={`avg wait ${k.opd_avg_wait} min · ${k.opd_today} booked`} icon={<Stethoscope className="h-5 w-5" />} tone="amber" onClick={() => nav('/opd')} />
        <Stat label="Staff on duty" value={k.doctors_on_duty + k.nurses_on_duty} sub={`${k.doctors_on_duty} doctors · ${k.nurses_on_duty} nurses`} icon={<Users className="h-5 w-5" />} tone="blue" onClick={() => nav('/staff')} />
        <Stat label="Awaiting approval" value={k.pending_approvals} sub={`${k.my_pending_approvals} need your decision`} icon={<ClipboardCheck className="h-5 w-5" />} tone={k.my_pending_approvals ? 'orange' : 'slate'} onClick={() => nav('/approvals')} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card title="Ward occupancy" subtitle="Live bed status by ward" icon={<BedDouble className="h-4 w-4" />} className="xl:col-span-2">
          <div className="grid gap-x-8 gap-y-3 md:grid-cols-2">
            {data.wards.filter((w: any) => w.ward_type !== 'emergency').map((w: any) => (
              <div key={w.id}>
                <div className="mb-1 flex items-center justify-between text-xs">
                  <span className="font-medium text-slate-700">{w.name}</span>
                  <span className="tabular-nums text-slate-500">{w.occupied}/{w.total} · <span className="text-emerald-600">{w.available} free</span></span>
                </div>
                <Progress value={w.occupancy} />
              </div>
            ))}
          </div>
        </Card>
        <Card title="Emergency board" subtitle="Sorted by triage priority" icon={<Siren className="h-4 w-4" />} actions={<button className="text-xs text-teal-700 hover:underline" onClick={() => nav('/emergency')}>Open</button>}>
          {data.emergency.length === 0 ? <Empty title="No active emergency cases" /> : (
            <div className="space-y-2">
              {data.emergency.map((e: any) => (
                <div key={e.id} className="flex items-center gap-3 rounded-lg border border-slate-100 p-2">
                  <div className={cls('flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-sm font-bold text-white', TRIAGE_COLORS[e.triage_level]?.bg)}>L{e.triage_level}</div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">{e.patient?.name}</div>
                    <div className="truncate text-xs text-slate-500">{e.chief_complaint}</div>
                  </div>
                  <div className="text-right">
                    <StatusBadge status={e.status} />
                    <div className={cls('mt-0.5 text-[10px]', e.breach ? 'font-semibold text-red-600' : 'text-slate-400')}>{e.waited_minutes} min{e.breach ? ' · BREACH' : ''}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card title="Patient flow — last 30 days" subtitle="Admissions and ER visits" icon={<Activity className="h-4 w-4" />} className="xl:col-span-2">
          <div className="h-60">
            <ResponsiveContainer>
              <AreaChart data={data.trend} margin={{ left: -20, right: 8, top: 5 }}>
                <defs>
                  <linearGradient id="gA" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#0d9488" stopOpacity={0.35} /><stop offset="100%" stopColor="#0d9488" stopOpacity={0} /></linearGradient>
                  <linearGradient id="gE" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f97316" stopOpacity={0.25} /><stop offset="100%" stopColor="#f97316" stopOpacity={0} /></linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="day" tickFormatter={fmtDate} tick={{ fontSize: 11 }} interval={4} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip labelFormatter={(l) => fmtDate(String(l))} />
                <Area type="monotone" dataKey="er_visits" name="ER visits" stroke="#f97316" fill="url(#gE)" strokeWidth={2} />
                <Area type="monotone" dataKey="admissions" name="Admissions" stroke="#0d9488" fill="url(#gA)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="Operational bottlenecks" subtitle="Detected by the Resource Optimization Agent" icon={<AlertTriangle className="h-4 w-4" />}>
          {!bottlenecks.data?.length ? <Empty title="No bottlenecks detected" /> : (
            <div className="space-y-2">
              {bottlenecks.data.map((b, i) => (
                <div key={i} className="rounded-lg border border-slate-100 p-2.5">
                  <div className="flex items-center gap-2"><Badge tone={b.severity === 'high' ? 'red' : b.severity === 'medium' ? 'amber' : 'slate'}>{b.severity}</Badge><span className="text-sm font-medium">{b.area}</span></div>
                  <div className="mt-1 text-xs text-slate-600">{b.issue}</div>
                  <div className="mt-0.5 text-xs text-teal-700">→ {b.suggestion}</div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card title="AI agent activity" subtitle="Latest orchestrated requests" icon={<Bot className="h-4 w-4" />} className="xl:col-span-2"
          actions={<button className="text-xs text-teal-700 hover:underline" onClick={() => nav('/agents')}>Agent console</button>}>
          {data.recent_requests.length === 0 ? <Empty title="No agent requests yet" hint="Open the AI Agent Console and try a scenario" /> : (
            <div className="divide-y divide-slate-100">
              {data.recent_requests.map((r: any) => (
                <button key={r.id} onClick={() => nav(`/agents?request=${r.id}`)} className="flex w-full items-center gap-3 py-2.5 text-left hover:bg-slate-50">
                  <span className="font-mono text-xs text-slate-400">#{r.id}</span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm text-slate-800">{r.text}</div>
                    <div className="mt-0.5 flex flex-wrap gap-1">{r.intents.slice(0, 3).map((i: any) => <Badge key={i.name} tone="teal">{i.name}</Badge>)}<Badge tone="slate">{r.source}</Badge></div>
                  </div>
                  <div className="text-right"><StatusBadge status={r.status} /><div className="mt-0.5 text-[10px] text-slate-400">{ago(r.created_at)}</div></div>
                </button>
              ))}
            </div>
          )}
        </Card>
        <Card title="Alerts" subtitle="Critical & warning notifications" icon={<AlertTriangle className="h-4 w-4" />}>
          <div className="space-y-2">
            {data.alerts.map((n: any) => (
              <div key={n.id} className={cls('rounded-lg border-l-4 bg-slate-50 px-3 py-2', n.level === 'critical' ? 'border-red-500' : 'border-amber-400')}>
                <div className="text-sm font-medium text-slate-800">{n.title}</div>
                <div className="line-clamp-2 text-xs text-slate-500">{n.message}</div>
                <div className="mt-0.5 text-[10px] text-slate-400">{ago(n.created_at)}</div>
              </div>
            ))}
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
            <div className="rounded-lg bg-slate-50 p-2"><FlaskConical className="mx-auto mb-1 h-4 w-4 text-amber-600" />{k.diagnostics_pending}<div className="text-[10px] text-slate-500">tests pending</div></div>
            <div className="rounded-lg bg-slate-50 p-2"><Pill className="mx-auto mb-1 h-4 w-4 text-emerald-600" />{k.low_stock}<div className="text-[10px] text-slate-500">low stock</div></div>
            <div className="rounded-lg bg-slate-50 p-2"><BedDouble className="mx-auto mb-1 h-4 w-4 text-sky-600" />{k.admissions_today}/{k.discharges_today}<div className="text-[10px] text-slate-500">adm / disch today</div></div>
          </div>
        </Card>
      </div>
    </div>
  )
}
