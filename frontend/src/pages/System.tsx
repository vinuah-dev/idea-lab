import { useState } from 'react'
import { Activity, BookOpen, Database, Layers, Play, RotateCcw, Settings, ShieldCheck, Siren, Square, StepForward, Zap } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import { meta } from '../components/agentMeta'
import { Badge, Button, Card, Modal, Spinner, useToast } from '../components/ui'
import { useAuth } from '../auth'
import { useApi, useLive } from '../live'
import { ago, cls } from '../utils'

const LAYERS = [
  { name: 'Client', color: 'bg-sky-50 border-sky-200 text-sky-900', items: ['Patient portal (PWA)', 'Doctor dashboard', 'Nurse dashboard', 'Administrator console'] },
  { name: 'Application layer', color: 'bg-indigo-50 border-indigo-200 text-indigo-900', items: ['FastAPI REST gateway', 'JWT authentication', 'Role-based access control', 'WebSocket event bus'] },
  { name: 'AI orchestration layer', color: 'bg-teal-50 border-teal-200 text-teal-900', items: ['Multi-agent orchestrator', 'NLP understanding (Claude / TF-IDF+LR)', 'Planner & task manager (DAG)', 'Shared blackboard context', 'Conflict resolution', 'Human-in-the-loop gate'] },
  { name: 'Specialised AI agents', color: 'bg-emerald-50 border-emerald-200 text-emerald-900', items: ['Bed management', 'Appointment & queue', 'Staff scheduling', 'Diagnostics', 'Pharmacy', 'Patient care', 'Emergency support', 'Resource optimisation', 'Notification'] },
  { name: 'Hospital services & algorithms', color: 'bg-amber-50 border-amber-200 text-amber-900', items: ['OR-Tools CP-SAT optimiser', 'NEWS2 triage', 'M/M/c queueing model', 'Holt-Winters forecasting', 'Drug-safety knowledge base', 'Audit & notifications'] },
  { name: 'Integration layer', color: 'bg-orange-50 border-orange-200 text-orange-900', items: ['HIS / EHR REST APIs', 'Laboratory system', 'Pharmacy system', 'IoT / MQTT (future)', 'SMS / e-mail gateways (simulated)'] },
  { name: 'Data layer', color: 'bg-slate-100 border-slate-300 text-slate-800', items: ['PostgreSQL / SQLite (SQLAlchemy ORM)', 'Patient records', 'Resource data', 'Workflow & agent traces', 'Audit log', 'Historical analytics'] },
]

const STACK = [
  ['Frontend', 'React 19 + TypeScript + Vite, Tailwind CSS v4, Recharts, PWA'], ['Backend', 'FastAPI (Python 3.11), Pydantic v2, Uvicorn'],
  ['Database', 'SQLAlchemy 2 ORM → SQLite (dev) / PostgreSQL 16 (Docker)'], ['AI / NLP', 'Claude (claude-opus-5) structured outputs + local TF-IDF / Logistic Regression'],
  ['Optimisation', 'Google OR-Tools CP-SAT (bed matching, rostering), SciPy Hungarian fallback'], ['Forecasting', 'Holt-Winters additive triple exponential smoothing (NumPy)'],
  ['Clinical scoring', 'NEWS2 (RCP 2017) + Manchester-style 5-level triage'], ['Auth', 'JWT (HS256) + PBKDF2-SHA256 password hashing + RBAC'],
  ['Real-time', 'WebSockets (FastAPI) event bus'], ['Deployment', 'Docker + docker-compose (Postgres, API, Nginx)'],
]

