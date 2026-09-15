import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { CalendarPlus, Cpu, Scissors } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import { Badge, Button, Card, Empty, Factors, Field, Modal, Spinner, Stat, StatusBadge, useToast } from '../components/ui'
import { useAuth } from '../auth'
import { useApi } from '../live'
import { cls, fmtTime } from '../utils'

const START_H = 7, END_H = 22, SPAN = (END_H - START_H) * 60
const minutesOf = (iso: string) => { const d = new Date(iso); return d.getHours() * 60 + d.getMinutes() }
const pct = (m: number) => Math.max(0, Math.min(100, ((m - START_H * 60) / SPAN) * 100))
const BAR: Record<string, string> = {
  completed: 'bg-slate-300 text-slate-700', in_progress: 'bg-blue-600 text-white ring-2 ring-blue-300', emergency: 'bg-red-500 text-white', urgent: 'bg-orange-400 text-white', elective: 'bg-teal-500 text-white',
}
const todayIso = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` }

export default function OperationTheatres() {
  const { user } = useAuth()
  const toast = useToast()
  const [day, setDay] = useState(todayIso())
  const [sel, setSel] = useState<any>(null)
  const [bookOpen, setBookOpen] = useState(false)
  const [opt, setOpt] = useState<any>(null)
  const [optBusy, setOptBusy] = useState(false)
  const { data, loading, reload } = useApi<any>(`/api/surgeries?day=${day}`, ['surgeries', 'resources'], 30000)
  const [, tick] = useState(0)
  useEffect(() => { const id = setInterval(() => tick((t) => t + 1), 60000); return () => clearInterval(id) }, [])
  const canPlan = ['admin', 'doctor'].includes(user!.role)
  const isToday = day === todayIso()
  const surgeries = data?.surgeries || []
  const stats = useMemo(() => {
    const booked = surgeries.reduce((s: number, x: any) => s + x.duration_minutes, 0)
    const cap = Math.max(1, (data?.theatres || []).filter((t: any) => t.status !== 'maintenance').length * 12 * 60)
    const overtime = surgeries.reduce((s: number, x: any) => s + Math.max(0, minutesOf(x.end) - 20 * 60), 0)
    return { util: booked / cap, overtime }
  }, [surgeries, data])

  const act = async (s: any, action: string) => {
    try { await api(`/api/surgeries/${s.id}/${action}`, { method: 'POST' }); setSel(null); reload() } catch (e: any) { toast({ title: 'Failed', message: e.message, level: 'critical' }) }
  }
  const optimise = async () => {
    setOptBusy(true)
    try { setOpt(await api(`/api/ot/optimize?day=${day}`, { method: 'POST' })) } catch (e: any) { toast({ title: 'Optimiser failed', message: e.message, level: 'critical' }) } finally { setOptBusy(false) }
  }
  const applyOpt = async () => {
    await api('/api/ot/optimize/apply', { body: { assignments: opt.assignments.map((a: any) => ({ surgery_id: a.surgery_id, ot_id: a.ot_id, start: a.start })) } })
    toast({ title: 'Optimised schedule applied', message: `${opt.moved} case(s) moved`, level: 'success' })
    setOpt(null)
    reload()
  }

  return (
    <div>
      <PageHeader title="Operation theatres" icon={<Scissors className="h-5 w-5" />}
        subtitle="Theatre timeline, AI slot finder (turnover + surgeon availability) and CP-SAT day re-optimisation"
        actions={<>
          <input type="date" className="input w-40" value={day} onChange={(e) => setDay(e.target.value)} />
          {canPlan && <Button variant="secondary" icon={<Cpu className="h-4 w-4" />} loading={optBusy} onClick={optimise}>Optimise day (CP-SAT)</Button>}
          {canPlan && <Button icon={<CalendarPlus className="h-4 w-4" />} onClick={() => setBookOpen(true)}>Book surgery</Button>}
        </>} />
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Cases" value={surgeries.length} icon={<Scissors className="h-5 w-5" />} />
        <Stat label="In progress" value={surgeries.filter((s: any) => s.status === 'in_progress').length} tone="blue" />
        <Stat label="Completed" value={surgeries.filter((s: any) => s.status === 'completed').length} tone="emerald" />
        <Stat label="Theatre utilisation" value={`${Math.round(stats.util * 100)}%`} sub="booked minutes / 08:00–20:00 capacity" tone="violet" />
        <Stat label="Overtime past 20:00" value={`${stats.overtime} min`} tone={stats.overtime ? 'red' : 'slate'} />
      </div>

      <Card title="Theatre timeline" subtitle="Bars = surgery · hatched = 30-min turnover · red line = now">
        {loading && !data ? <Spinner /> : (
          <div className="overflow-x-auto">
            <div className="min-w-[760px]">
              <div className="relative ml-24 h-6 border-b border-slate-200">
                {Array.from({ length: END_H - START_H + 1 }, (_, i) => (
                  <span key={i} className="absolute -translate-x-1/2 text-[10px] text-slate-400" style={{ left: `${(i * 60 / SPAN) * 100}%` }}>{String(START_H + i).padStart(2, '0')}:00</span>
                ))}
              </div>
              {(data?.theatres || []).map((t: any) => (
                <div key={t.id} className="flex items-center border-b border-slate-100">
                  <div className="w-24 shrink-0 py-3 pr-2">
                    <div className="text-sm font-semibold text-slate-700">{t.name}</div>
                    <StatusBadge status={t.status} />
                  </div>
                  <div className="relative h-16 flex-1 bg-[repeating-linear-gradient(90deg,transparent,transparent_calc(100%/15-1px),#f1f5f9_calc(100%/15-1px),#f1f5f9_calc(100%/15))]">
                    <div className="absolute inset-y-0 bg-slate-100/70" style={{ left: `${pct(20 * 60)}%`, right: 0 }} title="after 20:00" />
                    {surgeries.filter((s: any) => s.ot_id === t.id).map((s: any) => {
                      const a = minutesOf(s.scheduled_start), b = a + s.duration_minutes
                      return (
                        <div key={s.id}>
                          <button onClick={() => setSel(s)} title={`${s.procedure} — ${s.patient?.name}`}
                            className={cls('absolute top-2 bottom-2 overflow-hidden rounded-md px-1.5 text-left text-[10px] leading-tight shadow-sm transition hover:brightness-110', BAR[s.status === 'scheduled' ? s.priority : s.status] || BAR.elective)}
                            style={{ left: `${pct(a)}%`, width: `${pct(b) - pct(a)}%` }}>
                            <div className="truncate font-semibold">{s.procedure}</div>
                            <div className="truncate opacity-90">{fmtTime(s.scheduled_start)} · {s.patient?.name}</div>
                          </button>
                          <div className="absolute top-4 bottom-4 rounded-r bg-[repeating-linear-gradient(45deg,#cbd5e1,#cbd5e1_3px,transparent_3px,transparent_6px)]"
                            style={{ left: `${pct(b)}%`, width: `${pct(b + 30) - pct(b)}%` }} />
                        </div>
                      )
                    })}
                    {isToday && <div className="absolute inset-y-0 w-0.5 bg-red-500" style={{ left: `${pct(new Date().getHours() * 60 + new Date().getMinutes())}%` }} />}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="mt-3 flex flex-wrap gap-3 text-[11px] text-slate-500">
          {Object.entries({ elective: 'Elective', urgent: 'Urgent', emergency: 'Emergency', in_progress: 'In progress', completed: 'Completed' }).map(([k, v]) => (
            <span key={k} className="flex items-center gap-1"><span className={cls('h-3 w-3 rounded', BAR[k].split(' ')[0])} />{v}</span>
          ))}
        </div>
      </Card>

      <Card className="mt-4" title="Theatre list" bodyClass="p-0">
        {!surgeries.length ? <Empty title="No surgeries on this day" /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs text-slate-500"><tr><th className="px-4 py-2">Time</th><th className="px-4 py-2">Theatre</th><th className="px-4 py-2">Procedure</th><th className="px-4 py-2">Patient</th><th className="px-4 py-2">Surgeon</th><th className="px-4 py-2">Priority</th><th className="px-4 py-2">Status</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {surgeries.map((s: any) => (
                  <tr key={s.id} onClick={() => setSel(s)} className="cursor-pointer hover:bg-slate-50">
                    <td className="px-4 py-2 tabular-nums">{fmtTime(s.scheduled_start)}–{fmtTime(s.end)}</td>
                    <td className="px-4 py-2">{s.ot}</td>
                    <td className="px-4 py-2 font-medium">{s.procedure}<div className="text-[11px] font-normal text-slate-500">{s.specialty} · {s.anaesthesia} · {s.duration_minutes} min</div></td>
                    <td className="px-4 py-2">{s.patient?.name}</td>
                    <td className="px-4 py-2 text-slate-600">{s.surgeon}</td>
                    <td className="px-4 py-2"><Badge tone={s.priority === 'emergency' ? 'red' : s.priority === 'urgent' ? 'orange' : 'teal'}>{s.priority}</Badge></td>
                    <td className="px-4 py-2"><StatusBadge status={s.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal open={!!sel} onClose={() => setSel(null)} title={sel?.procedure || ''}>
        {sel && (
          <div className="space-y-3 text-sm">
            <div className="flex flex-wrap gap-2"><StatusBadge status={sel.status} /><Badge tone={sel.priority === 'emergency' ? 'red' : sel.priority === 'urgent' ? 'orange' : 'teal'}>{sel.priority}</Badge><Badge>{sel.anaesthesia}</Badge></div>
            <dl className="grid grid-cols-2 gap-2">
              <div><dt className="text-xs text-slate-500">Patient</dt><dd><Link className="text-teal-700 hover:underline" to={`/patients/${sel.patient?.id}`}>{sel.patient?.name}</Link></dd></div>
              <div><dt className="text-xs text-slate-500">Surgeon</dt><dd>{sel.surgeon || '—'}</dd></div>
              <div><dt className="text-xs text-slate-500">Theatre</dt><dd>{sel.ot}</dd></div>
              <div><dt className="text-xs text-slate-500">Time</dt><dd>{fmtTime(sel.scheduled_start)}–{fmtTime(sel.end)} ({sel.duration_minutes} min)</dd></div>
            </dl>
            <div className="flex gap-2 border-t border-slate-100 pt-3">
              {sel.status === 'scheduled' && <Button size="sm" onClick={() => act(sel, 'start')}>Start (patient in theatre)</Button>}
              {sel.status === 'in_progress' && <Button size="sm" variant="success" onClick={() => act(sel, 'complete')}>Complete → recovery</Button>}
              {sel.status === 'scheduled' && <Button size="sm" variant="secondary" onClick={() => act(sel, 'cancel')}>Cancel</Button>}
            </div>
          </div>
        )}
      </Modal>

      <Modal open={!!opt} onClose={() => setOpt(null)} title="CP-SAT theatre re-optimisation" wide
        footer={opt?.assignments?.length ? <><Button variant="secondary" onClick={() => setOpt(null)}>Discard</Button><Button onClick={applyOpt} disabled={!opt.moved}>Apply {opt.moved} change(s)</Button></> : <Button onClick={() => setOpt(null)}>Close</Button>}>
        {opt && (!opt.assignments?.length ? <Empty title="Nothing to optimise" hint={`Status: ${opt.status} — only not-yet-started surgeries can be moved`} /> : (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-2 text-center text-sm">
              {[['Overlaps', 'conflicts'], ['Overtime (min)', 'overtime_minutes'], ['Last case ends', 'makespan']].map(([l, k]) => (
                <div key={k} className="rounded-lg bg-slate-50 p-3"><div className="text-xs text-slate-500">{l}</div><div className="mt-1 font-semibold"><span className="text-slate-400 line-through">{opt.before[k]}</span> → <span className="text-teal-700">{opt.after[k]}</span></div></div>
              ))}
            </div>
            <div className="text-xs text-slate-500">{opt.solver} · {opt.status} · {opt.wall_ms} ms · {opt.movable} movable case(s). Constraints: no theatre/surgeon overlap, 30-min turnover; objective: priority-weighted start times + overtime + makespan.</div>
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-slate-500"><tr><th className="py-1">Case</th><th>Before</th><th>After</th></tr></thead>
              <tbody className="divide-y divide-slate-100">{opt.assignments.map((a: any) => (
                <tr key={a.surgery_id} className={a.moved ? 'bg-teal-50/50' : ''}><td className="py-1.5">{a.procedure}<div className="text-[11px] text-slate-500">{a.patient} · {a.priority}</div></td>
                  <td className="text-slate-500">{a.old_ot} {fmtTime(a.old_start)}</td><td className="font-medium">{a.ot} {fmtTime(a.start)}</td></tr>))}</tbody>
            </table>
          </div>
        ))}
      </Modal>

      <BookModal open={bookOpen} day={day} onClose={() => setBookOpen(false)} onBooked={() => { setBookOpen(false); reload() }} />
    </div>
  )
}

function BookModal({ open, day, onClose, onBooked }: { open: boolean; day: string; onClose: () => void; onBooked: () => void }) {
  const toast = useToast()
  const procs = useApi<any[]>(open ? '/api/ot/procedures' : null)
  const patients = useApi<any>(open ? '/api/patients?limit=300' : null)
  const doctors = useApi<any[]>(open ? '/api/staff?role=doctor' : null)
  const [f, setF] = useState({ patient_id: '', procedure_key: 'appendectomy', surgeon_id: '', priority: 'elective', day })
  const [slots, setSlots] = useState<any[] | null>(null)
  const [pick, setPick] = useState(0)
  const [busy, setBusy] = useState(false)
  useEffect(() => { if (open) { setSlots(null); setF((x) => ({ ...x, day })) } }, [open, day])
  const proc = (procs.data || []).find((p) => p.key === f.procedure_key)
  const surgeons = (doctors.data || []).filter((d) => !proc || d.department === proc.specialty)
  const find = async () => {
    const q = new URLSearchParams({ duration: String(proc?.duration || 60), priority: f.priority, day: f.day })
    if (f.surgeon_id) q.set('surgeon_id', f.surgeon_id)
    setSlots(await api(`/api/ot/slots?${q}`))
    setPick(0)
  }
  const book = async () => {
    const s = slots![pick]
    setBusy(true)
    try {
      await api('/api/surgeries', { body: { patient_id: Number(f.patient_id), procedure_key: f.procedure_key, surgeon_id: f.surgeon_id ? Number(f.surgeon_id) : null, priority: f.priority, ot_id: s.ot_id, scheduled_start: s.start } })
      toast({ title: 'Surgery booked', message: `${proc?.name} — ${s.ot} at ${fmtTime(s.start)}`, level: 'success' })
      onBooked()
    } catch (e: any) { toast({ title: 'Booking failed', message: e.message, level: 'critical' }) } finally { setBusy(false) }
  }
  return (
    <Modal open={open} onClose={onClose} title="Book surgery" wide
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button>{slots ? <Button loading={busy} onClick={book} disabled={!slots.length || !f.patient_id}>Book selected slot</Button> : <Button onClick={find} disabled={!f.patient_id}>Find best slots</Button>}</>}>
      <div className="grid gap-3 md:grid-cols-2">
        <Field label="Patient"><select className="input" value={f.patient_id} onChange={(e) => setF({ ...f, patient_id: e.target.value })}><option value="">Select…</option>{(patients.data?.items || []).map((p: any) => <option key={p.id} value={p.id}>{p.name} · {p.mrn}</option>)}</select></Field>
        <Field label="Procedure"><select className="input" value={f.procedure_key} onChange={(e) => { setF({ ...f, procedure_key: e.target.value, surgeon_id: '' }); setSlots(null) }}>{(procs.data || []).map((p) => <option key={p.key} value={p.key}>{p.name} ({p.duration} min)</option>)}</select></Field>
        <Field label={`Surgeon${proc ? ` — ${proc.specialty}` : ''}`}><select className="input" value={f.surgeon_id} onChange={(e) => { setF({ ...f, surgeon_id: e.target.value }); setSlots(null) }}><option value="">Any available</option>{surgeons.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Priority"><select className="input" value={f.priority} onChange={(e) => { setF({ ...f, priority: e.target.value }); setSlots(null) }}><option value="elective">Elective</option><option value="urgent">Urgent</option><option value="emergency">Emergency</option></select></Field>
          <Field label="Day"><input className="input" type="date" value={f.day} onChange={(e) => { setF({ ...f, day: e.target.value }); setSlots(null) }} /></Field>
        </div>
      </div>
      {slots && (
        <div className="mt-4 space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Ranked slot options (explainable cost)</div>
          {!slots.length && <Empty title="No feasible slot that day" hint="Try another day, surgeon or priority" />}
          {slots.map((s, i) => (
            <label key={i} className={cls('block cursor-pointer rounded-lg border p-3', pick === i ? 'border-teal-400 bg-teal-50/50' : 'border-slate-200')}>
              <div className="flex items-center gap-2"><input type="radio" checked={pick === i} onChange={() => setPick(i)} /><span className="font-medium">{s.ot} · {fmtTime(s.start)}–{fmtTime(s.end)}</span><Badge tone="slate">cost {s.cost}</Badge><span className="ml-auto text-xs text-slate-500">wait {s.wait_minutes} min</span></div>
              <Factors factors={s.factors} />
            </label>
          ))}
        </div>
      )}
    </Modal>
  )
}
