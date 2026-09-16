import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Brain, Eye, Gauge, Scale, ShieldCheck, Timer, UserCheck, Zap } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { Badge, Card, Empty, Spinner, Stat } from '../components/ui'
import { useApi } from '../live'
import { label, pct } from '../utils'

/** Responsible-AI dashboard: how humans oversee the agents, how good the models are, and who touched patient data. */
export default function Governance() {
  const { data, loading } = useApi<any>('/api/governance', ['settings'], 60000)
  if (loading && !data) return <Spinner label="Evaluating models and oversight metrics…" />
  if (!data) return <Empty title="Governance data unavailable" />
  const h = data.hitl
  const actions = Object.entries(h.by_action).map(([k, v]: any) => ({ name: label(k), approved: v.approved - v.modified, modified: v.modified, rejected: v.rejected, pending: v.pending, failed: v.failed }))
  const m = data.models
  return (
    <div>
      <PageHeader title="AI governance & model cards" icon={<ShieldCheck className="h-5 w-5" />}
        subtitle="Human-in-the-loop oversight, model quality with honest validation, safety events and data-access transparency" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Approval rate" value={h.approval_rate !== null ? pct(h.approval_rate) : '—'} sub={`${h.totals.approved} approved of ${h.totals.approved + h.totals.rejected + h.totals.failed}`} icon={<UserCheck className="h-5 w-5" />} tone="emerald" />
        <Stat label="Approved with changes" value={h.modification_rate !== null ? pct(h.modification_rate) : '—'} sub="humans edited the AI plan" icon={<Scale className="h-5 w-5" />} tone="violet" />
        <Stat label="Rejection rate" value={h.rejection_rate !== null ? pct(h.rejection_rate) : '—'} sub={`${h.totals.rejected} rejected`} icon={<ShieldCheck className="h-5 w-5" />} tone="red" />
        <Stat label="Median decision time" value={h.median_decision_minutes !== null ? `${h.median_decision_minutes} min` : '—'} sub={`${h.totals.pending} pending now`} icon={<Timer className="h-5 w-5" />} tone="amber" />
        <Stat label="Autonomy ratio" value={h.autonomy_ratio !== null ? pct(h.autonomy_ratio) : '—'} sub={`${h.auto_executed} auto · ${h.held_for_approval} held`} icon={<Zap className="h-5 w-5" />} tone="teal" />
        <Stat label="Record views (24 h)" value={data.privacy.record_views_24h} sub="access-logged" icon={<Eye className="h-5 w-5" />} tone="slate" />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card title="Human decisions by action type" subtitle="What the agents proposed and what people decided" className="xl:col-span-2">
          {!actions.length ? <Empty title="No approvals yet" /> : (
            <div className="h-64">
              <ResponsiveContainer>
                <BarChart data={actions} margin={{ left: -15, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} angle={-15} textAnchor="end" height={50} />
                  <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="approved" stackId="a" fill="#10b981" name="Approved" />
                  <Bar dataKey="modified" stackId="a" fill="#8b5cf6" name="Approved with changes" />
                  <Bar dataKey="rejected" stackId="a" fill="#ef4444" name="Rejected" />
                  <Bar dataKey="failed" stackId="a" fill="#f97316" name="Failed on execution" />
                  <Bar dataKey="pending" stackId="a" fill="#cbd5e1" name="Pending" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
        <Card title="Policy in force">
          <div className="space-y-2 text-xs">
            <div><span className="text-slate-500">Autonomy mode:</span> <Badge tone="sky">{data.policy.autonomy_mode}</Badge></div>
            <div className="text-slate-500">{data.policy.modes[data.policy.autonomy_mode]}</div>
            <div><span className="text-slate-500">Always human-reviewed:</span> <span className="flex flex-wrap gap-1 pt-1">{data.policy.always_review.map((a: string) => <Badge key={a} tone="amber">{label(a)}</Badge>)}</span></div>
            <div><span className="text-slate-500">Time-critical (never held):</span> {data.policy.time_critical.map((a: string) => <Badge key={a} tone="red">{label(a)}</Badge>)}</div>
            <div className="border-t border-slate-100 pt-2 text-slate-500">Approver roles</div>
            {Object.entries(data.policy.approver_roles).map(([k, v]: any) => <div key={k} className="flex justify-between"><span className="capitalize text-slate-600">{k}</span><span className="text-slate-800">{v.join(', ')}</span></div>)}
            {Object.keys(h.modified_fields).length > 0 && <div className="border-t border-slate-100 pt-2"><span className="text-slate-500">Fields humans changed most:</span> {Object.entries(h.modified_fields).map(([k, v]: any) => <Badge key={k} tone="violet">{label(k)} ×{v}</Badge>)}</div>}
          </div>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card title="Intent classifier" subtitle={m.intent_classifier.model} icon={<Brain className="h-4 w-4" />}>
          <Metric k="Cross-validated accuracy" v={`${pct(m.intent_classifier.cv_accuracy, 1)} ± ${pct(m.intent_classifier.cv_std, 1)}`} />
          <Metric k="Held-out accuracy (incl. Hinglish)" v={`${pct(m.intent_classifier.held_out_accuracy, 1)} (n=${m.intent_classifier.held_out_size})`} />
          <Metric k="Intents / training sentences" v={`${m.intent_classifier.intents} / ${m.intent_classifier.training_sentences}`} />
          <p className="mt-2 text-[11px] text-slate-400">{m.intent_classifier.method}</p>
          {m.intent_classifier.misses.length > 0 && (
            <div className="mt-2 space-y-1">{m.intent_classifier.misses.map((x: any) => <div key={x.text} className="rounded bg-amber-50 px-2 py-1 text-[11px] text-amber-900">“{x.text}” → {x.predicted} (expected {x.expected})</div>)}</div>
          )}
        </Card>
        <Card title="Length-of-stay model" subtitle="Gradient boosting + quantile interval" icon={<Gauge className="h-4 w-4" />}>
          <Metric k="MAE (days)" v={`${m.length_of_stay.metrics.mae_days} vs ${m.length_of_stay.metrics.baseline_mae_days} naïve`} />
          <Metric k="R²" v={m.length_of_stay.metrics.r2} />
          <Metric k="80% interval coverage" v={pct(m.length_of_stay.metrics.interval_coverage, 1)} />
          <div className="mt-2 space-y-1">
            {Object.entries(m.length_of_stay.importances).map(([k, v]: any) => (
              <div key={k} className="flex items-center gap-2 text-[11px]"><span className="w-32 truncate text-slate-500">{k}</span><div className="h-1.5 flex-1 rounded-full bg-slate-100"><div className="h-full rounded-full bg-teal-500" style={{ width: `${v * 100}%` }} /></div><span className="w-8 text-right tabular-nums">{Math.round(v * 100)}%</span></div>
            ))}
          </div>
        </Card>
        <Card title="30-day readmission model" subtitle={m.readmission.model} icon={<Scale className="h-4 w-4" />}>
          <Metric k="AUC (test)" v={m.readmission.metrics.auc} />
          <Metric k="LACE index alone (AUC)" v={m.readmission.metrics.lace_only_auc} />
          <Metric k="Brier score" v={m.readmission.metrics.brier} />
          <div className="mt-2 text-[11px] text-slate-500">Fairness check — AUC by gender:</div>
          <div className="mt-1 flex gap-2">{Object.entries(m.readmission.fairness_auc_by_gender).map(([k, v]: any) => <Badge key={k} tone="slate">{k}: {v}</Badge>)}</div>
          <p className="mt-2 text-[11px] text-slate-400">{m.readmission.training_data}</p>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card title="Medication safety">
          <Metric k="Prescriptions with safety alerts" v={data.safety.prescriptions_with_alerts} />
          <Metric k="Contraindicated (flagged)" v={data.safety.contraindicated_flagged} />
          <Metric k="Contraindicated dispensed" v={<Badge tone={data.safety.contraindicated_dispensed ? 'red' : 'green'}>{data.safety.contraindicated_dispensed}</Badge>} />
          <p className="mt-2 text-[11px] text-slate-400">Contraindicated prescriptions cannot be verified by pharmacy; they go back to the prescriber.</p>
        </Card>
        <Card title="Requests by channel">
          {Object.entries(data.requests.by_source).map(([k, v]: any) => <Metric key={k} k={k} v={v} />)}
          <Metric k="Mean NLP confidence" v={data.requests.mean_confidence ?? '—'} />
          <Metric k="Low-confidence requests (< 0.5)" v={data.requests.low_confidence} />
        </Card>
        <Card title="Who accessed patient records (24 h)" subtitle="Patients see their own access log in the portal">
          {!data.privacy.top_viewers.length ? <Empty title="No record views logged" /> : data.privacy.top_viewers.map((v: any) => <Metric key={v.actor} k={v.actor} v={`${v.views} view${v.views > 1 ? 's' : ''}`} />)}
        </Card>
      </div>

      <Card className="mt-4" title="Agent performance" bodyClass="p-0">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs text-slate-500"><tr>{['Agent', 'Tasks', 'Succeeded', 'Failed', 'Avg time'].map((x) => <th key={x} className="px-4 py-2">{x}</th>)}</tr></thead>
          <tbody className="divide-y divide-slate-100">{data.agents.map((a: any) => <tr key={a.key}><td className="px-4 py-2">{a.name}</td><td className="px-4 py-2 tabular-nums">{a.tasks}</td><td className="px-4 py-2 tabular-nums text-emerald-700">{a.success}</td><td className="px-4 py-2 tabular-nums text-red-600">{a.failed}</td><td className="px-4 py-2 tabular-nums">{a.avg_ms} ms</td></tr>)}</tbody>
        </table>
      </Card>
    </div>
  )
}

function Metric({ k, v }: { k: string; v: any }) {
  return <div className="flex items-center justify-between border-b border-slate-50 py-1 text-sm"><span className="text-slate-500">{k}</span><span className="font-medium tabular-nums text-slate-800">{v}</span></div>
}