export default function SystemPage() {
  const { user } = useAuth()
  const toast = useToast()
  const status = useApi<any>('/api/system/status', [], 10000)
  const agents = useApi<any>('/api/agents')
  const sim = useApi<any>('/api/simulation')
  const [confirm, setConfirm] = useState(false)
  useLive('simulation', () => sim.reload())
  const isAdmin = user?.role === 'admin'
  const simAction = async (a: string) => {
    try { await api(`/api/simulation/${a}`, { method: 'POST' }); sim.reload() } catch (e: any) { toast({ title: 'Failed', message: e.message, level: 'critical' }) }
  }
  const reset = async () => {
    await api('/api/system/reset', { method: 'POST' })
    setConfirm(false)
    toast({ title: 'Demo data reset', message: 'The hospital has been re-seeded.', level: 'success' })
  }
  return (
    <div>
      <PageHeader title="System & architecture" icon={<Settings className="h-5 w-5" />} subtitle="Layered architecture from the project synopsis (§4.3), runtime status and demo controls"
        actions={<a href="/docs" target="_blank" rel="noreferrer"><Button variant="secondary" icon={<BookOpen className="h-4 w-4" />}>API docs (Swagger)</Button></a>} />
      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="Runtime status" icon={<Activity className="h-4 w-4" />}>
          {!status.data ? <Spinner /> : (
            <dl className="space-y-2 text-sm">
              <Row k="Application" v={`${status.data.app} v${status.data.version}`} />
              <Row k="Hospital" v={status.data.hospital} />
              <Row k="Database" v={<span className="inline-flex items-center gap-1"><Database className="h-3.5 w-3.5" />{status.data.database}</span>} />
              <Row k="NLP engine" v={status.data.llm.enabled ? <Badge tone="violet">Claude · {status.data.llm.model}</Badge> : <Badge tone="teal">Local NLP (offline)</Badge>} />
              {status.data.llm.last_error && <Row k="LLM last error" v={<span className="text-xs text-red-600">{status.data.llm.last_error}</span>} />}
              <Row k="Agents" v={status.data.agents} />
              <Row k="Live WebSocket clients" v={status.data.websocket_clients} />
              <Row k="Simulation" v={<Badge tone={status.data.simulation ? 'amber' : 'slate'}>{status.data.simulation ? 'running' : 'stopped'}</Badge>} />
            </dl>
          )}
        </Card>
        <Card title="Live simulation" subtitle="Generates OPD walk-ins, lab results, bed turnover, deterioration alerts and ER arrivals (routed through the agents)" icon={<Zap className="h-4 w-4" />} className="xl:col-span-2">
          {isAdmin && (
            <div className="mb-3 flex flex-wrap gap-2">
              {sim.data?.running ? <Button variant="secondary" icon={<Square className="h-4 w-4" />} onClick={() => simAction('stop')}>Stop</Button> : <Button icon={<Play className="h-4 w-4" />} onClick={() => simAction('start')}>Start simulation</Button>}
              <Button variant="secondary" icon={<StepForward className="h-4 w-4" />} onClick={() => simAction('tick')}>Single tick</Button>
              <Button variant="danger" icon={<Siren className="h-4 w-4" />} onClick={() => simAction('emergency')}>Trigger ER arrival</Button>
              <Button variant="ghost" icon={<RotateCcw className="h-4 w-4" />} onClick={() => setConfirm(true)}>Reset demo data</Button>
            </div>
          )}
          <div className="max-h-56 space-y-1 overflow-y-auto">
            {(sim.data?.events || []).map((e: any, i: number) => (
              <div key={i} className="flex gap-2 text-xs"><span className="w-16 shrink-0 text-slate-400">{ago(e.ts)}</span><Badge tone={e.kind === 'emergency' ? 'red' : e.kind === 'alert' ? 'amber' : 'slate'}>{e.kind}</Badge><span className="text-slate-600">{e.text}</span></div>
            ))}
            {!sim.data?.events?.length && <div className="text-xs text-slate-400">No simulation events yet{isAdmin ? ' — press Start or Single tick.' : '.'}</div>}
          </div>
        </Card>
      </div>

      <PolicyCard isAdmin={isAdmin} />

      <Card className="mt-4" title="System architecture" subtitle="Requests flow top → bottom; events flow back up over the WebSocket bus" icon={<Layers className="h-4 w-4" />}>
        <div className="space-y-2">
          {LAYERS.map((l, i) => (
            <div key={l.name}>
              <div className={cls('flex flex-wrap items-center gap-2 rounded-xl border p-3', l.color)}>
                <div className="w-48 shrink-0 text-sm font-semibold">{l.name}</div>
                <div className="flex flex-1 flex-wrap gap-1.5">{l.items.map((it) => <span key={it} className="rounded-md bg-white/80 px-2 py-1 text-xs shadow-sm">{it}</span>)}</div>
              </div>
              {i < LAYERS.length - 1 && <div className="flex justify-center text-slate-300">▼</div>}
            </div>
          ))}
        </div>
      </Card>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="Agent catalogue">
          <div className="space-y-3">
            {(agents.data?.agents || []).map((a: any) => {
              const m = meta(a.key)
              return (
                <div key={a.key} className="flex gap-3">
                  <div className="h-fit rounded-lg p-2" style={{ background: `${m.color}15`, color: m.color }}><m.icon className="h-4 w-4" /></div>
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-slate-800">{a.name}</div>
                    <div className="text-xs text-slate-500">{a.description}</div>
                    <div className="mt-1 flex flex-wrap gap-1">{a.capabilities.map((c: string) => <Badge key={c}>{c}</Badge>)}</div>
                  </div>
                </div>
              )
            })}
          </div>
        </Card>
        <Card title="Technology stack">
          <table className="w-full text-sm">
            <tbody className="divide-y divide-slate-100">{STACK.map(([k, v]) => <tr key={k}><td className="w-36 py-2 font-medium text-slate-700">{k}</td><td className="py-2 text-slate-600">{v}</td></tr>)}</tbody>
          </table>
        </Card>
      </div>

      <Modal open={confirm} onClose={() => setConfirm(false)} title="Reset demo data?" footer={<><Button variant="secondary" onClick={() => setConfirm(false)}>Cancel</Button><Button variant="danger" onClick={reset}>Reset & re-seed</Button></>}>
        <p className="text-sm text-slate-600">This drops all tables and regenerates the synthetic hospital (patients, beds, staff, history). Agent requests, approvals and audit entries created during the demo will be removed.</p>
      </Modal>
    </div>
  )
}

