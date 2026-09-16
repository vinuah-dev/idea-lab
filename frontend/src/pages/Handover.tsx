import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowDownRight, ArrowRight, ArrowUpRight, ClipboardList, Printer } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { Badge, Button, Card, Empty, Spinner } from '../components/ui'
import { useApi } from '../live'
import { cls, fmtDateTime, newsClass } from '../utils'

const TREND: Record<string, any> = { worsening: ArrowUpRight, improving: ArrowDownRight }

/** SBAR shift handover generated from live chart data (situation · background · assessment · recommendation). */
export default function Handover() {
  const [ward, setWard] = useState('')
  const { data, loading } = useApi<any>(`/api/handover${ward ? `?ward_id=${ward}` : ''}`, ['ward', 'patients'])
  return (
    <div>
      <PageHeader title="Shift handover (SBAR)" icon={<ClipboardList className="h-5 w-5" />}
        subtitle="Structured handover generated from observations, results, medicines and pending care tasks — reduces omissions at shift change"
        actions={<>
          <select className="input w-60 py-1.5 text-xs print:hidden" value={ward} onChange={(e) => setWard(e.target.value)}>
            <option value="">All inpatient wards</option>{(data?.wards || []).map((w: any) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
          <Button size="sm" variant="secondary" icon={<Printer className="h-3.5 w-3.5" />} onClick={() => window.print()}>Print</Button>
        </>} />
      {loading && !data ? <Spinner /> : !data ? null : (
        <>
          <Card className="mb-4">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-semibold text-slate-800">{data.shift}</span><span className="text-xs text-slate-400">generated {fmtDateTime(data.generated_at)}</span>
              <span className="ml-auto flex flex-wrap gap-1.5">
                <Badge tone="slate">{data.summary.patients} patients</Badge><Badge tone="red">{data.summary.high_news2} NEWS2 ≥ 5</Badge>
                <Badge tone="amber">{data.summary.obs_overdue} obs overdue</Badge><Badge tone="violet">{data.summary.discharges_due} discharges &lt; 24 h</Badge>
              </span>
            </div>
          </Card>
          {!data.patients.length ? <Empty title="No inpatients in this ward" /> : (
            <div className="grid gap-3 xl:grid-cols-2">
              {data.patients.map((p: any) => {
                const T = TREND[p.trend] || ArrowRight
                return (
                  <div key={p.admission_id} className="break-inside-avoid rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs font-bold text-slate-500">{p.bed}</span>
                      <Link to={`/patients/${p.patient.id}`} className="font-semibold text-slate-800 hover:text-teal-700">{p.patient.name}</Link>
                      <span className="text-xs text-slate-400">{p.ward}</span>
                      <span className={cls('ml-auto flex h-7 min-w-7 items-center justify-center rounded-md px-1.5 text-sm font-bold', newsClass(p.news2))}>{p.news2 ?? '–'}</span>
                      <T className={cls('h-4 w-4', p.trend === 'worsening' ? 'text-red-500' : p.trend === 'improving' ? 'text-emerald-500' : 'text-slate-400')} />
                    </div>
                    {p.flags.length > 0 && <div className="mt-1.5 flex flex-wrap gap-1">{p.flags.map((f: string) => <Badge key={f} tone={f.startsWith('NEWS2') ? 'red' : f === 'allergy' ? 'rose' : f.startsWith('discharge') ? 'violet' : 'amber'}>{f}</Badge>)}</div>}
                    <dl className="mt-2 grid gap-1.5 text-xs">
                      {([['S', 'Situation', p.situation], ['B', 'Background', p.background], ['A', 'Assessment', p.assessment], ['R', 'Recommendation', p.recommendation]] as const).map(([k, l, v]) => (
                        <div key={k} className="flex gap-2"><dt className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-teal-600 text-[10px] font-bold text-white" title={l}>{k}</dt><dd className="text-slate-700">{v}</dd></div>
                      ))}
                    </dl>
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}
    </div>
  )
}
