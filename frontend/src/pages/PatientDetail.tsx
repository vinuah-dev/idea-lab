import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import {
  Activity, ArrowLeft, BedDouble, CalendarClock, CheckCircle2, Circle, FileText, FlaskConical, HeartPulse, Loader2, LogOut, MapPin, Pill,
  Scissors, Siren, Stethoscope,
} from 'lucide-react'
import { api } from '../api'
import VitalsModal from '../components/VitalsModal'
import { Badge, Button, Card, Empty, Progress, Spinner, StatusBadge, Tabs } from '../components/ui'
import { useAuth } from '../auth'
import { useApi } from '../live'
import { agentLink, cls, fmtDateTime, fmtTime, label, newsClass } from '../utils'

type Tab = 'timeline' | 'admissions' | 'appointments' | 'diagnostics' | 'prescriptions' | 'surgeries' | 'emergency'
const KIND_ICON: Record<string, any> = { admission: BedDouble, discharge: BedDouble, appointment: CalendarClock, diagnostic: FlaskConical, prescription: Pill, emergency: Siren, surgery: Scissors }

export default function PatientDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const nav = useNavigate()
  const [tab, setTab] = useState<Tab>('timeline')
  const [vitalsOpen, setVitalsOpen] = useState(false)
  const { data, loading, reload } = useApi<any>(`/api/patients/${id}`, ['patients', 'diagnostics', 'pharmacy', 'appointments', 'beds', 'surgeries'])
  const vitals = useApi<any[]>(`/api/patients/${id}/vitals`, ['ward', 'patients'])
  if (loading && !data) return <Spinner />
  if (!data) return <Empty title="Patient not found" />
  const p = data.patient
  const admitted = !!data.active_admission_id
  const canRecord = ['admin', 'doctor', 'nurse'].includes(user!.role)
  const clinical = ['admin', 'doctor'].includes(user!.role)
  const toggle = async (t: any) => {
    const next = t.status === 'done' ? 'pending' : t.status === 'pending' ? 'in_progress' : 'done'
    await api(`/api/care-tasks/${t.id}`, { method: 'PATCH', body: { status: next } })
    reload()
  }
  const actions: { label: string; icon: any; text?: string; href?: string; show: boolean }[] = [
    { label: admitted ? 'Transfer to ICU' : 'Admit', icon: BedDouble, text: admitted ? `Transfer ${p.name} to ICU` : `Admit ${p.name} to general ward`, show: clinical || user!.role === 'nurse' },
    { label: 'Order tests', icon: FlaskConical, text: `Order CBC and chest x-ray for ${p.name}`, show: true },
    { label: 'Prescribe', icon: Pill, text: `Prescribe paracetamol 500 mg TDS for ${p.name}`, show: clinical },
    { label: 'Book OPD', icon: CalendarClock, text: `Book an appointment for ${p.name} tomorrow at 10 am`, show: true },
    { label: 'Schedule surgery', icon: Scissors, text: `Schedule hernia repair for ${p.name} tomorrow`, show: clinical },
    { label: 'Journey status', icon: MapPin, text: `Where is ${p.name} in the care journey and what is pending?`, show: true },
    { label: 'Discharge', icon: LogOut, text: `Discharge ${p.name}`, show: clinical && admitted },
    { label: 'Discharge summary', icon: FileText, href: `/print/discharge/${data.active_admission_id || data.admissions[0]?.id}`, show: data.admissions.length > 0 },
  ]
  const chart = (vitals.data || []).map((v) => ({ t: fmtTime(v.recorded_at), NEWS2: v.news2, HR: v.hr, 'SpO₂': v.spo2, SBP: v.sbp }))
  const last = vitals.data?.[vitals.data.length - 1]

  return (
    <div>
      <Link to="/patients" className="mb-3 inline-flex items-center gap-1 text-xs text-slate-500 hover:text-teal-700"><ArrowLeft className="h-3 w-3" />All patients</Link>
      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-1">
          <div className="flex items-start gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-rose-50 text-rose-600"><HeartPulse className="h-6 w-6" /></div>
            <div className="min-w-0 flex-1">
              <h1 className="text-lg font-semibold text-slate-900">{p.name}</h1>
              <div className="text-xs text-slate-500">{p.mrn} · {p.age} yrs · {p.gender} · {p.blood_group || '—'}</div>
              <div className="mt-1.5"><StatusBadge status={p.status} /></div>
            </div>
          </div>
          <dl className="mt-4 space-y-2 text-sm">
            <div className="flex justify-between"><dt className="text-slate-500">Phone</dt><dd>{p.phone || '—'}</dd></div>
            <div className="flex justify-between"><dt className="text-slate-500">Primary doctor</dt><dd>{p.primary_doctor || '—'}</dd></div>
            <div><dt className="mb-1 text-slate-500">Clinical risk score</dt><dd><Progress value={p.risk_score} /></dd></div>
            <div><dt className="mb-1 text-slate-500">Allergies</dt><dd className="flex flex-wrap gap-1">{p.allergies.length ? p.allergies.map((a: string) => <Badge key={a} tone="red">⚠ {a}</Badge>) : <span className="text-xs text-slate-400">No known allergies</span>}</dd></div>
            <div><dt className="mb-1 text-slate-500">Conditions</dt><dd className="flex flex-wrap gap-1">{p.conditions.length ? p.conditions.map((c: string) => <Badge key={c}>{c}</Badge>) : <span className="text-xs text-slate-400">None recorded</span>}</dd></div>
          </dl>
          <div className="mt-4 border-t border-slate-100 pt-3">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Coordinate with AI agents</div>
            <div className="grid grid-cols-2 gap-1.5">
              {actions.filter((a) => a.show).map((a) => (
                <button key={a.label} onClick={() => a.href ? window.open(a.href, '_blank') : nav(agentLink(a.text!, p.id))}
                  className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-2 py-1.5 text-left text-xs text-slate-700 transition hover:border-teal-300 hover:bg-teal-50">
                  <a.icon className="h-3.5 w-3.5 shrink-0 text-teal-600" />{a.label}
                </button>
              ))}
            </div>
          </div>
        </Card>

        <Card className="xl:col-span-2" title="Care pathway" subtitle={data.pathway.name ? `${label(data.pathway.name)} pathway · tracked by the Patient Care Coordinator Agent · click a step to update` : 'No active pathway'}
          actions={data.pathway.name && <span className="text-sm font-semibold text-teal-700">{data.pathway.progress}%</span>}>
          {data.pathway.steps.length === 0 ? <Empty title="No care pathway yet" hint="Admissions, ER cases, surgeries and OPD visits create pathways automatically" /> : (
            <ol className="relative grid gap-2 md:grid-cols-2">
              {data.pathway.steps.map((t: any, i: number) => (
                <li key={t.id}>
                  <button onClick={() => toggle(t)} className={cls('flex w-full items-start gap-3 rounded-lg border p-2.5 text-left transition hover:border-teal-300',
                    t.status === 'done' ? 'border-emerald-200 bg-emerald-50/50' : t.status === 'in_progress' ? 'border-blue-200 bg-blue-50/50' : 'border-slate-200')}>
                    {t.status === 'done' ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" /> : t.status === 'in_progress' ? <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-blue-500" /> : <Circle className="mt-0.5 h-4 w-4 shrink-0 text-slate-300" />}
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-slate-800">{i + 1}. {t.title}</div>
                      <div className="text-[11px] text-slate-500">{t.assigned_role} · due {fmtDateTime(t.due_at)}</div>
                    </div>
                  </button>
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>

      <Card className="mt-4" title="Observations & NEWS2 trend" icon={<Activity className="h-4 w-4" />}
        subtitle={last ? `Last recorded ${fmtDateTime(last.recorded_at)} by ${last.recorded_by}` : 'No observations recorded yet'}
        actions={canRecord && <Button size="sm" icon={<Stethoscope className="h-3.5 w-3.5" />} onClick={() => setVitalsOpen(true)}>Record observations</Button>}>
        {!chart.length ? <Empty title="No bedside observations" hint="Nurses record vitals here; each set is NEWS2-scored and escalated automatically" /> : (
          <div className="grid gap-4 lg:grid-cols-[1fr_15rem]">
            <div className="h-56">
              <ResponsiveContainer>
                <LineChart data={chart} margin={{ left: -10, right: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="t" tick={{ fontSize: 10 }} />
                  <YAxis yAxisId="l" tick={{ fontSize: 10 }} domain={[40, 170]} />
                  <YAxis yAxisId="r" orientation="right" tick={{ fontSize: 10 }} domain={[0, 14]} />
                  <Tooltip />
                  <Legend />
                  <Line yAxisId="r" type="stepAfter" dataKey="NEWS2" stroke="#dc2626" strokeWidth={2.5} dot={{ r: 3 }} />
                  <Line yAxisId="l" dataKey="HR" stroke="#6366f1" dot={false} strokeWidth={1.5} />
                  <Line yAxisId="l" dataKey="SpO₂" stroke="#0d9488" dot={false} strokeWidth={1.5} />
                  <Line yAxisId="l" dataKey="SBP" stroke="#f59e0b" dot={false} strokeWidth={1.5} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            {last && (
              <div className="rounded-xl border border-slate-200 p-3">
                <div className="flex items-center gap-3">
                  <div className={cls('flex h-12 w-12 items-center justify-center rounded-lg text-xl font-bold', newsClass(last.news2))}>{last.news2}</div>
                  <div className="text-xs"><div className="font-semibold capitalize">{last.risk} risk</div><div className="text-slate-500">latest NEWS2</div></div>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-1.5 text-xs">
                  {[['HR', last.hr, '/min'], ['RR', last.rr, '/min'], ['SpO₂', last.spo2, '%'], ['BP', `${last.sbp}/${last.dbp ?? '–'}`, ''], ['Temp', last.temp, '°C'], ['ACVPU', last.consciousness, '']].map(([k, v, u]) => (
                    <div key={k as string} className="rounded bg-slate-50 px-2 py-1"><span className="text-slate-500">{k}</span> <b>{v}{u}</b></div>
                  ))}
                </div>
                {last.on_oxygen && <Badge tone="sky" className="mt-2">on supplemental O₂</Badge>}
              </div>
            )}
          </div>
        )}
      </Card>

      <div className="mt-4">
        <Tabs<Tab> value={tab} onChange={setTab} tabs={[
          { id: 'timeline', label: `Timeline (${data.timeline.length})` }, { id: 'admissions', label: `Admissions (${data.admissions.length})` },
          { id: 'appointments', label: `Appointments (${data.appointments.length})` }, { id: 'diagnostics', label: `Diagnostics (${data.diagnostics.length})` },
          { id: 'prescriptions', label: `Prescriptions (${data.prescriptions.length})` }, { id: 'surgeries', label: `Surgeries (${data.surgeries.length})` },
          { id: 'emergency', label: `Emergency (${data.emergency.length})` }]} />
        <Card className="mt-3">
          {tab === 'timeline' && (data.timeline.length === 0 ? <Empty title="No events" /> : (
            <ol className="relative space-y-3 border-l border-slate-200 pl-5">
              {data.timeline.map((e: any, i: number) => {
                const Icon = KIND_ICON[e.kind] || Circle
                return (
                  <li key={i} className="relative">
                    <span className="absolute -left-[29px] flex h-5 w-5 items-center justify-center rounded-full bg-white ring-1 ring-slate-200"><Icon className="h-3 w-3 text-teal-600" /></span>
                    <div className="flex flex-wrap items-baseline gap-2"><span className="text-sm font-medium text-slate-800">{e.title}</span><span className="text-[11px] text-slate-400">{fmtDateTime(e.ts)}</span></div>
                    {e.detail && <div className="text-xs text-slate-500">{e.detail}</div>}
                  </li>
                )
              })}
            </ol>
          ))}
          {tab === 'admissions' && <Table rows={data.admissions} cols={[['Ward', (a) => a.ward], ['Bed', (a) => a.bed], ['Reason', (a) => a.reason], ['Acuity', (a) => <StatusBadge status={a.acuity} />],
            ['Doctor', (a) => a.doctor], ['Admitted', (a) => fmtDateTime(a.admitted_at)], ['Expected discharge', (a) => fmtDateTime(a.expected_discharge)], ['Status', (a) => <StatusBadge status={a.status} />],
            ['', (a) => <button className="text-xs text-teal-700 hover:underline" onClick={() => window.open(`/print/discharge/${a.id}`, '_blank')}>Summary</button>]]} />}
          {tab === 'appointments' && <Table rows={data.appointments} cols={[['When', (a) => fmtDateTime(a.scheduled_at)], ['Department', (a) => a.department], ['Doctor', (a) => a.doctor], ['Reason', (a) => a.reason], ['Status', (a) => <StatusBadge status={a.status} />]]} />}
          {tab === 'diagnostics' && <Table rows={data.diagnostics} cols={[['Test', (o) => o.test_name], ['Priority', (o) => <StatusBadge status={o.priority} />], ['Status', (o) => <StatusBadge status={o.status} />],
            ['Result', (o) => o.result ? <span className={o.abnormal ? 'font-medium text-red-700' : ''}>{o.result}</span> : '—'], ['Ordered', (o) => fmtDateTime(o.created_at)]]} />}
          {tab === 'prescriptions' && <Table rows={data.prescriptions} cols={[['Medication', (r) => r.medication], ['Dose', (r) => `${r.dose} ${r.frequency} × ${r.duration_days}d`], ['Doctor', (r) => r.doctor],
            ['Alerts', (r) => r.alerts.length ? r.alerts.map((a: any, i: number) => <Badge key={i} tone="red">{a.type}: {a.severity}</Badge>) : '—'], ['Status', (r) => <StatusBadge status={r.status} />]]} />}
          {tab === 'surgeries' && <Table rows={data.surgeries} cols={[['When', (s) => fmtDateTime(s.scheduled_start)], ['Procedure', (s) => s.procedure], ['Theatre', (s) => s.ot], ['Surgeon', (s) => s.surgeon],
            ['Priority', (s) => <Badge tone={s.priority === 'emergency' ? 'red' : s.priority === 'urgent' ? 'orange' : 'teal'}>{s.priority}</Badge>], ['Status', (s) => <StatusBadge status={s.status} />]]} />}
          {tab === 'emergency' && <Table rows={data.emergency} cols={[['Arrived', (e) => fmtDateTime(e.created_at)], ['Complaint', (e) => e.chief_complaint], ['Triage', (e) => `L${e.triage_level} ${e.triage_label}`], ['NEWS2', (e) => e.news2_score], ['Status', (e) => <StatusBadge status={e.status} />]]} />}
        </Card>
      </div>
      <VitalsModal patient={vitalsOpen ? { id: p.id, name: p.name } : null} onClose={() => setVitalsOpen(false)} onSaved={() => { vitals.reload(); reload() }} />
    </div>
  )
}

function Table({ rows, cols }: { rows: any[]; cols: [string, (r: any) => any][] }) {
  if (!rows.length) return <Empty title="No records" />
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-slate-500"><tr>{cols.map(([h], i) => <th key={i} className="px-2 py-1.5">{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-slate-100">{rows.map((r, i) => <tr key={i}>{cols.map(([h, f], j) => <td key={j} className="px-2 py-2 text-slate-700">{f(r)}</td>)}</tr>)}</tbody>
      </table>
    </div>
  )
}
