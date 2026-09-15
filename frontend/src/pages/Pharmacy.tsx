import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Pill, ShieldCheck } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import { Badge, Button, Card, Empty, Field, Progress, Spinner, StatusBadge, Tabs, useToast } from '../components/ui'
import { useAuth } from '../auth'
import { useApi } from '../live'
import { ago, cls, fmtDate } from '../utils'

type Tab = 'rx' | 'inventory' | 'safety'

export default function Pharmacy() {
  const [tab, setTab] = useState<Tab>('rx')
  return (
    <div>
      <PageHeader title="Pharmacy coordination" icon={<Pill className="h-5 w-5" />} subtitle="Prescription verification with allergy, interaction and dose screening; inventory and replenishment"
        actions={<Tabs<Tab> value={tab} onChange={setTab} tabs={[{ id: 'rx', label: 'Prescription queue' }, { id: 'inventory', label: 'Inventory' }, { id: 'safety', label: 'Safety checker' }]} />} />
      {tab === 'rx' && <RxQueue />}
      {tab === 'inventory' && <Inventory />}
      {tab === 'safety' && <SafetyChecker />}
    </div>
  )
}

function RxQueue() {
  const { user } = useAuth()
  const toast = useToast()
  const [status, setStatus] = useState('pending')
  const { data, loading } = useApi<any[]>(`/api/prescriptions?status=${status}`, ['pharmacy'])
  const can = ['admin', 'pharmacist'].includes(user!.role)
  const act = async (id: number, action: string) => {
    try { await api(`/api/prescriptions/${id}/${action}`, { method: 'POST' }); toast({ title: `Prescription ${action === 'verify' ? 'verified' : action === 'dispense' ? 'dispensed' : 'rejected'}`, level: 'success' }) }
    catch (e: any) { toast({ title: 'Action blocked', message: e.message, level: 'critical' }) }
  }
  return (
    <Card title="Prescriptions" actions={<select className="input w-40 py-1 text-xs" value={status} onChange={(e) => setStatus(e.target.value)}>{['pending', 'verified', 'dispensed', 'rejected'].map((s) => <option key={s}>{s}</option>)}</select>} bodyClass="p-0">
      {loading && !data ? <Spinner /> : !data?.length ? <Empty title={`No ${status} prescriptions`} /> : (
        <div className="divide-y divide-slate-100">
          {data.map((r) => (
            <div key={r.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2"><span className="font-medium text-slate-800">{r.medication}</span><span className="text-sm text-slate-500">{r.dose} · {r.frequency} × {r.duration_days}d · qty {r.quantity}</span><StatusBadge status={r.status} /></div>
                <div className="text-xs text-slate-500"><Link to={`/patients/${r.patient?.id}`} className="text-teal-700 hover:underline">{r.patient?.name}</Link> · {r.doctor || 'AI orchestrator'} · {ago(r.created_at)}</div>
                {r.alerts.length > 0 && <div className="mt-1.5 flex flex-wrap gap-1">{r.alerts.map((a: any, i: number) => (
                  <span key={i} className={cls('inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px]', a.severity === 'contraindicated' ? 'bg-red-100 text-red-800' : a.severity === 'major' ? 'bg-orange-100 text-orange-800' : 'bg-amber-50 text-amber-800')}>
                    <AlertTriangle className="h-3 w-3" />{a.message}</span>))}</div>}
              </div>
              {can && r.status === 'pending' && <><Button size="sm" variant="success" onClick={() => act(r.id, 'verify')}>Verify</Button><Button size="sm" variant="secondary" onClick={() => act(r.id, 'reject')}>Reject</Button></>}
              {can && r.status === 'verified' && <Button size="sm" onClick={() => act(r.id, 'dispense')}>Dispense</Button>}
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function Inventory() {
  const { user } = useAuth()
  const { data, loading, reload } = useApi<any[]>('/api/medications', ['pharmacy'])
  const [edit, setEdit] = useState<Record<number, string>>({})
  const [filter, setFilter] = useState<'all' | 'low'>('all')
  const can = ['admin', 'pharmacist'].includes(user!.role)
  const save = async (m: any) => {
    await api(`/api/medications/${m.id}`, { method: 'PATCH', body: { stock: Number(edit[m.id]) } })
    setEdit((e) => { const n = { ...e }; delete n[m.id]; return n })
    reload()
  }
  if (loading && !data) return <Spinner />
  const rows = (data || []).filter((m) => filter === 'all' || m.low_stock)
  return (
    <Card title="Formulary inventory" subtitle={`${(data || []).filter((m) => m.low_stock).length} items at or below reorder level — ask the Pharmacy Agent “Which medicines are running low?” to raise a purchase order`}
      actions={<Tabs value={filter} onChange={setFilter} tabs={[{ id: 'all', label: 'All' }, { id: 'low', label: 'Low stock' }]} />} bodyClass="p-0">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs text-slate-500"><tr><th className="px-4 py-2">Medicine</th><th className="px-4 py-2">Class</th><th className="px-4 py-2">Form</th><th className="w-56 px-4 py-2">Stock vs reorder level</th><th className="px-4 py-2">Days left</th><th className="px-4 py-2">Expiry</th><th className="px-4 py-2">Unit ₹</th>{can && <th className="px-4 py-2">Adjust</th>}</tr></thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((m) => (
              <tr key={m.id} className={m.low_stock ? 'bg-red-50/40' : ''}>
                <td className="px-4 py-2"><div className="font-medium text-slate-800">{m.name} <span className="text-xs font-normal text-slate-400">{m.strength}</span></div><div className="text-[11px] text-slate-400">{m.generic}</div></td>
                <td className="px-4 py-2 text-xs text-slate-600">{m.drug_class}</td>
                <td className="px-4 py-2 text-xs text-slate-600">{m.form}</td>
                <td className="px-4 py-2"><div className="mb-1 flex justify-between text-[11px]"><span className={m.low_stock ? 'font-semibold text-red-700' : 'text-slate-600'}>{m.stock}</span><span className="text-slate-400">reorder {m.reorder_level}</span></div>
                  <Progress value={m.stock} max={m.reorder_level * 3} tone={m.low_stock ? 'bg-red-500' : 'bg-emerald-500'} /></td>
                <td className="px-4 py-2 tabular-nums text-slate-600">{m.days_of_stock}</td>
                <td className="px-4 py-2 text-xs">{m.expiry && new Date(m.expiry).getTime() - Date.now() < 60 * 864e5 ? <Badge tone="amber">{fmtDate(m.expiry)}</Badge> : fmtDate(m.expiry)}</td>
                <td className="px-4 py-2 text-xs tabular-nums text-slate-600">{m.unit_price}</td>
                {can && <td className="px-4 py-2"><div className="flex gap-1"><input className="w-20 rounded border border-slate-200 px-1.5 py-0.5 text-xs" placeholder={String(m.stock)} value={edit[m.id] ?? ''} onChange={(e) => setEdit({ ...edit, [m.id]: e.target.value })} />
                  {edit[m.id] && <Button size="sm" onClick={() => save(m)}>Save</Button>}</div></td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function SafetyChecker() {
  const patients = useApi<any>('/api/patients?limit=300')
  const meds = useApi<any[]>('/api/medications')
  const [pid, setPid] = useState('')
  const [mid, setMid] = useState('')
  const [res, setRes] = useState<any>(null)
  const check = async () => setRes(await api('/api/pharmacy/check', { body: { patient_id: Number(pid), medication_id: Number(mid) } }))
  const patient = (patients.data?.items || []).find((p: any) => String(p.id) === pid)
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Prescription safety check" subtitle="Allergy cross-reactivity + drug–drug interactions against the patient's active medicines" icon={<ShieldCheck className="h-4 w-4" />}>
        <div className="space-y-3">
          <Field label="Patient"><select className="input" value={pid} onChange={(e) => { setPid(e.target.value); setRes(null) }}><option value="">Select…</option>{(patients.data?.items || []).map((p: any) => <option key={p.id} value={p.id}>{p.name} · {p.mrn}{p.allergies.length ? ` · ⚠ ${p.allergies.join(', ')}` : ''}</option>)}</select></Field>
          <Field label="Medication"><select className="input" value={mid} onChange={(e) => { setMid(e.target.value); setRes(null) }}><option value="">Select…</option>{(meds.data || []).map((m) => <option key={m.id} value={m.id}>{m.name} {m.strength} ({m.drug_class})</option>)}</select></Field>
          <Button onClick={check} disabled={!pid || !mid} icon={<ShieldCheck className="h-4 w-4" />}>Run safety check</Button>
          <p className="text-xs text-slate-400">Try a patient with a penicillin allergy + Amoxicillin, or a patient on Warfarin + Aspirin.</p>
        </div>
      </Card>
      <Card title="Result">
        {!res ? <Empty title="Choose a patient and a medicine" /> : res.alerts.length === 0 ? (
          <div className="flex items-center gap-3 rounded-lg bg-emerald-50 p-4 text-emerald-800"><ShieldCheck className="h-6 w-6" /><div><div className="font-semibold">No safety alerts</div><div className="text-sm">In stock: {res.stock}. {patient?.allergies?.length ? `Checked against allergies: ${patient.allergies.join(', ')}` : 'No allergies recorded.'}</div></div></div>
        ) : (
          <div className="space-y-2">
            {res.alerts.map((a: any, i: number) => (
              <div key={i} className={cls('rounded-lg p-3', a.severity === 'contraindicated' ? 'bg-red-50 text-red-800' : 'bg-orange-50 text-orange-800')}>
                <div className="flex items-center gap-2 font-semibold"><AlertTriangle className="h-4 w-4" />{a.type} · {a.severity}</div>
                <div className="mt-0.5 text-sm">{a.message}</div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
