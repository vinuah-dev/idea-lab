import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, ShieldAlert, X } from 'lucide-react'
import { api } from '../api'
import { useAuth } from '../auth'
import { ago, cls, label } from '../utils'
import { meta } from './agentMeta'
import { Badge, Button, StatusBadge, useToast } from './ui'

const RISK_STYLE: Record<string, string> = {
  low: 'border-l-emerald-400', medium: 'border-l-amber-400', high: 'border-l-orange-500', critical: 'border-l-red-600',
}

const HIDDEN_KEYS = new Set(['orders', 'assignments', 'alerts', 'reason', 'follow_up'])

export default function ApprovalCard({ approval, onDone, compact, alternatives }: {
  approval: any; onDone?: () => void; compact?: boolean; alternatives?: Record<string, { value: number; label: string }[]>
}) {
  const { user } = useAuth()
  const toast = useToast()
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState<'approve' | 'reject' | null>(null)
  const [overrides, setOverrides] = useState<Record<string, number>>({})
  const alts = alternatives || approval.alternatives || {}
  const canDecide = approval.status === 'pending' && (approval.can_decide ?? (user?.role === 'admin' || approval.required_roles?.includes(user?.role)))
  const agentKey = Object.entries({ bed: 'Bed', staff: 'Staff', diagnostic: 'Diagnostic', pharmacy: 'Pharmacy', care: 'Care', optimization: 'Optimization', appointment: 'Appointment', emergency: 'Emergency' })
    .find(([, v]) => approval.agent?.includes(v))?.[0]
  const m = meta(agentKey)

  const decide = async (approve: boolean) => {
    setBusy(approve ? 'approve' : 'reject')
    try {
      const res = await api(`/api/approvals/${approval.id}/decide`, { body: { approve, note: note || null, overrides } })
      toast({ title: approve ? (res.status === 'executed' ? 'Approved & executed' : `Approval ${res.status}`) : 'Rejected',
        message: res.execution_result?.error || approval.title, level: res.status === 'failed' ? 'critical' : approve ? 'success' : 'warning' })
      onDone?.()
    } catch (e: any) {
      toast({ title: 'Could not record decision', message: e.message, level: 'critical' })
    } finally { setBusy(null) }
  }

  const payload = approval.payload || {}
  const facts = Object.entries(payload).filter(([k, v]) => !HIDDEN_KEYS.has(k) && v !== null && typeof v !== 'object').slice(0, 6)

  return (
    <div className={cls('fade-in rounded-xl border border-l-4 border-slate-200 bg-white p-4 shadow-sm', RISK_STYLE[approval.risk_level] || '')}>
      <div className="flex flex-wrap items-start gap-3">
        <div className="rounded-lg p-2" style={{ background: `${m.color}15`, color: m.color }}><m.icon className="h-4 w-4" /></div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold text-slate-800">{approval.title}</span>
            <Badge tone={approval.risk_level === 'critical' ? 'red' : approval.risk_level === 'high' ? 'orange' : approval.risk_level === 'medium' ? 'amber' : 'green'}>
              <ShieldAlert className="h-3 w-3" />{approval.risk_level} risk
            </Badge>
            <StatusBadge status={approval.status} />
          </div>
          <div className="mt-0.5 text-xs text-slate-500">
            Proposed by <span className="font-medium text-slate-700">{approval.agent}</span> · {ago(approval.created_at)} · approvers: {approval.required_roles?.join(', ')}
            {approval.request_id && <> · <Link className="text-teal-700 hover:underline" to={`/agents?request=${approval.request_id}`}>request #{approval.request_id}</Link></>}
          </div>
          {approval.description && <p className="mt-2 text-sm text-slate-600">{approval.description}</p>}
        </div>
      </div>

      {!compact && approval.rationale?.length > 0 && (
        <div className="mt-3 rounded-lg bg-slate-50 p-3">
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Why the agents recommend this</div>
          <ul className="space-y-1 text-xs text-slate-700">
            {approval.rationale.map((r: string, i: number) => <li key={i} className="flex gap-2"><span className="text-teal-600">•</span><span>{r}</span></li>)}
          </ul>
        </div>
      )}

      {!compact && facts.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {facts.map(([k, v]) => <span key={k} className="rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[11px] text-slate-600">{label(k)}: {String(v)}</span>)}
          {payload.orders && <span className="rounded-md bg-amber-50 px-2 py-0.5 text-[11px] text-amber-800">{payload.orders.length} item(s): {payload.orders.map((o: any) => o.code || o.name).join(', ')}</span>}
          {payload.assignments && <span className="rounded-md bg-sky-50 px-2 py-0.5 text-[11px] text-sky-800">{payload.assignments.length} assignment(s)</span>}
        </div>
      )}

      {canDecide && (
        <div className="mt-3 space-y-2 border-t border-slate-100 pt-3">
          {Object.entries(alts).filter(([, opts]) => (opts as any[]).length > 1).map(([key, opts]) => (
            <label key={key} className="flex items-center gap-2 text-xs">
              <span className="w-28 shrink-0 font-medium text-slate-600">Modify {label(key.replace('_id', ''))}</span>
              <select className="input py-1 text-xs" value={overrides[key] ?? payload[key] ?? ''} onChange={(e) => setOverrides((o) => ({ ...o, [key]: Number(e.target.value) }))}>
                {(opts as any[]).map((o) => <option key={o.value} value={o.value}>{o.label}{o.value === payload[key] ? ' (AI choice)' : ''}</option>)}
              </select>
            </label>
          ))}
          <div className="flex flex-wrap items-center gap-2">
            <input className="input flex-1 py-1.5 text-xs" placeholder="Decision note (optional, stored in audit log)" value={note} onChange={(e) => setNote(e.target.value)} />
            <Button size="sm" variant="success" icon={<Check className="h-3.5 w-3.5" />} loading={busy === 'approve'} onClick={() => decide(true)}>Approve{Object.keys(overrides).length ? ' with changes' : ''}</Button>
            <Button size="sm" variant="secondary" icon={<X className="h-3.5 w-3.5" />} loading={busy === 'reject'} onClick={() => decide(false)}>Reject</Button>
          </div>
        </div>
      )}
      {approval.status === 'pending' && !canDecide && (
        <div className="mt-3 text-xs text-slate-500">Waiting for {approval.required_roles?.join(' / ')} — your role ({user?.role}) cannot decide this action.</div>
      )}
      {approval.status !== 'pending' && (
        <div className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
          {approval.status === 'rejected' ? 'Rejected' : 'Decided'} by <b>{approval.decided_by}</b> {ago(approval.decided_at)}
          {approval.decision_note && <> — “{approval.decision_note}”</>}
          {approval.execution_result && Object.keys(approval.execution_result).length > 0 && (
            <div className="mt-1 font-mono text-[11px] text-slate-500">{JSON.stringify(approval.execution_result)}</div>
          )}
        </div>
      )}
    </div>
  )
}
