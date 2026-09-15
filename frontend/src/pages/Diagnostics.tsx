import { useState } from 'react'
import { Link } from 'react-router-dom'
import { FlaskConical, Plus } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import { Badge, Button, Field, Modal, Spinner, StatusBadge, useToast } from '../components/ui'
import { useAuth } from '../auth'
import { useApi } from '../live'
import { ago, cls, fmtTime } from '../utils'

const COLUMNS = [
  { id: 'ordered', label: 'Ordered' }, { id: 'scheduled', label: 'Scheduled' }, { id: 'in_progress', label: 'In progress' }, { id: 'completed', label: 'Completed' },
]
const NEXT: Record<string, string> = { ordered: 'scheduled', scheduled: 'in_progress' }

export default function Diagnostics() {
  const { user } = useAuth()
  const toast = useToast()
  const [cat, setCat] = useState('')
  const [resultFor, setResultFor] = useState<any>(null)
  const [newOpen, setNewOpen] = useState(false)
  const { data, loading } = useApi<any[]>(`/api/diagnostics?limit=300${cat ? `&category=${cat}` : ''}`, ['diagnostics'])
  const canWork = ['admin', 'lab', 'doctor'].includes(user!.role)

  const advance = async (o: any) => {
    try { await api(`/api/diagnostics/${o.id}`, { method: 'PATCH', body: { status: NEXT[o.status] } }) } catch (e: any) { toast({ title: 'Failed', message: e.message, level: 'critical' }) }
  }
  return (
    <div>
      <PageHeader title="Diagnostic coordination" icon={<FlaskConical className="h-5 w-5" />} subtitle="Lab & imaging orders scheduled on the least-loaded modality, with turnaround tracking and result routing"
        actions={<>
          <select className="input w-40" value={cat} onChange={(e) => setCat(e.target.value)}><option value="">All categories</option><option value="lab">Lab</option><option value="imaging">Imaging</option><option value="cardiac">Cardiac</option></select>
          {['admin', 'doctor'].includes(user!.role) && <Button icon={<Plus className="h-4 w-4" />} onClick={() => setNewOpen(true)}>New order</Button>}
        </>} />
      {loading && !data ? <Spinner /> : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {COLUMNS.map((c) => {
            const items = (data || []).filter((o) => o.status === c.id)
            return (
              <div key={c.id} className="rounded-xl bg-slate-100/70 p-2">
                <div className="flex items-center justify-between px-2 py-1.5"><span className="text-sm font-semibold text-slate-700">{c.label}</span><Badge>{items.length}</Badge></div>
                <div className="max-h-[70vh] space-y-2 overflow-y-auto p-1">
                  {items.slice(0, 60).map((o) => (
                    <div key={o.id} className={cls('rounded-lg border bg-white p-2.5 shadow-sm', o.abnormal ? 'border-red-200' : 'border-slate-200')}>
                      <div className="flex items-center gap-1.5">
                        <span className="text-sm font-medium text-slate-800">{o.test_name}</span>
                        <span className="ml-auto"><StatusBadge status={o.priority} /></span>
                      </div>
                      <Link to={`/patients/${o.patient?.id}`} className="text-xs text-teal-700 hover:underline">{o.patient?.name}</Link>
                      <div className="mt-0.5 text-[11px] text-slate-500">{o.resource || 'Lab'}{o.scheduled_at ? ` · ${fmtTime(o.scheduled_at)}` : ''} · ordered {ago(o.created_at)}</div>
                      {o.result && <div className={cls('mt-1.5 rounded bg-slate-50 p-1.5 text-[11px]', o.abnormal ? 'font-medium text-red-700' : 'text-slate-600')}>{o.result}</div>}
                      {canWork && o.status !== 'completed' && (
                        <div className="mt-2 flex gap-1.5">
                          {NEXT[o.status] && <Button size="sm" variant="secondary" onClick={() => advance(o)}>→ {NEXT[o.status].replace('_', ' ')}</Button>}
                          <Button size="sm" onClick={() => setResultFor(o)}>Enter result</Button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}
      <ResultModal order={resultFor} onClose={() => setResultFor(null)} />
      <NewOrderModal open={newOpen} onClose={() => setNewOpen(false)} />
    </div>
  )
}

function ResultModal({ order, onClose }: { order: any; onClose: () => void }) {
  const toast = useToast()
  const [result, setResult] = useState('')
  const [abnormal, setAbnormal] = useState(false)
  const save = async () => {
    try {
      await api(`/api/diagnostics/${order.id}`, { method: 'PATCH', body: { result, abnormal, status: 'completed' } })
      toast({ title: 'Result reported', message: 'Ordering doctors have been notified.', level: 'success' })
      setResult(''); setAbnormal(false); onClose()
    } catch (e: any) { toast({ title: 'Failed', message: e.message, level: 'critical' }) }
  }
  return (
    <Modal open={!!order} onClose={onClose} title={order ? `Result — ${order.test_name}` : ''} footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={save} disabled={!result}>Report result</Button></>}>
      {order && <div className="space-y-3">
        <div className="text-sm text-slate-600">{order.patient?.name} · {order.priority}</div>
        <Field label="Findings"><textarea className="input min-h-24" value={result} onChange={(e) => setResult(e.target.value)} /></Field>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={abnormal} onChange={(e) => setAbnormal(e.target.checked)} />Flag as abnormal (alerts doctors)</label>
      </div>}
    </Modal>
  )
}

function NewOrderModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast()
  const catalog = useApi<any[]>(open ? '/api/diagnostics/catalog' : null)
  const patients = useApi<any>(open ? '/api/patients?limit=300' : null)
  const [f, setF] = useState({ patient_id: '', test_code: 'CBC', priority: 'routine' })
  const save = async () => {
    try {
      const o = await api('/api/diagnostics', { body: { ...f, patient_id: Number(f.patient_id) } })
      toast({ title: 'Order placed', message: `${o.test_name} ${o.resource ? `on ${o.resource} at ${fmtTime(o.scheduled_at)}` : ''}`, level: 'success' })
      onClose()
    } catch (e: any) { toast({ title: 'Failed', message: e.message, level: 'critical' }) }
  }
  return (
    <Modal open={open} onClose={onClose} title="New diagnostic order" footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={save} disabled={!f.patient_id}>Order</Button></>}>
      <div className="space-y-3">
        <Field label="Patient"><select className="input" value={f.patient_id} onChange={(e) => setF({ ...f, patient_id: e.target.value })}><option value="">Select…</option>{(patients.data?.items || []).map((p: any) => <option key={p.id} value={p.id}>{p.name} · {p.mrn}</option>)}</select></Field>
        <Field label="Test"><select className="input" value={f.test_code} onChange={(e) => setF({ ...f, test_code: e.target.value })}>{(catalog.data || []).map((t) => <option key={t.code} value={t.code}>{t.name} ({t.category}, ~{t.tat} min)</option>)}</select></Field>
        <Field label="Priority"><select className="input" value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}><option value="routine">Routine</option><option value="urgent">Urgent</option><option value="stat">STAT</option></select></Field>
      </div>
    </Modal>
  )
}
