import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  AlertTriangle, ArrowRight, Bot, Brain, CheckCircle2, CircleDashed, GitBranch, Loader2, MessageSquare, Mic, MicOff, Send, Sparkles, UserCheck, Wand2, XCircle, Zap,
} from 'lucide-react'

const SpeechRec: any = typeof window !== 'undefined' ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition : null
import { api } from '../api'
import AgentNetwork from '../components/AgentNetwork'
import ApprovalCard from '../components/ApprovalCard'
import { meta } from '../components/agentMeta'
import PageHeader from '../components/PageHeader'
import { Badge, Button, Card, Empty, Factors, Spinner, StatusBadge, useToast } from '../components/ui'
import { useApi, useLive } from '../live'
import { ago, cls, label } from '../utils'

const TERMINAL = new Set(['completed', 'awaiting_approval', 'failed', 'rejected'])
const STAGES = [
  { key: 'intake', label: 'Intake' }, { key: 'nlp', label: 'NLP understanding' }, { key: 'plan', label: 'Agent planning' },
  { key: 'exec', label: 'Coordinated execution' }, { key: 'conflict', label: 'Conflict resolution' }, { key: 'hitl', label: 'Human approval gate' },
  { key: 'notify', label: 'Notify & log' },
]

function stageIndex(trace: any[], status: string) {
  if (TERMINAL.has(status)) return STAGES.length
  const kinds = new Set(trace.map((e) => e.kind))
  if (trace.some((e) => e.agent === 'notification')) return 6
  if (kinds.has('approval') || kinds.has('action')) return 5
  if (kinds.has('conflict') || trace.some((e) => e.title?.startsWith('Conflict check'))) return 4
  if (kinds.has('agent_start')) return 3
  if (kinds.has('plan')) return 2
  if (kinds.has('understanding')) return 1
  return 0
}

