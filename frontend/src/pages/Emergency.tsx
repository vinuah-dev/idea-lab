import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Ambulance, Bot, HeartPulse, Siren } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import { Badge, Button, Card, Empty, Field, Spinner, StatusBadge, useToast } from '../components/ui'
import { useApi } from '../live'
import { cls, label, TRIAGE_COLORS } from '../utils'

const PRESETS = [
  { name: 'Chest pain', complaint: 'Crushing chest pain radiating to left arm with sweating', age: 62, gender: 'Male', arrival_mode: 'ambulance', vitals: { hr: 118, rr: 24, spo2: 93, sbp: 94, temp: 36.9, consciousness: 'A', on_oxygen: false } },
  { name: 'Stroke', complaint: 'Sudden facial droop and slurred speech, right arm weakness', age: 71, gender: 'Female', arrival_mode: 'ambulance', vitals: { hr: 96, rr: 18, spo2: 95, sbp: 182, temp: 37.0, consciousness: 'C', on_oxygen: false } },
  { name: 'Sepsis', complaint: 'High fever, confusion and low blood pressure — suspected sepsis', age: 55, gender: 'Male', arrival_mode: 'walk-in', vitals: { hr: 128, rr: 26, spo2: 92, sbp: 86, temp: 39.7, consciousness: 'C', on_oxygen: false } },
  { name: 'Asthma', complaint: 'Severe breathlessness, known asthmatic', age: 28, gender: 'Female', arrival_mode: 'walk-in', vitals: { hr: 122, rr: 28, spo2: 89, sbp: 128, temp: 37.2, consciousness: 'A', on_oxygen: true } },
  { name: 'Minor injury', complaint: 'Fall from bicycle — wrist pain and swelling', age: 19, gender: 'Male', arrival_mode: 'walk-in', vitals: { hr: 86, rr: 16, spo2: 99, sbp: 124, temp: 36.8, consciousness: 'A', on_oxygen: false } },
]

const NEWS_LABEL: Record<string, string> = { respiration_rate: 'Resp. rate', spo2: 'SpO₂', supplemental_o2: 'Supplemental O₂', systolic_bp: 'Systolic BP', pulse: 'Pulse', consciousness: 'Consciousness', temperature: 'Temperature' }

