import { useState } from 'react'
import { CalendarClock, Clock, Plus, Users } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import { Badge, Button, Card, Empty, Factors, Field, Modal, Progress, Spinner, StatusBadge, Tabs, useToast } from '../components/ui'
import { useApi } from '../live'
import { cls, fmtTime } from '../utils'

type Tab = 'queue' | 'list'

export default function Opd() {
  const [tab, setTab] = useState<Tab>('queue')
  const [open, setOpen] = useState(false)
  return (
    <div>
      <PageHeader title="OPD appointments & live queue" icon={<CalendarClock className="h-5 w-5" />}
        subtitle="Dynamic queue prioritisation with ageing, per-patient ETA and M/M/c queueing-theory wait predictions"
        actions={<><Tabs<Tab> value={tab} onChange={setTab} tabs={[{ id: 'queue', label: 'Live queue' }, { id: 'list', label: "Today's appointments" }]} />
          <Button icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>Book</Button></>} />
      {tab === 'queue' ? <Queue /> : <List />}
      <BookModal open={open} onClose={() => setOpen(false)} />
    </div>
  )
}

function Queue() {
  const { data, loading } = useApi<any[]>('/api/queue', ['appointments'], 20000)
  if (loading && !data) return <Spinner />
  if (!data?.length) return <Empty title="No OPD activity today" />
  return (
    <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
      {data.map((d) => (
        <Card key={d.department.id} title={d.department.name} subtitle={`${d.doctors_on_duty} doctor(s) on duty · ~${d.department.avg_consult_minutes} min/consult`}
          actions={<Badge tone={d.waiting > 5 ? 'orange' : 'teal'}><Users className="h-3 w-3" />{d.waiting} waiting</Badge>}>
          <div className="mb-3 grid grid-cols-3 gap-2 text-center">
            <div className="rounded-lg bg-slate-50 p-2"><div className="text-[10px] text-slate-500">Utilisation ρ</div><div className={cls('text-sm font-semibold', d.metrics.utilization > 0.85 ? 'text-red-600' : 'text-slate-800')}>{(d.metrics.utilization * 100).toFixed(0)}%</div></div>
            <div className="rounded-lg bg-slate-50 p-2"><div className="text-[10px] text-slate-500">P(wait)</div><div className="text-sm font-semibold">{(d.metrics.p_wait * 100).toFixed(0)}%</div></div>
            <div className="rounded-lg bg-slate-50 p-2"><div className="text-[10px] text-slate-500">Wq (M/M/c)</div><div className="text-sm font-semibold">{d.metrics.wq_minutes ?? '∞'} min</div></div>
          </div>
          <Progress value={d.completed} max={d.booked} tone="bg-teal-500" />
          <div className="mb-3 mt-1 text-[10px] text-slate-400">{d.completed}/{d.booked} consultations completed today</div>
          {d.queue.length === 0 ? <div className="py-4 text-center text-xs text-slate-400">Queue empty</div> : (
            <div className="space-y-1.5">
              {d.queue.map((a: any) => <QueueRow key={a.id} a={a} />)}
            </div>
          )}
        </Card>
      ))}
    </div>
  )
}