export default function AgentConsole() {
  const [params, setParams] = useSearchParams()
  const selected = params.get('request') ? Number(params.get('request')) : null
  const toast = useToast()
  const [text, setText] = useState('')
  const [patientId, setPatientId] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [req, setReq] = useState<any>(null)
  const [trace, setTrace] = useState<any[]>([])
  const history = useApi<any[]>('/api/agents/requests?limit=40')
  const scenarios = useApi<any[]>('/api/agents/scenarios')
  const agents = useApi<any>('/api/agents')
  const patients = useApi<any>('/api/patients?limit=300')
  const traceEnd = useRef<HTMLDivElement>(null)
  const [listening, setListening] = useState(false)
  const recRef = useRef<any>(null)

  useEffect(() => {  // prefill from quick actions elsewhere in the app (?text=…&patient=…)
    const t = params.get('text')
    if (t && !params.get('request')) {
      setText(t)
      if (params.get('patient')) setPatientId(params.get('patient')!)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const toggleVoice = () => {
    if (listening) { recRef.current?.stop(); return }
    const rec = new SpeechRec()
    rec.lang = 'en-IN'
    rec.interimResults = true
    rec.continuous = false
    rec.onresult = (e: any) => setText(Array.from(e.results).map((r: any) => r[0].transcript).join(''))
    rec.onend = () => setListening(false)
    rec.onerror = () => setListening(false)
    recRef.current = rec
    rec.start()
    setListening(true)
  }

  const load = useCallback(async (id: number) => {
    try {
      const r = await api(`/api/agents/requests/${id}`)
      setReq(r)
      setTrace((t) => (r.trace.length >= t.length ? r.trace : t))
      return r
    } catch { return null }
  }, [])

  useEffect(() => {
    setReq(null)
    setTrace([])
    if (!selected) return
    let stop = false
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      const r = await load(selected)
      if (!stop && (!r || !TERMINAL.has(r.status))) timer = setTimeout(poll, 900)
    }
    poll()
    return () => { stop = true; clearTimeout(timer) }
  }, [selected, load])

  useLive('agent.trace', (d: any) => {
    if (d.request_id !== selected) return
    setTrace((t) => (t.some((e) => e.seq === d.event.seq) ? t : [...t, d.event].sort((a, b) => a.seq - b.seq)))
  })
  useLive('agent.request', (d: any) => {
    history.reload()
    if (d.id === selected && TERMINAL.has(d.status)) load(d.id)
  })
  useLive('approval', (d: any) => { if (selected && d.request_id === selected) load(selected) })

  useEffect(() => {  // keep the trace pane pinned to the newest event without scrolling the page
    const box = traceEnd.current?.parentElement
    if (box) box.scrollTop = box.scrollHeight
  }, [trace.length])

  const submit = async (t = text) => {
    if (!t.trim()) return
    setSubmitting(true)
    try {
      const r = await api('/api/agents/requests', { body: { text: t, patient_id: patientId ? Number(patientId) : null } })
      setParams({ request: String(r.id) })
      setText('')
      history.reload()
    } catch (e: any) {
      toast({ title: 'Request failed', message: e.message, level: 'critical' })
    } finally { setSubmitting(false) }
  }

  const derived = useMemo(() => {
    const active = new Set<string>(), done = new Set<string>(), used = new Set<string>()
    const messages: any[] = []
    for (const e of trace) {
      if (e.kind === 'agent_start' && e.agent) { active.add(e.agent); used.add(e.agent) }
      if ((e.kind === 'agent_result' || e.kind === 'agent_skip') && e.agent) { active.delete(e.agent); done.add(e.agent) }
      if (e.kind === 'message' && e.data) {
        messages.push({ from: e.data.from, to: e.data.to, performative: e.data.performative, at: new Date(e.ts).getTime() })
        used.add(e.data.from); used.add(e.data.to)
      }
    }
    for (const s of req?.plan || []) used.add(s.agent)
    // replay recent messages as "fresh" while live so they animate
    const liveNow = Date.now()
    const latest = messages.length ? Math.max(...messages.map((m) => m.at)) : 0
    const shifted = messages.map((m) => ({ ...m, at: liveNow - (latest - m.at) }))
    return { active, done, used, messages: req && TERMINAL.has(req.status) ? [] : shifted }
  }, [trace, req])

  const status = req?.status || (selected ? 'received' : '')
  const busy = !!selected && !TERMINAL.has(status)
  const stage = stageIndex(trace, status)
  const alternatives = useMemo(() => {
    const cands = req?.results?.['bed.find_beds']?.data?.candidates || []
    const docs = req?.results?.['staff.find_staff']?.data?.doctors || []
    return {
      bed_id: cands.map((c: any) => ({ value: c.bed_id, label: `${c.code} — ${c.ward} (fit ${c.fit_score})` })),
      doctor_id: docs.map((d: any) => ({ value: d.id, label: `${d.name} (load ${d.load}/${d.max})` })),
    }
  }, [req])

  return (
    <div>
      <PageHeader title="AI Agent Console" icon={<Bot className="h-5 w-5" />}
        subtitle="Describe a hospital need in natural language — the orchestrator plans, coordinates specialised agents and asks humans to approve critical actions." />

      <div className="grid gap-4 xl:grid-cols-[18rem_1fr]">
        {/* history */}
        <Card title="Request history" className="order-2 xl:order-1" bodyClass="p-0">
          <div className="max-h-[calc(100vh-14rem)] divide-y divide-slate-100 overflow-y-auto">
            {(history.data || []).map((r) => (
              <button key={r.id} onClick={() => setParams({ request: String(r.id) })}
                className={cls('block w-full px-4 py-2.5 text-left hover:bg-slate-50', r.id === selected && 'bg-teal-50/60')}>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[11px] text-slate-400">#{r.id}</span>
                  <StatusBadge status={r.status} />
                  {r.pending_approvals > 0 && <Badge tone="amber">{r.pending_approvals} pending</Badge>}
                  <span className="ml-auto text-[10px] text-slate-400">{ago(r.created_at)}</span>
                </div>
                <div className="mt-1 line-clamp-2 text-xs text-slate-700">{r.text}</div>
                <div className="mt-1 text-[10px] text-slate-400">{r.source}{r.duration_ms ? ` · ${r.duration_ms} ms` : ''}</div>
              </button>
            ))}
            {!history.data?.length && <Empty title="No requests yet" />}
          </div>
        </Card>

        <div className="order-1 min-w-0 space-y-4 xl:order-2">
          {/* composer */}
          <Card>
            <div className="flex flex-col gap-3 md:flex-row">
              <textarea className="input min-h-[76px] flex-1 resize-y" value={text} onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submit() }}
                placeholder='e.g. "Patient needs admission and requires ICU monitoring" or "Emergency: 60 year old with chest pain, BP 90/60, SpO2 91%"' />
              <div className="flex flex-col gap-2 md:w-56">
                <select className="input text-xs" value={patientId} onChange={(e) => setPatientId(e.target.value)}>
                  <option value="">Patient (optional — or name in text)</option>
                  {(patients.data?.items || []).map((p: any) => <option key={p.id} value={p.id}>{p.name} · {p.mrn}</option>)}
                </select>
                <Button onClick={() => submit()} loading={submitting} icon={<Send className="h-4 w-4" />} disabled={!text.trim()}>Run agents</Button>
                {SpeechRec && (
                  <Button variant={listening ? 'danger' : 'secondary'} icon={listening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />} onClick={toggleVoice}>
                    {listening ? 'Listening… stop' : 'Speak request'}
                  </Button>
                )}
                <div className="text-center text-[10px] text-slate-400">Ctrl + Enter to send{SpeechRec ? ' · voice: en-IN' : ''}</div>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <span className="flex items-center gap-1 text-[11px] font-medium text-slate-500"><Wand2 className="h-3 w-3" />Try:</span>
              {(scenarios.data || []).map((s) => (
                <button key={s.title} onClick={() => submit(s.text)} title={s.text} disabled={submitting}
                  className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] text-slate-600 transition hover:border-teal-400 hover:bg-teal-50 hover:text-teal-800">
                  {s.title}
                </button>
              ))}
            </div>
          </Card>

          {!selected && <Intro agents={agents.data} />}
          {selected && !req && <Spinner label="Starting orchestration…" />}

          {selected && req && (
            <>
              {/* header + pipeline */}
              <Card>
                <div className="flex flex-wrap items-start gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                      <span className="font-mono">Request #{req.id}</span><StatusBadge status={req.status} />
                      <Badge tone="violet"><Brain className="h-3 w-3" />{req.nlp_engine}</Badge>
                      {req.duration_ms > 0 && <Badge tone="slate">{req.duration_ms} ms</Badge>}
                      <Badge tone="slate">{req.source}</Badge>
                    </div>
                    <div className="mt-1.5 text-base font-medium text-slate-900">“{req.text}”</div>
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-7 gap-1">
                  {STAGES.map((s, i) => (
                    <div key={s.key} className="text-center">
                      <div className={cls('h-1.5 rounded-full transition-all', i < stage ? 'bg-teal-500' : i === stage && busy ? 'blink bg-teal-300' : 'bg-slate-200')} />
                      <div className={cls('mt-1.5 text-[10px] leading-tight', i <= stage ? 'font-medium text-slate-700' : 'text-slate-400')}>{s.label}</div>
                    </div>
                  ))}
                </div>
              </Card>

              <div className="grid gap-4 2xl:grid-cols-2">
                <Card title="Live agent network" subtitle="Orchestrator dispatch and inter-agent messages (FIPA-ACL performatives)" icon={<GitBranch className="h-4 w-4" />}>
                  <div className="h-[330px]"><AgentNetwork active={derived.active} used={derived.used} done={derived.done} messages={derived.messages} busy={busy} /></div>
                </Card>
                <Card title="Live trace" subtitle={`${trace.length} events`} icon={<MessageSquare className="h-4 w-4" />} bodyClass="p-0">
                  <div className="h-[362px] overflow-y-auto px-4 py-3">
                    <ol className="relative space-y-2.5 border-l border-slate-200 pl-4">
                      {trace.map((e) => <TraceItem key={e.seq} e={e} />)}
                      {busy && <li className="flex items-center gap-2 text-xs text-slate-400"><Loader2 className="h-3 w-3 animate-spin" />agents working…</li>}
                    </ol>
                    <div ref={traceEnd} />
                  </div>
                </Card>
              </div>

              {req.intents?.length > 0 && (
                <div className="grid gap-4 lg:grid-cols-2">
                  <Card title="Understanding" subtitle="Intent classification & entity extraction" icon={<Brain className="h-4 w-4" />}>
                    <div className="space-y-2">
                      {req.intents.map((i: any) => (
                        <div key={i.name} className="flex items-center gap-3 text-sm">
                          <span className="w-32 font-medium capitalize text-slate-700">{label(i.name)}</span>
                          <div className="h-2 flex-1 rounded-full bg-slate-100"><div className="h-full rounded-full bg-violet-500" style={{ width: `${i.confidence * 100}%` }} /></div>
                          <span className="w-12 text-right text-xs tabular-nums text-slate-500">{(i.confidence * 100).toFixed(0)}%</span>
                        </div>
                      ))}
                    </div>
                    <div className="mt-4 flex flex-wrap gap-1.5">
                      {Object.entries(req.entities || {}).filter(([k]) => !k.startsWith('_')).map(([k, v]) => (
                        <span key={k} className="rounded-md bg-slate-100 px-2 py-1 text-[11px]"><span className="text-slate-500">{label(k)}:</span>{' '}
                          <span className="font-medium text-slate-800">{typeof v === 'object' ? (Array.isArray(v) ? v.map((x: any) => x?.name || x).join(', ') : Object.entries(v as any).map(([a, b]) => `${a} ${b}`).join(', ')) : String(v)}</span>
                        </span>
                      ))}
                    </div>
                  </Card>
                  <Card title="Execution plan" subtitle="Dependency-ordered workflow built by the orchestrator" icon={<GitBranch className="h-4 w-4" />}>
                    <PlanView plan={req.plan || []} results={req.results || {}} active={derived.active} />
                  </Card>
                </div>
              )}

              {Object.keys(req.results || {}).filter((k) => !k.startsWith('_')).length > 0 && (
                <Card title="Agent findings & explainable recommendations" icon={<Sparkles className="h-4 w-4" />}>
                  <div className="grid gap-3 lg:grid-cols-2">
                    {Object.entries(req.results).filter(([k]) => !k.startsWith('_')).map(([k, r]: any) => <ResultCard key={k} step={k} r={r} />)}
                  </div>
                </Card>
              )}

              {(req.conflicts?.length > 0 || req.approvals?.length > 0 || req.results?._executed?.length > 0) && (
                <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
                  <Card title="Human-in-the-loop approvals" subtitle="Safety-critical actions wait for an authorised person" icon={<UserCheck className="h-4 w-4" />}>
                    {req.approvals?.length ? (
                      <div className="space-y-3">{req.approvals.map((a: any) => <ApprovalCard key={a.id} approval={a} alternatives={alternatives} onDone={() => load(req.id)} />)}</div>
                    ) : <Empty title="No approvals required" hint="All proposed actions were low-risk and executed automatically" />}
                  </Card>
                  <div className="space-y-4">
                    <Card title="Auto-executed" icon={<Zap className="h-4 w-4" />}>
                      {req.results?._executed?.length ? req.results._executed.map((e: any, i: number) => (
                        <div key={i} className="mb-2 flex gap-2 text-xs"><CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" /><span>{e.title}</span></div>
                      )) : <div className="text-xs text-slate-400">Nothing executed automatically.</div>}
                    </Card>
                    <Card title="Conflict resolution" icon={<AlertTriangle className="h-4 w-4" />}>
                      {req.conflicts?.length ? req.conflicts.map((c: any, i: number) => (
                        <div key={i} className="mb-2 rounded-lg bg-amber-50 p-2 text-xs">
                          <div className="font-medium text-amber-900">{c.description}</div>
                          <div className="mt-0.5 text-amber-800">→ {c.resolution}</div>
                        </div>
                      )) : <div className="text-xs text-slate-400">No conflicts between agent proposals.</div>}
                    </Card>
                  </div>
                </div>
              )}

              {req.summary && (
                <Card title="Coordination brief" subtitle={req.nlp_engine?.startsWith('Claude') ? 'Written by Claude from agent findings' : 'Compiled from agent findings'} icon={<Sparkles className="h-4 w-4" />}>
                  <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">{req.summary}</div>
                </Card>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function TraceItem({ e }: { e: any }) {
  const m = meta(e.agent)
  const icon = e.kind === 'error' ? <XCircle className="h-3.5 w-3.5 text-red-500" />
    : e.kind === 'conflict' ? <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
      : e.kind === 'approval' ? <UserCheck className="h-3.5 w-3.5 text-amber-600" />
        : e.kind === 'human' ? <UserCheck className="h-3.5 w-3.5 text-slate-700" />
          : e.kind === 'action' ? <Zap className="h-3.5 w-3.5 text-emerald-600" />
            : e.kind === 'done' ? <CheckCircle2 className="h-3.5 w-3.5 text-teal-600" />
              : e.kind === 'message' ? <ArrowRight className="h-3.5 w-3.5" style={{ color: m.color }} />
                : e.kind === 'agent_start' ? <CircleDashed className="h-3.5 w-3.5" style={{ color: m.color }} />
                  : <m.icon className="h-3.5 w-3.5" style={{ color: m.color }} />
  return (
    <li className="fade-in relative">
      <span className="absolute -left-[23px] top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-white ring-2 ring-white">{icon}</span>
      <div className="flex items-baseline gap-2">
        <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wide" style={{ color: m.color }}>{e.agent === 'orchestrator' ? 'orchestrator' : m.short}</span>
        <span className={cls('text-xs', e.kind === 'agent_result' ? 'text-slate-800' : e.kind === 'message' ? 'font-medium text-slate-600' : 'text-slate-600', e.kind === 'blackboard' && 'text-slate-400')}>{e.title}</span>
        {e.t_ms !== undefined && <span className="ml-auto shrink-0 font-mono text-[10px] text-slate-300">{e.t_ms}ms</span>}
      </div>
      {e.detail && <div className="mt-0.5 text-[11px] text-slate-500">{e.detail}</div>}
    </li>
  )
}

function PlanView({ plan, results, active }: { plan: any[]; results: any; active: Set<string> }) {
  const levels = [...new Set(plan.map((s) => s.level))].sort((a, b) => a - b)
  return (
    <div className="flex gap-2 overflow-x-auto pb-1">
      {levels.map((lv, idx) => (
        <div key={lv} className="flex items-center gap-2">
          <div className="min-w-[9.5rem] space-y-1.5">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Level {lv}</div>
            {plan.filter((s) => s.level === lv).map((s) => {
              const r = results[s.id]
              const m = meta(s.agent)
              const st = r?.status || (active.has(s.agent) ? 'running' : 'waiting')
              return (
                <div key={s.id} className="rounded-lg border px-2 py-1.5" style={{ borderColor: `${m.color}55`, background: `${m.color}0d` }}>
                  <div className="flex items-center gap-1.5 text-[11px] font-medium" style={{ color: m.color }}><m.icon className="h-3 w-3" />{m.short}</div>
                  <div className="text-[11px] text-slate-700">{label(s.action)}</div>
                  <div className="mt-0.5"><Badge tone={st === 'success' ? 'green' : st === 'failed' ? 'red' : st === 'partial' ? 'amber' : st === 'running' ? 'blue' : 'slate'}>{st}</Badge></div>
                </div>
              )
            })}
          </div>
          {idx < levels.length - 1 && <ArrowRight className="h-4 w-4 shrink-0 text-slate-300" />}
        </div>
      ))}
    </div>
  )
}

function ResultCard({ step, r }: { step: string; r: any }) {
  const m = meta(r.agent)
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-xl border border-slate-200 p-3">
      <div className="flex items-center gap-2">
        <div className="rounded-lg p-1.5" style={{ background: `${m.color}15`, color: m.color }}><m.icon className="h-4 w-4" /></div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-slate-800">{m.name}</div>
          <div className="font-mono text-[10px] text-slate-400">{step}</div>
        </div>
        <StatusBadge status={r.status === 'success' ? 'completed' : r.status === 'partial' ? 'warning' : r.status} />
      </div>
      <p className="mt-2 text-xs leading-relaxed text-slate-600">{r.summary}</p>
      {r.recommendations?.length > 0 && (
        <div className="mt-2 space-y-2">
          {r.recommendations.slice(0, open ? 10 : 2).map((rec: any, i: number) => (
            <div key={i} className="rounded-lg bg-slate-50 p-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium text-slate-800">{rec.title}</span>
                {rec.score !== null && rec.score !== undefined && <Badge tone="teal">{rec.score}</Badge>}
              </div>
              {rec.detail && <div className="text-[11px] text-slate-500">{rec.detail}</div>}
              {open && <Factors factors={rec.factors} />}
            </div>
          ))}
          {(r.recommendations.length > 2 || r.recommendations.some((x: any) => x.factors?.length)) && (
            <button onClick={() => setOpen((o) => !o)} className="text-[11px] font-medium text-teal-700 hover:underline">{open ? 'Hide details' : 'Explain — show factor breakdown'}</button>
          )}
        </div>
      )}
    </div>
  )
}

function Intro({ agents }: { agents: any }) {
  return (
    <Card>
      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <h3 className="text-base font-semibold text-slate-900">How the multi-agent engine works</h3>
          <ol className="mt-3 space-y-2 text-sm text-slate-600">
            {['Request intake from staff, the emergency desk, the patient portal or the live simulator',
              'NLP classifies intents and extracts entities (Claude when configured, otherwise local TF-IDF + logistic regression)',
              'The orchestrator selects agents and builds a dependency-ordered plan',
              'Agents collaborate through a shared blackboard and FIPA-ACL style messages',
              'OR-Tools CP-SAT optimisation, NEWS2 triage, queueing theory and forecasting power the decisions',
              'Conflicts (contention, overload, safety) are resolved by priority rules',
              'Low-risk reversible actions run automatically; safety-critical ones wait for human approval',
              'Everything is logged, audited and pushed live over WebSockets'].map((s, i) => (
              <li key={i} className="flex gap-2"><span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-teal-100 text-[11px] font-semibold text-teal-800">{i + 1}</span>{s}</li>
            ))}
          </ol>
        </div>
        <div>
          <h3 className="text-base font-semibold text-slate-900">Specialised agents</h3>
          <div className="mt-3 space-y-2">
            {(agents?.agents || []).map((a: any) => {
              const m = meta(a.key)
              return (
                <div key={a.key} className="flex items-start gap-2.5">
                  <div className="rounded-lg p-1.5" style={{ background: `${m.color}15`, color: m.color }}><m.icon className="h-4 w-4" /></div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 text-sm font-medium text-slate-800">{a.name}{a.tasks > 0 && <Badge tone="slate">{a.tasks} tasks</Badge>}</div>
                    <div className="text-xs text-slate-500">{a.description}</div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </Card>
  )
}
