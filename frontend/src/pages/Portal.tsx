import { useState } from 'react'
import { CalendarClock, CheckCircle2, Eye, FlaskConical, HeartPulse, Loader2, Pill, Printer, Receipt, ShieldCheck, Sparkles } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, Card, Empty, Field, Spinner, StatusBadge, useToast } from '../components/ui'
import { useApi } from '../live'
import { ago, cls, fmtDateTime, inr } from '../utils'

const CLINICAL = ['General Medicine', 'Cardiology', 'Neurology', 'Orthopedics', 'Pediatrics', 'Obstetrics & Gynecology', 'Pulmonology', 'Oncology', 'General Surgery']

export default function Portal() {
  const toast = useToast()
  const { data, loading, reload } = useApi<any>('/api/portal/me', ['appointments', 'diagnostics', 'pharmacy'])
  const [form, setForm] = useState({ department: 'Cardiology', preferred: '', reason: '' })
  const [booking, setBooking] = useState<{ status: string; summary?: string } | null>(null)
  const bill = useApi<any>('/api/portal/bill', ['billing'])
  const access = useApi<any[]>('/api/portal/access-log')
  const [paying, setPaying] = useState(false)
  const pay = async (amount: number) => {
    setPaying(true)
    try {
      const r = await api('/api/portal/pay', { body: { amount } })
      toast({ title: `Paid ${inr(r.amount)}`, message: `Demo UPI reference ${r.reference} — no real money was charged.`, level: 'success' })
      bill.reload()
    } catch (e: any) { toast({ title: 'Payment failed', message: e.message, level: 'critical' }) } finally { setPaying(false) }
  }

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

        <Card title="My bill" icon={<Receipt className="h-4 w-4" />} subtitle={bill.data?.payer_label}>
          {!bill.data ? <Spinner /> : !bill.data.invoice ? <Empty title="Nothing to pay" hint="Charges appear here automatically after a visit, test or admission" /> : (() => {
            const s = bill.data.invoice.summary
            return (
              <div>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div className="rounded-lg bg-slate-50 p-2"><div className="text-[11px] text-slate-500">Total charges</div><div className="font-semibold tabular-nums">{inr(s.gross)}</div></div>
                  <div className="rounded-lg bg-emerald-50 p-2"><div className="text-[11px] text-emerald-700">Covered by insurance / scheme</div><div className="font-semibold tabular-nums text-emerald-800">{inr(s.expected_insurance)}</div></div>
                  <div className="rounded-lg bg-slate-50 p-2"><div className="text-[11px] text-slate-500">Paid so far</div><div className="font-semibold tabular-nums">{inr(s.paid)}</div></div>
                  <div className={cls('rounded-lg p-2', s.balance > 0 ? 'bg-amber-50' : 'bg-emerald-50')}><div className="text-[11px] text-slate-600">Balance</div><div className="font-semibold tabular-nums">{inr(s.balance)}</div></div>
                </div>
                {s.claim_status && <div className="mt-2 text-xs text-slate-600"><ShieldCheck className="mr-1 inline h-3.5 w-3.5 text-emerald-600" />Insurance claim: <StatusBadge status={s.claim_status} /></div>}
                <div className="mt-3 flex gap-2">
                  {s.balance > 0 && <Button className="flex-1" loading={paying} onClick={() => pay(s.balance)}>Pay {inr(s.balance)} via UPI (demo)</Button>}
                  <a href={`/print/invoice/${bill.data.invoice.id}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-teal-700 ring-1 ring-inset ring-teal-200 hover:bg-teal-50"><Printer className="h-4 w-4" />Itemised bill</a>
                </div>
              </div>
            )
          })()}
        </Card>

        <Card title="Who accessed my record" icon={<Eye className="h-4 w-4" />} subtitle="Every staff access to your record is logged (DPDP Act 2023 transparency)">
          {!access.data?.length ? <Empty title="No access recorded yet" /> : (
            <div className="max-h-56 divide-y divide-slate-100 overflow-y-auto">
              {access.data.map((a, i) => (
                <div key={i} className="flex items-center gap-2 py-1.5 text-sm">
                  <span className="font-medium text-slate-800">{a.actor}</span><Badge>{a.role}</Badge>
                  <span className="text-xs text-slate-500">{a.action}</span><span className="ml-auto text-[11px] text-slate-400">{ago(a.timestamp)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
      <p className="mt-6 text-center text-xs text-slate-400">Reminders and results are informational. Please consult your doctor for medical advice.</p>
    </div>
  )
}
