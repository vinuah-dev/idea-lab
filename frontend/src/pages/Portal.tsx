import { useState } from 'react'
import { CalendarClock, CheckCircle2, FlaskConical, HeartPulse, Loader2, Pill, Sparkles } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, Card, Empty, Field, Spinner, StatusBadge, useToast } from '../components/ui'
import { useApi } from '../live'
import { cls, fmtDateTime } from '../utils'

const CLINICAL = ['General Medicine', 'Cardiology', 'Neurology', 'Orthopedics', 'Pediatrics', 'Obstetrics & Gynecology', 'Pulmonology', 'Oncology', 'General Surgery']

export default function Portal() {
  const toast = useToast()
  const { data, loading, reload } = useApi<any>('/api/portal/me', ['appointments', 'diagnostics', 'pharmacy'])
  const [form, setForm] = useState({ department: 'Cardiology', preferred: '', reason: '' })
  const [booking, setBooking] = useState<{ status: string; summary?: string } | null>(null)

  const book = async () => {
    setBooking({ status: 'running' })
    try {
      const r = await api('/api/portal/appointments', { body: { department: form.department, preferred: form.preferred || null, reason: form.reason } })
      for (let i = 0; i < 30; i++) {
        await new Promise((res) => setTimeout(res, 700))
        const s = await api(`/api/portal/requests/${r.request_id}`)
        if (['completed', 'awaiting_approval', 'failed', 'rejected'].includes(s.status)) {
          setBooking(s)
          reload()
          toast({ title: s.status === 'completed' ? 'Appointment booked' : 'Request submitted', level: s.status === 'completed' ? 'success' : 'info' })
          return
        }
      }
    } catch (e: any) {
      setBooking(null)
      toast({ title: 'Booking failed', message: e.message, level: 'critical' })
    }
  }

  if (loading && !data) return <Spinner />
  if (!data) return <Empty title="No patient record linked" />
  const p = data.patient
  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-5 rounded-2xl bg-gradient-to-br from-teal-600 to-teal-800 p-6 text-white shadow">
        <div className="flex flex-wrap items-center gap-4">
          <div className="rounded-xl bg-white/15 p-3"><HeartPulse className="h-7 w-7" /></div>
          <div>
            <div className="text-sm text-teal-100">Welcome back</div>
            <h1 className="text-2xl font-semibold">{p.name}</h1>
            <div className="text-sm text-teal-100">{p.mrn} · {p.age} yrs · {p.gender} · Blood group {p.blood_group}</div>
          </div>
          <div className="ml-auto flex flex-wrap gap-1.5">
            {p.allergies.map((a: string) => <span key={a} className="rounded-full bg-red-500/90 px-2.5 py-1 text-xs font-medium">⚠ Allergy: {a}</span>)}
            {p.conditions.map((c: string) => <span key={c} className="rounded-full bg-white/15 px-2.5 py-1 text-xs">{c}</span>)}
          </div>
        </div>
        {data.admission && <div className="mt-4 rounded-lg bg-white/10 p-3 text-sm">Currently admitted: {data.admission.ward} · bed {data.admission.bed} · under {data.admission.doctor}</div>}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Book an appointment" subtitle="Our Appointment Agent finds the best doctor and the earliest slot for you" icon={<Sparkles className="h-4 w-4" />}>
          <div className="space-y-3">
            <Field label="Department"><select className="input" value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })}>{CLINICAL.map((d) => <option key={d}>{d}</option>)}</select></Field>
            <Field label="Preferred date & time (optional)"><input type="datetime-local" className="input" value={form.preferred} onChange={(e) => setForm({ ...form, preferred: e.target.value })} /></Field>
            <Field label="Reason for visit"><input className="input" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} placeholder="e.g. follow-up for blood pressure" /></Field>
            <Button className="w-full" onClick={book} loading={booking?.status === 'running'} icon={<CalendarClock className="h-4 w-4" />}>Find & book the best slot</Button>
            {booking && booking.status !== 'running' && (
              <div className={cls('rounded-lg p-3 text-sm', booking.status === 'completed' ? 'bg-emerald-50 text-emerald-800' : 'bg-amber-50 text-amber-800')}>
                <div className="mb-1 flex items-center gap-2 font-medium"><CheckCircle2 className="h-4 w-4" />{booking.status === 'completed' ? 'Confirmed' : booking.status}</div>
                <div className="whitespace-pre-wrap text-xs">{booking.summary}</div>
              </div>
            )}
            {booking?.status === 'running' && <div className="flex items-center gap-2 text-xs text-slate-500"><Loader2 className="h-3 w-3 animate-spin" />Agents are checking doctor availability and queues…</div>}
          </div>
        </Card>

        <Card title="Upcoming appointments" icon={<CalendarClock className="h-4 w-4" />}>
          {!data.upcoming.length ? <Empty title="No upcoming appointments" /> : data.upcoming.map((a: any) => (
            <div key={a.id} className="mb-2 flex items-center gap-3 rounded-lg border border-slate-100 p-3">
              <div className="rounded-lg bg-indigo-50 p-2 text-indigo-600"><CalendarClock className="h-4 w-4" /></div>
              <div className="min-w-0 flex-1">
                <div className="font-medium text-slate-800">{fmtDateTime(a.scheduled_at)}</div>
                <div className="text-xs text-slate-500">{a.doctor} · {a.department} · token #{a.queue_number}</div>
              </div>
              <StatusBadge status={a.status} />
            </div>
          ))}
          {data.past.length > 0 && <div className="mt-3 text-xs text-slate-400">{data.past.length} past visit(s) — last on {fmtDateTime(data.past[0].scheduled_at)}</div>}
        </Card>

        <Card title="My reports" icon={<FlaskConical className="h-4 w-4" />}>
          {!data.reports.length ? <Empty title="No reports yet" /> : data.reports.map((o: any) => (
            <div key={o.id} className="mb-2 rounded-lg border border-slate-100 p-3">
              <div className="flex items-center gap-2"><span className="font-medium text-slate-800">{o.test_name}</span>{o.abnormal && <Badge tone="amber">review with doctor</Badge>}<span className="ml-auto"><StatusBadge status={o.status} /></span></div>
              {o.result && <div className="mt-1 text-sm text-slate-600">{o.result}</div>}
              <div className="mt-0.5 text-[11px] text-slate-400">{fmtDateTime(o.completed_at || o.created_at)}</div>
            </div>
          ))}
        </Card>

        <Card title="My medicines" icon={<Pill className="h-4 w-4" />}>
          {!data.prescriptions.length ? <Empty title="No prescriptions" /> : data.prescriptions.map((r: any) => (
            <div key={r.id} className="mb-2 flex items-center gap-3 rounded-lg border border-slate-100 p-3">
              <div className="rounded-lg bg-emerald-50 p-2 text-emerald-600"><Pill className="h-4 w-4" /></div>
              <div className="min-w-0 flex-1"><div className="font-medium text-slate-800">{r.medication} {r.dose}</div><div className="text-xs text-slate-500">{r.frequency} for {r.duration_days} days · {r.doctor}</div></div>
              <StatusBadge status={r.status} />
            </div>
          ))}
        </Card>
      </div>
      <p className="mt-6 text-center text-xs text-slate-400">Reminders and results are informational. Please consult your doctor for medical advice.</p>
    </div>
  )
}