function QueueRow({ a }: { a: any }) {
  const [open, setOpen] = useState(false)
  const toast = useToast()
  const act = async (action: string) => {
    try { await api(`/api/appointments/${a.id}/${action}`, { method: 'POST' }) } catch (e: any) { toast({ title: 'Failed', message: e.message, level: 'critical' }) }
  }
  return (
    <div className={cls('rounded-lg border p-2', a.status === 'in_progress' ? 'border-blue-200 bg-blue-50/50' : 'border-slate-100')}>
      <div className="flex items-center gap-2">
        <span className={cls('flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-bold', a.status === 'in_progress' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600')}>{a.position || '▶'}</span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium text-slate-800">{a.patient?.name} <span className="text-xs font-normal text-slate-400">{a.patient?.age}{a.patient?.gender?.[0]}</span></div>
          <div className="truncate text-[11px] text-slate-500">{a.doctor} · waited {a.waited_minutes} min</div>
        </div>
        <div className="text-right">
          {a.status === 'in_progress' ? <Badge tone="blue">in consultation</Badge> : <div className="flex items-center gap-1 text-xs font-semibold text-slate-700"><Clock className="h-3 w-3" />ETA {a.eta_minutes}m</div>}
          {a.priority_score !== undefined && <button onClick={() => setOpen((o) => !o)} className="text-[10px] text-teal-700 hover:underline">score {a.priority_score}</button>}
        </div>
        {a.status === 'checked_in' && <Button size="sm" variant="secondary" onClick={() => act('start')}>Call</Button>}
        {a.status === 'in_progress' && <Button size="sm" variant="success" onClick={() => act('complete')}>Done</Button>}
      </div>
      {open && <Factors factors={a.factors} />}
    </div>
  )
}

function List() {
  const { data, loading } = useApi<any[]>('/api/appointments', ['appointments'])
  const toast = useToast()
  const act = async (id: number, action: string) => {
    try { await api(`/api/appointments/${id}/${action}`, { method: 'POST' }) } catch (e: any) { toast({ title: 'Failed', message: e.message, level: 'critical' }) }
  }
  if (loading && !data) return <Spinner />
  return (
    <Card bodyClass="p-0">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs text-slate-500"><tr><th className="px-4 py-2">Time</th><th className="px-4 py-2">#</th><th className="px-4 py-2">Patient</th><th className="px-4 py-2">Department</th><th className="px-4 py-2">Doctor</th><th className="px-4 py-2">Reason</th><th className="px-4 py-2">Booked via</th><th className="px-4 py-2">Status</th><th className="px-4 py-2"></th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {(data || []).map((a) => (
              <tr key={a.id} className="hover:bg-slate-50">
                <td className="px-4 py-2 tabular-nums">{fmtTime(a.scheduled_at)}</td>
                <td className="px-4 py-2 text-slate-400">{a.queue_number}</td>
                <td className="px-4 py-2 font-medium">{a.patient?.name}</td>
                <td className="px-4 py-2 text-slate-600">{a.department}</td>
                <td className="px-4 py-2 text-slate-600">{a.doctor}</td>
                <td className="px-4 py-2 text-slate-500">{a.reason}</td>
                <td className="px-4 py-2 text-xs text-slate-500">{a.booked_by}</td>
                <td className="px-4 py-2"><StatusBadge status={a.status} /></td>
                <td className="px-4 py-2 text-right">
                  {a.status === 'scheduled' && <Button size="sm" variant="secondary" onClick={() => act(a.id, 'check_in')}>Check in</Button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function BookModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast()
  const patients = useApi<any>(open ? '/api/patients?limit=300' : null)
  const doctors = useApi<any[]>(open ? '/api/staff?role=doctor' : null)
  const now = new Date(Date.now() + 3600e3)
  const [f, setF] = useState({ patient_id: '', doctor_id: '', when: `${now.toISOString().slice(0, 11)}${String(now.getHours()).padStart(2, '0')}:00`, priority: 3, reason: '' })
  const [busy, setBusy] = useState(false)
  const save = async () => {
    setBusy(true)
    try {
      await api('/api/appointments', { body: { patient_id: Number(f.patient_id), doctor_id: Number(f.doctor_id), scheduled_at: f.when, priority: Number(f.priority), reason: f.reason } })
      toast({ title: 'Appointment booked', level: 'success' })
      onClose()
    } catch (e: any) { toast({ title: 'Booking failed', message: e.message, level: 'critical' }) } finally { setBusy(false) }
  }
  return (
    <Modal open={open} onClose={onClose} title="Book appointment" footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={busy} onClick={save} disabled={!f.patient_id || !f.doctor_id}>Book</Button></>}>
      <div className="space-y-3">
        <p className="rounded-lg bg-teal-50 p-2 text-xs text-teal-800">Tip: the Appointment & Queue Agent can pick the best doctor & slot for you — try “Book an appointment with a cardiologist tomorrow at 11 am for …” in the AI Agent Console.</p>
        <Field label="Patient"><select className="input" value={f.patient_id} onChange={(e) => setF({ ...f, patient_id: e.target.value })}><option value="">Select…</option>{(patients.data?.items || []).map((p: any) => <option key={p.id} value={p.id}>{p.name} · {p.mrn}</option>)}</select></Field>
        <Field label="Doctor"><select className="input" value={f.doctor_id} onChange={(e) => setF({ ...f, doctor_id: e.target.value })}><option value="">Select…</option>{(doctors.data || []).map((d) => <option key={d.id} value={d.id}>{d.name} — {d.specialization}</option>)}</select></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Date & time"><input className="input" type="datetime-local" value={f.when} onChange={(e) => setF({ ...f, when: e.target.value })} /></Field>
          <Field label="Priority"><select className="input" value={f.priority} onChange={(e) => setF({ ...f, priority: Number(e.target.value) })}>{[1, 2, 3, 4, 5].map((p) => <option key={p} value={p}>{p} {p === 1 ? '(highest)' : p === 5 ? '(lowest)' : ''}</option>)}</select></Field>
        </div>
        <Field label="Reason"><input className="input" value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} /></Field>
      </div>
    </Modal>
  )
}
