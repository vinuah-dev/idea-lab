import { useState } from 'react'
import { Link } from 'react-router-dom'
import { BedDouble, Wrench } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import { Badge, Button, Card, Modal, Progress, Spinner, StatusBadge, useToast } from '../components/ui'
import { useAuth } from '../auth'
import { useApi } from '../live'
import { ago, cls, label } from '../utils'

const BED_STYLE: Record<string, string> = {
  available: 'bg-emerald-50 border-emerald-300 text-emerald-800', occupied: 'bg-rose-50 border-rose-300 text-rose-800',
  reserved: 'bg-violet-50 border-violet-300 text-violet-800', cleaning: 'bg-amber-50 border-amber-300 text-amber-800',
  maintenance: 'bg-slate-100 border-slate-300 text-slate-500',
}
const NEXT: Record<string, string[]> = { available: ['maintenance', 'cleaning'], reserved: ['available'], cleaning: ['available', 'maintenance'], maintenance: ['available', 'cleaning'], occupied: [] }
const FEATURE_ICON: Record<string, string> = { ventilator: 'V', cardiac_monitor: 'C', monitor: 'M', oxygen: 'O', isolation: 'I' }

export default function Beds() {
  const { user } = useAuth()
  const toast = useToast()
  const [type, setType] = useState('')
  const [sel, setSel] = useState<any>(null)
  const wards = useApi<any[]>('/api/wards', ['beds'], 20000)
  const res = useApi<any[]>('/api/resources', ['resources', 'beds'])
  const canEdit = ['admin', 'nurse', 'doctor'].includes(user!.role)
  const all = (wards.data || []).flatMap((w) => w.beds)
  const count = (s: string) => all.filter((b) => b.status === s).length

  const setStatus = async (bed: any, status: string) => {
    try {
      await api(`/api/beds/${bed.id}`, { method: 'PATCH', body: { status } })
      toast({ title: `${bed.code} → ${label(status)}`, level: 'success' })
      setSel(null)
      wards.reload()
    } catch (e: any) { toast({ title: 'Update failed', message: e.message, level: 'critical' }) }
  }
  const setResStatus = async (r: any, status: string) => {
    try { await api(`/api/resources/${r.id}`, { method: 'PATCH', body: { status } }); res.reload() } catch (e: any) { toast({ title: 'Update failed', message: e.message, level: 'critical' }) }
  }
  const types = [...new Set((wards.data || []).map((w) => w.ward_type))]
  const groupedRes: Record<string, any[]> = {}
  for (const r of res.data || []) (groupedRes[r.resource_type] ||= []).push(r)

  return (
    <div>
      <PageHeader title="Beds & equipment" icon={<BedDouble className="h-5 w-5" />} subtitle="Real-time tracking of general beds, ICU/HDU, emergency bays, operating rooms and critical equipment"
        actions={<select className="input w-44" value={type} onChange={(e) => setType(e.target.value)}><option value="">All ward types</option>{types.map((t) => <option key={t} value={t}>{t.toUpperCase()}</option>)}</select>} />
      <div className="mb-4 flex flex-wrap gap-2">
        {['available', 'occupied', 'reserved', 'cleaning', 'maintenance'].map((s) => (
          <div key={s} className={cls('flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm', BED_STYLE[s])}><span className="font-semibold tabular-nums">{count(s)}</span>{s}</div>
        ))}
        <div className="ml-auto flex items-center gap-3 text-[11px] text-slate-500">{Object.entries(FEATURE_ICON).map(([k, v]) => <span key={k}><b>{v}</b> {label(k)}</span>)}</div>
      </div>
      {wards.loading && !wards.data ? <Spinner /> : (
        <div className="grid gap-4 xl:grid-cols-2">
          {(wards.data || []).filter((w) => !type || w.ward_type === type).map((w) => (
            <Card key={w.id} title={w.name} subtitle={`${w.department || ''} · floor ${w.floor} · ${w.ward_type.toUpperCase()}`}
              actions={<div className="w-40"><div className="mb-1 text-right text-xs text-slate-500">{w.occupied}/{w.total} occupied</div><Progress value={w.occupancy} /></div>}>
              <div className="grid grid-cols-4 gap-2 sm:grid-cols-5 md:grid-cols-6">
                {w.beds.map((b: any) => (
                  <button key={b.id} onClick={() => setSel(b)} title={b.patient ? `${b.patient.name} (${b.patient.mrn})` : b.status}
                    className={cls('rounded-lg border px-1.5 py-1.5 text-left transition hover:shadow', BED_STYLE[b.status])}>
                    <div className="font-mono text-[11px] font-semibold">{b.code}</div>
                    <div className="truncate text-[10px] opacity-80">{b.patient ? b.patient.name.split(' ')[0] : label(b.status)}</div>
                    <div className="mt-0.5 flex gap-0.5">{b.features.map((f: string) => <span key={f} className="rounded bg-white/70 px-0.5 text-[8px] font-bold">{FEATURE_ICON[f]}</span>)}</div>
                  </button>
                ))}
              </div>
            </Card>
          ))}
        </div>
      )}

      <Card className="mt-4" title="Operating rooms & critical equipment" subtitle="Live status + predictive maintenance (● green/amber/red = low/medium/high service risk from age since last service and usage hours)" icon={<Wrench className="h-4 w-4" />}>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Object.entries(groupedRes).map(([t, items]) => (
            <div key={t} className="rounded-lg border border-slate-100 p-3">
              <div className="mb-2 flex items-center justify-between"><span className="text-sm font-semibold capitalize text-slate-700">{label(t)}</span>
                <span className="text-xs text-slate-500">{items.filter((i) => i.status === 'available').length}/{items.length} free</span></div>
              <div className="space-y-1.5">
                {items.map((r) => (
                  <div key={r.id} className="flex items-center gap-2 text-xs">
                    <span className={cls('h-2 w-2 shrink-0 rounded-full', r.maintenance_band === 'high' ? 'bg-red-500' : r.maintenance_band === 'medium' ? 'bg-amber-400' : 'bg-emerald-400')}
                      title={`Predicted maintenance risk ${Math.round(r.maintenance_risk * 100)}% — service due ${r.maintenance_due}`} />
                    <span className="flex-1 truncate text-slate-700" title={r.location}>{r.name}</span>
                    <span className={cls('text-[10px]', r.maintenance_due_in_days < 0 ? 'font-semibold text-red-600' : 'text-slate-400')}>
                      {r.maintenance_due_in_days < 0 ? `service overdue ${-r.maintenance_due_in_days}d` : `service in ${r.maintenance_due_in_days}d`}
                    </span>
                    {canEdit ? (
                      <select className="rounded border border-slate-200 bg-white px-1 py-0.5 text-[11px]" value={r.status} onChange={(e) => setResStatus(r, e.target.value)}>
                        {['available', 'in_use', 'maintenance'].map((s) => <option key={s} value={s}>{label(s)}</option>)}
                      </select>
                    ) : <StatusBadge status={r.status} />}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Modal open={!!sel} onClose={() => setSel(null)} title={sel ? `Bed ${sel.code}` : ''}>
        {sel && (
          <div className="space-y-3 text-sm">
            <div className="flex items-center gap-2"><StatusBadge status={sel.status} /><span className="text-slate-500">{sel.ward} · {sel.bed_type.toUpperCase()}</span></div>
            <div className="flex flex-wrap gap-1">{sel.features.map((f: string) => <Badge key={f} tone="sky">{label(f)}</Badge>)}</div>
            {sel.patient && <div className="rounded-lg bg-slate-50 p-3">Patient: <Link className="font-medium text-teal-700 hover:underline" to={`/patients/${sel.patient.id}`}>{sel.patient.name}</Link> ({sel.patient.mrn}, {sel.patient.age}{sel.patient.gender?.[0]})</div>}
            <div className="text-xs text-slate-500">Last updated {ago(sel.updated_at)}</div>
            {canEdit && NEXT[sel.status]?.length > 0 && (
              <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-3">
                {NEXT[sel.status].map((s) => <Button key={s} size="sm" variant={s === 'available' ? 'success' : 'secondary'} onClick={() => setStatus(sel, s)}>Mark {label(s)}</Button>)}
              </div>
            )}
            {sel.status === 'occupied' && <div className="text-xs text-slate-500">Occupied beds are released through the discharge workflow (AI Agent Console → “Discharge &lt;patient&gt;”).</div>}
          </div>
        )}
      </Modal>
    </div>
  )
}
