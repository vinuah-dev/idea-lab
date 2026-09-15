import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { HeartPulse, Search, UserPlus } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import { Badge, Button, Card, Field, Modal, Progress, Spinner, StatusBadge, useToast } from '../components/ui'
import { useApi } from '../live'

const STATUSES = ['', 'registered', 'waiting', 'in_consultation', 'emergency', 'admitted', 'icu', 'discharged']

export default function Patients() {
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [open, setOpen] = useState(false)
  const { data, loading, reload } = useApi<any>(`/api/patients?limit=200&q=${encodeURIComponent(q)}&status=${status}`, ['patients'])
  return (
    <div>
      <PageHeader title="Patients" icon={<HeartPulse className="h-5 w-5" />} subtitle="Unified patient records linked to admissions, appointments, diagnostics, prescriptions and care pathways"
        actions={<Button icon={<UserPlus className="h-4 w-4" />} onClick={() => setOpen(true)}>Register patient</Button>} />
      <Card bodyClass="p-0">
        <div className="flex flex-wrap gap-2 border-b border-slate-100 p-3">
          <div className="relative min-w-60 flex-1">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <input className="input pl-9" placeholder="Search by name, MRN or phone" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <select className="input w-48" value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s ? s.replace('_', ' ') : 'All statuses'}</option>)}
          </select>
          <div className="self-center text-xs text-slate-500">{data?.total ?? 0} patients</div>
        </div>
        {loading && !data ? <Spinner /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs text-slate-500">
                <tr><th className="px-4 py-2">MRN</th><th className="px-4 py-2">Name</th><th className="px-4 py-2">Age / Sex</th><th className="px-4 py-2">Status</th>
                  <th className="px-4 py-2">Risk</th><th className="px-4 py-2">Primary doctor</th><th className="px-4 py-2">Allergies / conditions</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data?.items.map((p: any) => (
                  <tr key={p.id} onClick={() => nav(`/patients/${p.id}`)} className="cursor-pointer hover:bg-slate-50">
                    <td className="px-4 py-2 font-mono text-xs text-slate-500">{p.mrn}</td>
                    <td className="px-4 py-2 font-medium text-slate-800">{p.name}</td>
                    <td className="px-4 py-2 text-slate-600">{p.age} / {p.gender?.[0]}</td>
                    <td className="px-4 py-2"><StatusBadge status={p.status} /></td>
                    <td className="w-28 px-4 py-2"><Progress value={p.risk_score} /></td>
                    <td className="px-4 py-2 text-slate-600">{p.primary_doctor || '—'}</td>
                    <td className="px-4 py-2"><div className="flex flex-wrap gap-1">
                      {p.allergies.map((a: string) => <Badge key={a} tone="red">⚠ {a}</Badge>)}
                      {p.conditions.slice(0, 2).map((c: string) => <Badge key={c} tone="slate">{c}</Badge>)}
                    </div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <RegisterModal open={open} onClose={() => setOpen(false)} onCreated={(p) => { reload(); nav(`/patients/${p.id}`) }} />
    </div>
  )
}

function RegisterModal({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (p: any) => void }) {
  const toast = useToast()
  const [f, setF] = useState({ name: '', age: 30, gender: 'Male', phone: '', blood_group: 'O+', allergies: '', conditions: '' })
  const [busy, setBusy] = useState(false)
  const save = async () => {
    setBusy(true)
    try {
      const p = await api('/api/patients', { body: { ...f, age: Number(f.age), allergies: f.allergies.split(',').map((s) => s.trim()).filter(Boolean), conditions: f.conditions.split(',').map((s) => s.trim()).filter(Boolean) } })
      toast({ title: 'Patient registered', message: `${p.name} — ${p.mrn}`, level: 'success' })
      onClose()
      onCreated(p)
    } catch (e: any) { toast({ title: 'Registration failed', message: e.message, level: 'critical' }) } finally { setBusy(false) }
  }
  return (
    <Modal open={open} onClose={onClose} title="Register new patient" footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={save} loading={busy} disabled={f.name.length < 2}>Register</Button></>}>
      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2"><Field label="Full name"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field></div>
        <Field label="Age"><input className="input" type="number" value={f.age} onChange={(e) => setF({ ...f, age: Number(e.target.value) })} /></Field>
        <Field label="Gender"><select className="input" value={f.gender} onChange={(e) => setF({ ...f, gender: e.target.value })}><option>Male</option><option>Female</option><option>Other</option></select></Field>
        <Field label="Phone"><input className="input" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
        <Field label="Blood group"><select className="input" value={f.blood_group} onChange={(e) => setF({ ...f, blood_group: e.target.value })}>{['O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-'].map((b) => <option key={b}>{b}</option>)}</select></Field>
        <div className="col-span-2"><Field label="Allergies (comma separated, e.g. penicillin, sulfa)"><input className="input" value={f.allergies} onChange={(e) => setF({ ...f, allergies: e.target.value })} /></Field></div>
        <div className="col-span-2"><Field label="Known conditions (comma separated)"><input className="input" value={f.conditions} onChange={(e) => setF({ ...f, conditions: e.target.value })} /></Field></div>
      </div>
    </Modal>
  )
}
