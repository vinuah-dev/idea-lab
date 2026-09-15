import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Activity, AlertTriangle, BedDouble, Clock, Download, FileText, HeartPulse, LogOut, Search } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import VitalsModal from '../components/VitalsModal'
import { Badge, Button, Card, Empty, Spinner, Stat } from '../components/ui'
import { useAuth } from '../auth'
import { useApi } from '../live'
import { agentLink, ago, cls, downloadCsv, fmtDateTime, newsClass } from '../utils'

const TYPES = ['', 'general', 'icu', 'hdu', 'cardiac', 'pediatric', 'maternity', 'isolation']

export default function Inpatients() {
  const { user } = useAuth()
  const nav = useNavigate()
  const [ward, setWard] = useState('')
  const [q, setQ] = useState('')
  const [vitalsFor, setVitalsFor] = useState<any>(null)
  const { data, loading, reload } = useApi<any[]>(`/api/admissions${ward ? `?ward_type=${ward}` : ''}`, ['ward', 'patients', 'beds'], 30000)
  const rows = (data || []).filter((r) => !q || r.patient.name.toLowerCase().includes(q.toLowerCase()) || (r.bed || '').toLowerCase().includes(q.toLowerCase()))
  const canRecord = ['admin', 'doctor', 'nurse'].includes(user!.role)
  const all = data || []

  return (
    <div>
      <PageHeader title="Inpatients & early warning" icon={<Activity className="h-5 w-5" />}
        subtitle="Ward census with NEWS2 bedside monitoring, observation schedules, ML length-of-stay prediction and discharge planning"
        actions={<Button variant="secondary" icon={<Download className="h-4 w-4" />} onClick={() => downloadCsv('inpatient-census.csv', rows.map((r) => ({
          bed: r.bed, ward: r.ward, mrn: r.patient.mrn, patient: r.patient.name, age: r.patient.age, doctor: r.doctor, reason: r.reason, news2: r.news2,
          los_days: r.los_days, predicted_los: r.predicted_los?.days, expected_discharge: r.expected_discharge })))}>Export CSV</Button>} />
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Inpatients" value={all.length} icon={<BedDouble className="h-5 w-5" />} />
        <Stat label="NEWS2 ≥ 7 (emergency)" value={all.filter((r) => r.news2 >= 7).length} icon={<AlertTriangle className="h-5 w-5" />} tone="red" />
        <Stat label="NEWS2 5–6 (urgent)" value={all.filter((r) => r.news2 >= 5 && r.news2 < 7).length} icon={<HeartPulse className="h-5 w-5" />} tone="orange" />
        <Stat label="Observations overdue" value={all.filter((r) => r.obs_overdue).length} icon={<Clock className="h-5 w-5" />} tone="amber" />
        <Stat label="Discharge due ≤ 24 h" value={all.filter((r) => r.discharge_due).length} icon={<LogOut className="h-5 w-5" />} tone="blue" />
      </div>
      <Card bodyClass="p-0">
        <div className="flex flex-wrap gap-2 border-b border-slate-100 p-3">
          <div className="relative min-w-56 flex-1"><Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" /><input className="input pl-9" placeholder="Search patient or bed" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          <select className="input w-44" value={ward} onChange={(e) => setWard(e.target.value)}>{TYPES.map((t) => <option key={t} value={t}>{t ? t.toUpperCase() : 'All wards'}</option>)}</select>
        </div>
        {loading && !data ? <Spinner /> : !rows.length ? <Empty title="No inpatients" /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs text-slate-500">
                <tr><th className="px-3 py-2">NEWS2</th><th className="px-3 py-2">Bed</th><th className="px-3 py-2">Patient</th><th className="px-3 py-2">Reason / doctor</th>
                  <th className="px-3 py-2">Last observations</th><th className="px-3 py-2">Length of stay</th><th className="px-3 py-2">Expected discharge</th><th className="px-3 py-2 text-right">Actions</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r) => (
                  <tr key={r.id} className={cls('hover:bg-slate-50', r.news2 >= 7 && 'bg-red-50/50')}>
                    <td className="px-3 py-2"><span className={cls('inline-flex h-8 w-8 items-center justify-center rounded-lg text-sm font-bold', newsClass(r.news2))}>{r.news2 ?? '–'}</span></td>
                    <td className="px-3 py-2"><div className="font-mono text-xs font-semibold">{r.bed}</div><div className="text-[11px] text-slate-500">{r.ward}</div></td>
                    <td className="px-3 py-2">
                      <Link to={`/patients/${r.patient.id}`} className="font-medium text-slate-800 hover:text-teal-700">{r.patient.name}</Link>
                      <div className="text-[11px] text-slate-500">{r.patient.mrn} · {r.patient.age}{r.patient.gender?.[0]} {r.patient.allergies.map((a: string) => <Badge key={a} tone="red" className="ml-1">⚠ {a}</Badge>)}</div>
                    </td>
                    <td className="max-w-56 px-3 py-2"><div className="truncate text-xs text-slate-700" title={r.reason}>{r.reason}</div><div className="text-[11px] text-slate-500">{r.doctor} · {r.acuity}</div></td>
                    <td className="min-w-64 px-3 py-2 text-xs">
                      {r.vitals ? <>
                        <div className="flex flex-wrap gap-1">
                          {[['HR', r.vitals.hr], ['RR', r.vitals.rr], ['SpO₂', `${r.vitals.spo2}%`], ['BP', `${r.vitals.sbp}/${r.vitals.dbp ?? '–'}`], ['T', `${r.vitals.temp}°`]].map(([k, val]) => (
                            <span key={k} className="whitespace-nowrap rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-700"><span className="text-slate-400">{k}</span> {val}</span>
                          ))}
                        </div>
                        <div className={cls('mt-1 whitespace-nowrap text-[11px]', r.obs_overdue ? 'font-semibold text-red-600' : 'text-slate-500')}>{ago(r.vitals.recorded_at)} · next {r.monitoring}{r.obs_overdue ? ' · OVERDUE' : ''}</div>
                      </> : <span className="text-red-600">no observations recorded</span>}
                    </td>
                    <td className="px-3 py-2 text-xs">
                      <div className="text-slate-700">{r.los_days} d{r.predicted_los && <span className="text-slate-400"> / predicted {r.predicted_los.days} d</span>}</div>
                      {r.predicted_los && <div className="mt-1 h-1.5 w-28 rounded-full bg-slate-100"><div className={cls('h-full rounded-full', r.los_days > r.predicted_los.high ? 'bg-red-500' : 'bg-teal-500')} style={{ width: `${Math.min(100, (r.los_days / Math.max(r.predicted_los.high, 0.1)) * 100)}%` }} /></div>}
                    </td>
                    <td className="px-3 py-2 text-xs">{fmtDateTime(r.expected_discharge)}{r.discharge_due && <Badge tone="blue" className="ml-1">due</Badge>}</td>
                    <td className="px-3 py-2">
                      <div className="flex justify-end gap-1">
                        {canRecord && <Button size="sm" variant="secondary" icon={<HeartPulse className="h-3.5 w-3.5" />} onClick={() => setVitalsFor(r.patient)}>Obs</Button>}
                        <Button size="sm" variant="ghost" icon={<FileText className="h-3.5 w-3.5" />} onClick={() => window.open(`/print/discharge/${r.id}`, '_blank')}>Summary</Button>
                        {['admin', 'doctor'].includes(user!.role) && <Button size="sm" variant="ghost" icon={<LogOut className="h-3.5 w-3.5" />} onClick={() => nav(agentLink(`Discharge ${r.patient.name}`, r.patient.id))}>Discharge</Button>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <VitalsModal patient={vitalsFor} onClose={() => setVitalsFor(null)} onSaved={() => reload()} />
    </div>
  )
}