function PolicyCard({ isAdmin }: { isAdmin: boolean }) {
  const toast = useToast()
  const { data, reload } = useApi<any>('/api/settings', ['settings'])
  const [busy, setBusy] = useState(false)
  if (!data) return null
  const v = data.values
  const save = async (values: any) => {
    setBusy(true)
    try { await api('/api/settings', { method: 'PUT', body: { values } }); toast({ title: 'Policy updated', level: 'success' }); reload() }
    catch (e: any) { toast({ title: 'Update failed', message: e.message, level: 'critical' }) } finally { setBusy(false) }
  }
  return (
    <Card className="mt-4" title="Human-in-the-loop autonomy policy" subtitle="Controls which agent actions may execute automatically — every decision is audited" icon={<ShieldCheck className="h-4 w-4" />}>
      <div className="grid gap-3 md:grid-cols-3">
        {Object.entries(data.autonomy_modes).map(([k, desc]: any) => (
          <button key={k} disabled={!isAdmin || busy} onClick={() => save({ autonomy_mode: k })}
            className={cls('rounded-xl border p-3 text-left transition disabled:cursor-default', v.autonomy_mode === k ? 'border-teal-500 bg-teal-50 ring-2 ring-teal-500/20' : 'border-slate-200 hover:border-teal-300')}>
            <div className="flex items-center gap-2"><span className={cls('h-3 w-3 rounded-full border-2', v.autonomy_mode === k ? 'border-teal-600 bg-teal-600' : 'border-slate-300')} /><span className="text-sm font-semibold capitalize">{k}</span></div>
            <p className="mt-1 text-xs text-slate-600">{desc}</p>
          </button>
        ))}
      </div>
      <div className="mt-4 grid gap-3 text-sm md:grid-cols-3">
        <label className="flex items-center justify-between gap-2 rounded-lg bg-slate-50 px-3 py-2">NEWS2 urgent-review threshold
          <input type="number" min={1} max={10} disabled={!isAdmin} className="w-16 rounded border border-slate-200 px-2 py-0.5" defaultValue={v.news2_review_threshold}
            onBlur={(e) => Number(e.target.value) !== v.news2_review_threshold && save({ news2_review_threshold: Number(e.target.value) })} /></label>
        <label className="flex items-center justify-between gap-2 rounded-lg bg-slate-50 px-3 py-2">NEWS2 emergency threshold
          <input type="number" min={3} max={14} disabled={!isAdmin} className="w-16 rounded border border-slate-200 px-2 py-0.5" defaultValue={v.news2_escalation_threshold}
            onBlur={(e) => Number(e.target.value) !== v.news2_escalation_threshold && save({ news2_escalation_threshold: Number(e.target.value) })} /></label>
        <label className="flex items-center justify-between gap-2 rounded-lg bg-slate-50 px-3 py-2">Auto-propose ICU transfer
          <input type="checkbox" disabled={!isAdmin} checked={!!v.auto_icu_transfer_proposal} onChange={(e) => save({ auto_icu_transfer_proposal: e.target.checked })} /></label>
      </div>
      {!isAdmin && <p className="mt-2 text-xs text-slate-400">Only administrators can change the policy.</p>}
    </Card>
  )
}

function Row({ k, v }: { k: string; v: any }) {
  return <div className="flex items-center justify-between gap-3"><dt className="text-slate-500">{k}</dt><dd className="text-right text-slate-800">{v}</dd></div>
}