export default function Emergency() {
  const nav = useNavigate()
  const toast = useToast()
  const board = useApi<any[]>('/api/emergency', ['emergency'], 20000)
  const [f, setF] = useState<any>({ name: '', age: 45, gender: 'Male', arrival_mode: 'walk-in', chief_complaint: '', auto_coordinate: true,
    vitals: { hr: 90, rr: 18, spo2: 97, sbp: 125, temp: 37.0, consciousness: 'A', on_oxygen: false } })
  const [preview, setPreview] = useState<any>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const id = setTimeout(() => {
      api('/api/emergency/triage-preview', { body: { chief_complaint: f.chief_complaint, age: Number(f.age), vitals: numVitals(f.vitals) } }).then(setPreview).catch(() => {})
    }, 250)
    return () => clearTimeout(id)
  }, [f.chief_complaint, f.age, f.vitals])

  const submit = async () => {
    setBusy(true)
    try {
      const r = await api('/api/emergency', { body: { ...f, age: Number(f.age), name: f.name || null, vitals: numVitals(f.vitals) } })
      toast({ title: `Triage L${r.triage.triage_level}: ${r.triage.triage_label}`, message: `NEWS2 ${r.triage.news2} — ${r.request_id ? 'agents are coordinating bed, team and diagnostics' : 'registered'}`, level: r.triage.triage_level <= 2 ? 'critical' : 'info' })
      if (r.request_id) nav(`/agents?request=${r.request_id}`)
    } catch (e: any) { toast({ title: 'Registration failed', message: e.message, level: 'critical' }) } finally { setBusy(false) }
  }
  const setStatus = async (c: any, status: string) => {
    try { await api(`/api/emergency/${c.id}`, { method: 'PATCH', body: { status } }) } catch (e: any) { toast({ title: 'Failed', message: e.message, level: 'critical' }) }
  }
  const v = f.vitals
  const setV = (k: string, val: any) => setF({ ...f, vitals: { ...v, [k]: val } })
  const tc = preview ? TRIAGE_COLORS[preview.triage_level] : null

  return (
    <div>
      <PageHeader title="Emergency department" icon={<Siren className="h-5 w-5" />} subtitle="NEWS2 early-warning triage (Royal College of Physicians) + red-flag detection → Emergency Support Agent mobilises bed, team and diagnostics"
        actions={<Link to="/ambulance" className="inline-flex items-center gap-1.5 rounded-lg bg-fuchsia-50 px-3 py-1.5 text-xs font-medium text-fuchsia-800 ring-1 ring-inset ring-fuchsia-200 hover:bg-fuchsia-100"><Ambulance className="h-3.5 w-3.5" />Ambulance & 108 dispatch</Link>} />
      <div className="grid gap-4 xl:grid-cols-[28rem_1fr]">
        <div className="space-y-4">
          <Card title="New emergency arrival" icon={<Ambulance className="h-4 w-4" />}>
            <div className="mb-3 flex flex-wrap gap-1.5">
              {PRESETS.map((p) => <button key={p.name} onClick={() => setF({ ...f, name: '', chief_complaint: p.complaint, age: p.age, gender: p.gender, arrival_mode: p.arrival_mode, vitals: p.vitals })}
                className="rounded-full border border-slate-200 px-2.5 py-1 text-[11px] text-slate-600 hover:border-red-300 hover:bg-red-50 hover:text-red-700">{p.name}</button>)}
            </div>
            <div className="grid grid-cols-6 gap-2.5">
              <div className="col-span-3"><Field label="Name (blank = unknown)"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field></div>
              <div className="col-span-1"><Field label="Age"><input className="input" type="number" value={f.age} onChange={(e) => setF({ ...f, age: e.target.value })} /></Field></div>
              <div className="col-span-2"><Field label="Sex"><select className="input" value={f.gender} onChange={(e) => setF({ ...f, gender: e.target.value })}><option>Male</option><option>Female</option></select></Field></div>
              <div className="col-span-6"><Field label="Chief complaint"><input className="input" value={f.chief_complaint} onChange={(e) => setF({ ...f, chief_complaint: e.target.value })} placeholder="e.g. chest pain with sweating" /></Field></div>
              <div className="col-span-2"><Field label="Heart rate"><input className="input" type="number" value={v.hr} onChange={(e) => setV('hr', e.target.value)} /></Field></div>
              <div className="col-span-2"><Field label="Resp. rate"><input className="input" type="number" value={v.rr} onChange={(e) => setV('rr', e.target.value)} /></Field></div>
              <div className="col-span-2"><Field label="SpO₂ %"><input className="input" type="number" value={v.spo2} onChange={(e) => setV('spo2', e.target.value)} /></Field></div>
              <div className="col-span-2"><Field label="Systolic BP"><input className="input" type="number" value={v.sbp} onChange={(e) => setV('sbp', e.target.value)} /></Field></div>
              <div className="col-span-2"><Field label="Temp °C"><input className="input" type="number" step="0.1" value={v.temp} onChange={(e) => setV('temp', e.target.value)} /></Field></div>
              <div className="col-span-2"><Field label="ACVPU"><select className="input" value={v.consciousness} onChange={(e) => setV('consciousness', e.target.value)}><option value="A">Alert</option><option value="C">Confused (new)</option><option value="V">Voice</option><option value="P">Pain</option><option value="U">Unresponsive</option></select></Field></div>
              <div className="col-span-3"><Field label="Arrival"><select className="input" value={f.arrival_mode} onChange={(e) => setF({ ...f, arrival_mode: e.target.value })}><option value="walk-in">Walk-in</option><option value="ambulance">Ambulance</option><option value="referral">Referral</option></select></Field></div>
              <label className="col-span-3 flex items-end gap-2 pb-2 text-sm"><input type="checkbox" checked={v.on_oxygen} onChange={(e) => setV('on_oxygen', e.target.checked)} />On supplemental O₂</label>
            </div>
            <label className="mt-3 flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={f.auto_coordinate} onChange={(e) => setF({ ...f, auto_coordinate: e.target.checked })} /><Bot className="h-4 w-4 text-teal-600" />Let the agents coordinate bed, team & workup</label>
            <Button className="mt-3 w-full" variant="danger" loading={busy} disabled={f.chief_complaint.length < 3} onClick={submit} icon={<Siren className="h-4 w-4" />}>Register & triage</Button>
          </Card>

          {preview && tc && (
            <Card title="Live triage preview" icon={<HeartPulse className="h-4 w-4" />}>
              <div className="flex items-center gap-4">
                <div className={cls('flex h-16 w-16 flex-col items-center justify-center rounded-xl text-white', tc.bg)}>
                  <div className="text-[10px] uppercase">Level</div><div className="text-2xl font-bold leading-none">{preview.triage_level}</div>
                </div>
                <div>
                  <div className="text-lg font-semibold">{preview.triage_label}</div>
                  <div className="text-sm text-slate-600">NEWS2 <b>{preview.news2}</b> · {preview.clinical_risk} clinical risk</div>
                  <div className="text-xs text-slate-500">Target time to doctor: {preview.target_minutes === 0 ? 'immediate' : `${preview.target_minutes} min`}</div>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-1.5">
                {Object.entries(preview.news2_components).map(([k, pts]: any) => (
                  <div key={k} className={cls('flex justify-between rounded-md px-2 py-1 text-xs', pts >= 3 ? 'bg-red-50 text-red-700' : pts >= 2 ? 'bg-orange-50 text-orange-700' : pts >= 1 ? 'bg-amber-50 text-amber-800' : 'bg-slate-50 text-slate-500')}>
                    <span>{NEWS_LABEL[k] || k}</span><b>{pts}</b>
                  </div>
                ))}
              </div>
              {preview.red_flags.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{preview.red_flags.map((r: string) => <Badge key={r} tone="red">🚩 {r}</Badge>)}</div>}
            </Card>
          )}
        </div>

        <Card title="ED board" subtitle="Sorted by triage level, then arrival time" icon={<Siren className="h-4 w-4" />}>
          {board.loading && !board.data ? <Spinner /> : !board.data?.length ? <Empty title="No active emergency cases" /> : (
            <div className="space-y-2">
              {board.data.map((c) => {
                const t = TRIAGE_COLORS[c.triage_level]
                return (
                  <div key={c.id} className={cls('flex overflow-hidden rounded-xl border bg-white', c.status === 'incoming' ? 'border-fuchsia-300 ring-2 ring-fuchsia-100' : c.breach ? 'border-red-300 ring-2 ring-red-100' : 'border-slate-200')}>
                    <div className={cls('flex w-16 shrink-0 flex-col items-center justify-center text-white', t.bg)}><div className="text-[10px] uppercase">Triage</div><div className="text-xl font-bold">L{c.triage_level}</div></div>
                    <div className="min-w-0 flex-1 p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <Link to={`/patients/${c.patient?.id}`} className="font-semibold text-slate-800 hover:text-teal-700">{c.patient?.name}</Link>
                        <span className="text-xs text-slate-500">{c.patient?.age}{c.patient?.gender?.[0]} · {c.arrival_mode}</span>
                        <StatusBadge status={c.status} />
                        <Badge tone={c.news2_score >= 7 ? 'red' : c.news2_score >= 5 ? 'orange' : 'slate'}>NEWS2 {c.news2_score}</Badge>
                        {c.breach && <Badge tone="red">TARGET BREACHED</Badge>}
                        {c.status === 'incoming' && <Badge tone="violet">🚑 Incoming — pre-alerted{c.bed ? `, bay ${c.bed} held` : ''}</Badge>}
                      </div>
                      <div className="mt-0.5 text-sm text-slate-600">{c.chief_complaint}</div>
                      <div className="mt-1 flex flex-wrap gap-x-3 text-[11px] text-slate-500">
                        {Object.entries(c.vitals || {}).filter(([k]) => ['hr', 'rr', 'spo2', 'sbp', 'temp'].includes(k)).map(([k, val]) => <span key={k}>{k.toUpperCase()} <b className="text-slate-700">{String(val)}</b></span>)}
                      </div>
                      <div className="mt-1 text-[11px] text-slate-500">Waiting {c.waited_minutes} min (target {c.target_minutes === 0 ? 'immediate' : `${c.target_minutes} min`}) · bed {c.bed || '—'} · doctor {c.doctor || '—'}</div>
                    </div>
                    <div className="flex flex-col justify-center gap-1 p-2">
                      <select className="rounded border border-slate-200 px-1 py-0.5 text-[11px]" value={c.status} onChange={(e) => setStatus(c, e.target.value)}>
                        {['incoming', 'triage', 'awaiting_bed', 'in_treatment', 'admitted', 'discharged'].map((s) => <option key={s} value={s}>{label(s)}</option>)}
                      </select>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}

function numVitals(v: any) {
  const out: any = { consciousness: v.consciousness, on_oxygen: !!v.on_oxygen }
  for (const k of ['hr', 'rr', 'spo2', 'sbp', 'temp']) if (v[k] !== '' && v[k] !== null && v[k] !== undefined) out[k] = Number(v[k])
  return out
}
