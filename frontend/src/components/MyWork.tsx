import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Briefcase, CalendarClock, FlaskConical, HeartPulse, Pill, Scissors, Users } from 'lucide-react'
import { useAuth } from '../auth'
import { useApi } from '../live'
import { cls, fmtTime, newsClass } from '../utils'
import VitalsModal from './VitalsModal'
import { Badge, Card, Empty, StatusBadge } from './ui'

/** Role-specific work list shown at the top of the dashboard. */
export default function MyWork() {
  const { user } = useAuth()
  const { data, reload } = useApi<any>('/api/dashboard/mywork', ['ward', 'patients', 'appointments', 'diagnostics', 'pharmacy', 'surgeries'], 30000)
  const [vitalsFor, setVitalsFor] = useState<any>(null)
  if (!data) return null
  const role = user!.role
  const titles: Record<string, string> = { doctor: 'My patients today', nurse: 'Ward early-warning board', lab: 'Lab worklist', pharmacist: 'Pharmacy worklist', receptionist: 'Front desk', admin: 'Clinical overview' }
  const title = titles[role] || 'My work'

  return (
    <div className="mb-4 grid gap-4 xl:grid-cols-3">
      {data.inpatients && (
        <Card className="xl:col-span-2" icon={<HeartPulse className="h-4 w-4" />} title={role === 'doctor' ? 'My inpatients' : role === 'nurse' ? title : 'Inpatients by NEWS2'}
          subtitle={`${data.high_news2} with NEWS2 ≥ 5 · ${data.overdue_obs} observation(s) overdue`}
          actions={<Link to="/inpatients" className="text-xs text-teal-700 hover:underline">Full census</Link>} bodyClass="p-0">
          {!data.inpatients.length ? <Empty title="No inpatients" /> : (
            <div className="divide-y divide-slate-100">
              {data.inpatients.slice(0, 7).map((r: any) => (
                <div key={r.id} className="flex items-center gap-3 px-4 py-2">
                  <span className={cls('flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-sm font-bold', newsClass(r.news2))}>{r.news2 ?? '–'}</span>
                  <div className="min-w-0 flex-1">
                    <Link to={`/patients/${r.patient.id}`} className="truncate text-sm font-medium text-slate-800 hover:text-teal-700">{r.patient.name}</Link>
                    <div className="truncate text-[11px] text-slate-500">{r.bed} · {r.ward} · {r.reason}</div>
                  </div>
                  <div className={cls('text-right text-[11px]', r.obs_overdue ? 'font-semibold text-red-600' : 'text-slate-500')}>{r.obs_overdue ? 'obs overdue' : r.monitoring}</div>
                  {['nurse', 'doctor', 'admin'].includes(role) && <button onClick={() => setVitalsFor(r.patient)} className="rounded-md border border-slate-200 px-2 py-1 text-[11px] hover:bg-slate-50">Obs</button>}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}
      {data.opd && (
        <Card icon={<CalendarClock className="h-4 w-4" />} title="My OPD today" subtitle={`${data.opd.length} upcoming / waiting`} bodyClass="p-0">
          {!data.opd.length ? <Empty title="No OPD patients left today" /> : data.opd.slice(0, 7).map((a: any) => (
            <div key={a.id} className="flex items-center gap-2 border-b border-slate-50 px-4 py-2 text-sm"><span className="w-12 tabular-nums text-slate-500">{fmtTime(a.scheduled_at)}</span><span className="flex-1 truncate">{a.patient?.name}</span><StatusBadge status={a.status} /></div>
          ))}
        </Card>
      )}
      {data.surgeries && !data.opd && (
        <Card icon={<Scissors className="h-4 w-4" />} title="Theatre list today" actions={<Link to="/theatres" className="text-xs text-teal-700 hover:underline">Theatres</Link>} bodyClass="p-0">
          {!data.surgeries.length ? <Empty title="No surgeries" /> : data.surgeries.slice(0, 7).map((s: any) => (
            <div key={s.id} className="flex items-center gap-2 border-b border-slate-50 px-4 py-2 text-sm"><span className="w-12 tabular-nums text-slate-500">{fmtTime(s.scheduled_start)}</span><span className="flex-1 truncate">{s.procedure}<span className="text-xs text-slate-400"> · {s.ot}</span></span><StatusBadge status={s.status} /></div>
          ))}
        </Card>
      )}
      {data.surgeries && data.opd && data.surgeries.length > 0 && (
        <Card className="xl:col-span-3" icon={<Scissors className="h-4 w-4" />} title="My theatre cases today">
          <div className="flex flex-wrap gap-2">{data.surgeries.map((s: any) => <div key={s.id} className="rounded-lg border border-slate-200 px-3 py-2 text-xs"><b>{fmtTime(s.scheduled_start)}</b> · {s.procedure} · {s.ot} · <StatusBadge status={s.status} /></div>)}</div>
        </Card>
      )}
      {data.orders && (
        <Card className="xl:col-span-3" icon={<FlaskConical className="h-4 w-4" />} title={title} subtitle={`${data.tat_breaches} beyond turnaround time`} actions={<Link to="/diagnostics" className="text-xs text-teal-700 hover:underline">Diagnostics board</Link>} bodyClass="p-0">
          <div className="grid divide-y divide-slate-100 md:grid-cols-2 md:divide-y-0">
            {data.orders.map((o: any) => (
              <div key={o.id} className="flex items-center gap-2 border-b border-slate-50 px-4 py-2 text-sm"><StatusBadge status={o.priority} /><span className="flex-1 truncate">{o.test_name} — {o.patient?.name}</span>{o.tat_breach && <Badge tone="red">TAT</Badge>}<StatusBadge status={o.status} /></div>
            ))}
          </div>
        </Card>
      )}
      {data.prescriptions && (
        <>
          <Card className="xl:col-span-2" icon={<Pill className="h-4 w-4" />} title={title} subtitle="Pending verification — flagged items first" actions={<Link to="/pharmacy" className="text-xs text-teal-700 hover:underline">Open queue</Link>} bodyClass="p-0">
            {!data.prescriptions.length ? <Empty title="Queue empty" /> : data.prescriptions.slice(0, 8).map((r: any) => (
              <div key={r.id} className="flex items-center gap-2 border-b border-slate-50 px-4 py-2 text-sm"><span className="flex-1 truncate">{r.medication} {r.dose} — {r.patient?.name}</span>{r.alerts.length > 0 && <Badge tone="red"><AlertTriangle className="h-3 w-3" />{r.alerts.length}</Badge>}<StatusBadge status={r.status} /></div>
            ))}
          </Card>
          <Card icon={<AlertTriangle className="h-4 w-4" />} title="Low stock">
            <div className="flex flex-wrap gap-1.5">{data.low_stock.map((m: any) => <Badge key={m.id} tone="red">{m.name}: {m.stock}</Badge>)}</div>
          </Card>
        </>
      )}
      {data.waiting && (
        <Card className="xl:col-span-3" icon={<Users className="h-4 w-4" />} title={title} subtitle={`${data.waiting.length} waiting · ${data.upcoming} more booked today · ${data.registrations_today} new registrations`}
          actions={<Link to="/opd" className="text-xs text-teal-700 hover:underline">OPD queue</Link>} bodyClass="p-0">
          <div className="grid md:grid-cols-2">
            {data.waiting.map((a: any) => (
              <div key={a.id} className="flex items-center gap-2 border-b border-slate-50 px-4 py-2 text-sm"><span className="flex-1 truncate">{a.patient?.name}<span className="text-xs text-slate-400"> · {a.department}</span></span><span className={cls('text-xs', a.waited_minutes > 45 ? 'font-semibold text-red-600' : 'text-slate-500')}>{a.waited_minutes} min</span></div>
            ))}
          </div>
        </Card>
      )}
      {!data.inpatients && !data.orders && !data.prescriptions && !data.waiting && <Card title="My work" icon={<Briefcase className="h-4 w-4" />}><Empty title="Nothing assigned" /></Card>}
      <VitalsModal patient={vitalsFor} onClose={() => setVitalsFor(null)} onSaved={() => reload()} />
    </div>
  )
}
