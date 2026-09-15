import { useMemo, useState } from 'react'
import {
  Area, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { AlertTriangle, BarChart3, Bot, Brain, Clock, TrendingUp, Wrench } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import { Badge, Button, Card, Empty, Field, Progress, Spinner } from '../components/ui'
import { meta } from '../components/agentMeta'
import { useApi } from '../live'
import { fmtDate, label } from '../utils'

const METRICS = [
  { id: 'admissions', label: 'Admissions / day' }, { id: 'er_visits', label: 'ER visits / day' }, { id: 'opd_visits', label: 'OPD visits / day' },
  { id: 'bed_occupancy', label: 'Bed occupancy' }, { id: 'icu_occupancy', label: 'ICU occupancy' }, { id: 'avg_wait_minutes', label: 'Avg OPD wait (min)' },
]

function LosCard() {
  const card = useApi<any>('/api/analytics/los-model')
  const [f, setF] = useState({ age: 68, ward_type: 'icu', acuity: 'high', comorbidities: 2, emergency: true })
  const [pred, setPred] = useState<any>(null)
  const run = async () => setPred(await api('/api/analytics/los-predict', { body: { ...f, age: Number(f.age), comorbidities: Number(f.comorbidities) } }))
  if (!card.data) return null
  const m = card.data.metrics
  const maxImp = Math.max(...Object.values(card.data.importances as Record<string, number>))
  return (
    <Card className="mt-4" title="Length-of-stay prediction model" subtitle="Gradient Boosting regressor with 10th/90th-percentile quantile models — used by the Resource Optimization Agent to set expected discharge" icon={<Brain className="h-4 w-4" />}>
      <div className="grid gap-6 lg:grid-cols-3">
        <div>
          <div className="flex flex-wrap gap-2 text-xs">
            <Badge tone="teal">MAE {m.mae_days} days</Badge><Badge tone="violet">R² {m.r2}</Badge><Badge tone="sky">80% interval coverage {Math.round(m.interval_coverage * 100)}%</Badge>
          </div>
          <div className="mt-2 text-[11px] text-slate-500">{m.train_rows} training / {m.test_rows} hold-out rows · {card.data.training_data}</div>
        </div>
        <div className="space-y-1.5">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Feature importance</div>
          {Object.entries(card.data.importances).map(([k, v]: any) => (
            <div key={k} className="flex items-center gap-2 text-xs"><span className="w-36 capitalize text-slate-600">{k}</span><div className="h-2 flex-1 rounded-full bg-slate-100"><div className="h-full rounded-full bg-violet-500" style={{ width: `${(v / maxImp) * 100}%` }} /></div><span className="w-10 text-right tabular-nums">{(v * 100).toFixed(0)}%</span></div>
          ))}
        </div>
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">What-if prediction</div>
          <div className="mt-1 grid grid-cols-2 gap-2">
            <Field label="Age"><input className="input py-1" type="number" value={f.age} onChange={(e) => setF({ ...f, age: Number(e.target.value) })} /></Field>
            <Field label="Ward"><select className="input py-1" value={f.ward_type} onChange={(e) => setF({ ...f, ward_type: e.target.value })}>{['general', 'icu', 'hdu', 'cardiac', 'isolation', 'pediatric', 'maternity'].map((w) => <option key={w}>{w}</option>)}</select></Field>
            <Field label="Acuity"><select className="input py-1" value={f.acuity} onChange={(e) => setF({ ...f, acuity: e.target.value })}>{['low', 'moderate', 'high', 'critical'].map((w) => <option key={w}>{w}</option>)}</select></Field>
            <Field label="Comorbidities"><input className="input py-1" type="number" min={0} max={6} value={f.comorbidities} onChange={(e) => setF({ ...f, comorbidities: Number(e.target.value) })} /></Field>
          </div>
          <div className="mt-2 flex items-center gap-3">
            <label className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={f.emergency} onChange={(e) => setF({ ...f, emergency: e.target.checked })} />Emergency admission</label>
            <Button size="sm" onClick={run}>Predict</Button>
          </div>
          {pred && <div className="mt-2 rounded-lg bg-violet-50 p-2 text-sm text-violet-900">Predicted stay <b>{pred.days} days</b> <span className="text-xs">(80% interval {pred.low}–{pred.high} d)</span></div>}
        </div>
      </div>
    </Card>
  )
}

export default function Analytics() {
  const [metric, setMetric] = useState('admissions')
  const [horizon, setHorizon] = useState(14)
  const fc = useApi<any>(`/api/analytics/forecast?metric=${metric}&horizon=${horizon}`)
  const history = useApi<any[]>('/api/analytics/history?days=90')
  const util = useApi<any>('/api/analytics/utilization', ['beds', 'staff', 'resources'])
  const waits = useApi<any[]>('/api/analytics/wait-times', ['appointments'])
  const bottlenecks = useApi<any[]>('/api/analytics/bottlenecks')
  const agents = useApi<any>('/api/analytics/agents')
  const isPct = metric.includes('occupancy')

  const chart = useMemo(() => {
    if (!fc.data) return []
    const hist = fc.data.history.map((h: any) => ({ day: h.day, actual: h.actual, fitted: h.fitted }))
    const last = hist[hist.length - 1]
    const fut = fc.data.forecast.map((f: any) => ({ day: f.day, forecast: f.forecast, lower: f.lower, band: f.upper - f.lower }))
    if (last) fut.unshift({ day: last.day, forecast: last.actual, lower: last.actual, band: 0 })
    return [...hist.slice(0, -1), { ...last, ...(fut[0] || {}) }, ...fut.slice(1)]
  }, [fc.data])
  const fmt = (v: any) => (typeof v === 'number' ? (isPct ? `${(v * 100).toFixed(1)}%` : v.toFixed(1)) : v)

  return (
    <div>
      <PageHeader title="Analytics & demand forecasting" icon={<BarChart3 className="h-5 w-5" />} subtitle="Historical & real-time data → Holt-Winters forecasts, queueing-theory wait analysis, utilisation and bottleneck detection" />

      <Card title="Demand forecast" subtitle="Holt-Winters triple exponential smoothing (weekly seasonality) with 95% prediction interval" icon={<TrendingUp className="h-4 w-4" />}
        actions={<>
          <select className="input w-48 py-1 text-xs" value={metric} onChange={(e) => setMetric(e.target.value)}>{METRICS.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}</select>
          <select className="input w-28 py-1 text-xs" value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>{[7, 14, 30].map((h) => <option key={h} value={h}>{h} days</option>)}</select>
        </>}>
        {!fc.data ? <Spinner /> : (
          <>
            <div className="mb-3 flex flex-wrap gap-2 text-xs">
              <Badge tone="teal">hold-out MAPE {fc.data.mape ?? '—'}%</Badge>
              <Badge tone="slate">α={fc.data.params.alpha} β={fc.data.params.beta} γ={fc.data.params.gamma} · season {fc.data.params.season}d</Badge>
              <Badge tone="violet">next {horizon}d mean: {fmt(fc.data.forecast.reduce((s: number, f: any) => s + f.forecast, 0) / fc.data.forecast.length)}</Badge>
            </div>
            <div className="h-72">
              <ResponsiveContainer>
                <ComposedChart data={chart} margin={{ left: -10, right: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="day" tickFormatter={fmtDate} tick={{ fontSize: 11 }} minTickGap={24} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => (isPct ? `${Math.round(v * 100)}%` : v)} domain={['auto', 'auto']} />
                  <Tooltip labelFormatter={(l) => fmtDate(String(l))} formatter={(v: any, n: any) => (n === 'band' || n === 'lower' ? [null, null] : [fmt(v), n])} />
                  <Legend />
                  <Area dataKey="lower" stackId="ci" stroke="none" fill="transparent" legendType="none" isAnimationActive={false} />
                  <Area dataKey="band" stackId="ci" stroke="none" fill="#99f6e4" fillOpacity={0.5} name="95% interval" isAnimationActive={false} />
                  <Line dataKey="actual" name="Actual" stroke="#334155" dot={false} strokeWidth={1.8} />
                  <Line dataKey="fitted" name="Model fit" stroke="#94a3b8" dot={false} strokeDasharray="4 4" strokeWidth={1.2} />
                  <Line dataKey="forecast" name="Forecast" stroke="#0d9488" dot={{ r: 2 }} strokeWidth={2.5} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </>
        )}
      </Card>

      <LosCard />

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="Occupancy trend — 90 days" icon={<TrendingUp className="h-4 w-4" />}>
          <div className="h-60">
            <ResponsiveContainer>
              <LineChart data={history.data || []} margin={{ left: -10, right: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="day" tickFormatter={fmtDate} tick={{ fontSize: 11 }} minTickGap={24} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${Math.round(v * 100)}%`} domain={[0.5, 1]} />
                <Tooltip labelFormatter={(l) => fmtDate(String(l))} formatter={(v: any) => `${(v * 100).toFixed(1)}%`} />
                <Legend />
                <Line dataKey="bed_occupancy" name="Bed occupancy" stroke="#0ea5e9" dot={false} strokeWidth={2} />
                <Line dataKey="icu_occupancy" name="ICU occupancy" stroke="#e11d48" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="OPD waiting time by department" subtitle="Observed door-to-doctor vs M/M/c model prediction" icon={<Clock className="h-4 w-4" />}>
          <div className="h-60">
            <ResponsiveContainer>
              <BarChart data={waits.data || []} margin={{ left: -10, right: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="department" tick={{ fontSize: 10 }} interval={0} angle={-20} textAnchor="end" height={50} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="observed_avg_wait" name="Observed (min)" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                <Bar dataKey="wq_minutes" name="M/M/c Wq (min)" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card title="Equipment utilisation" icon={<Wrench className="h-4 w-4" />}>
          {!util.data ? <Spinner /> : (
            <div className="space-y-2.5">
              {util.data.resources.map((r: any) => (
                <div key={r.type}>
                  <div className="mb-1 flex justify-between text-xs"><span className="capitalize text-slate-700">{label(r.type)}</span><span className="text-slate-500">{r.in_use}/{r.total} in use{r.maintenance ? ` · ${r.maintenance} maint.` : ''}</span></div>
                  <Progress value={r.in_use} max={r.total} />
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card title="Staff workload by department" subtitle="On-duty patient load vs capacity">
          {!util.data ? <Spinner /> : (
            <div className="space-y-2.5">
              {util.data.staff.map((s: any) => (
                <div key={s.department}>
                  <div className="mb-1 flex justify-between text-xs"><span className="text-slate-700">{s.department}</span><span className="text-slate-500">{s.load}/{s.capacity} · {s.doctors}D {s.nurses}N</span></div>
                  <Progress value={s.utilization} />
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card title="Bottlenecks" icon={<AlertTriangle className="h-4 w-4" />}>
          {!bottlenecks.data?.length ? <Empty title="No bottlenecks" /> : bottlenecks.data.map((b, i) => (
            <div key={i} className="mb-2 rounded-lg border border-slate-100 p-2.5">
              <div className="flex items-center gap-2"><Badge tone={b.severity === 'high' ? 'red' : b.severity === 'medium' ? 'amber' : 'slate'}>{b.severity}</Badge><span className="text-sm font-medium">{b.area}</span></div>
              <div className="mt-1 text-xs text-slate-600">{b.issue}</div>
              <div className="text-xs text-teal-700">→ {b.suggestion}</div>
            </div>
          ))}
        </Card>
      </div>

      <Card className="mt-4" title="AI agent performance" subtitle={agents.data ? `${agents.data.requests} orchestrated requests · avg ${agents.data.avg_duration_ms} ms end-to-end` : ''} icon={<Bot className="h-4 w-4" />}>
        {!agents.data ? <Spinner /> : (
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="h-56">
              <ResponsiveContainer>
                <BarChart data={Object.entries(agents.data.by_intent).map(([k, v]) => ({ intent: label(k), count: v }))} margin={{ left: -20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="intent" tick={{ fontSize: 10 }} interval={0} angle={-20} textAnchor="end" height={50} />
                  <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" name="Requests by intent" fill="#0d9488" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <table className="w-full text-xs">
              <thead className="text-left text-slate-500"><tr><th className="py-1">Agent</th><th>Tasks</th><th>Success</th><th>Failed</th><th>Avg ms</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {agents.data.agents.map((a: any) => {
                  const m = meta(a.key)
                  return <tr key={a.key}><td className="py-1.5"><span className="inline-flex items-center gap-1.5"><m.icon className="h-3.5 w-3.5" style={{ color: m.color }} />{a.name}</span></td><td>{a.tasks}</td><td className="text-emerald-700">{a.success}</td><td className="text-red-600">{a.failed}</td><td>{a.avg_ms}</td></tr>
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
