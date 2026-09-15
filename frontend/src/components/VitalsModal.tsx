import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Bot, HeartPulse } from 'lucide-react'
import { api } from '../api'
import { cls, newsClass } from '../utils'
import { Button, Field, Modal, useToast } from './ui'

const DEFAULT = { hr: 84, rr: 16, spo2: 97, sbp: 124, dbp: 78, temp: 36.9, consciousness: 'A', on_oxygen: false }
const LABEL: Record<string, string> = { respiration_rate: 'Resp. rate', spo2: 'SpO₂', supplemental_o2: 'O₂', systolic_bp: 'Systolic BP', pulse: 'Pulse', consciousness: 'ACVPU', temperature: 'Temp' }

function num(v: any) {
  const out: any = { consciousness: v.consciousness, on_oxygen: !!v.on_oxygen }
  for (const k of ['hr', 'rr', 'spo2', 'sbp', 'dbp', 'temp']) if (v[k] !== '' && v[k] !== null && v[k] !== undefined) out[k] = Number(v[k])
  return out
}

/** Bedside observation entry with live NEWS2 scoring; the backend applies the escalation policy. */
export default function VitalsModal({ patient, onClose, onSaved }: { patient: { id: number; name: string } | null; onClose: () => void; onSaved?: (r: any) => void }) {
  const toast = useToast()
  const [v, setV] = useState<any>(DEFAULT)
  const [preview, setPreview] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<any>(null)

  useEffect(() => { if (patient) { setResult(null); setV(DEFAULT) } }, [patient])
  useEffect(() => {
    if (!patient) return
    const id = setTimeout(() => api('/api/emergency/triage-preview', { body: { chief_complaint: '', vitals: num(v) } }).then(setPreview).catch(() => {}), 200)
    return () => clearTimeout(id)
  }, [v, patient])

  const save = async () => {
    if (!patient) return
    setBusy(true)
    try {
      const r = await api(`/api/patients/${patient.id}/vitals`, { body: num(v) })
      setResult(r)
      toast({ title: `Observations saved — NEWS2 ${r.news2}`, message: r.escalation ? `Escalation: ${r.escalation.replace(/_/g, ' ')}` : `Next observations ${r.monitoring}`,
        level: r.news2 >= 7 ? 'critical' : r.news2 >= 5 ? 'warning' : 'success' })
      onSaved?.(r)
    } catch (e: any) { toast({ title: 'Could not save', message: e.message, level: 'critical' }) } finally { setBusy(false) }
  }
  const set = (k: string, val: any) => setV({ ...v, [k]: val })

  return (
    <Modal open={!!patient} onClose={onClose} title={<span className="flex items-center gap-2"><HeartPulse className="h-4 w-4 text-rose-600" />Record observations — {patient?.name}</span>} wide
      footer={result ? <Button onClick={onClose}>Done</Button> : <><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={busy} onClick={save}>Save observations</Button></>}>
      {result ? (
        <div className="space-y-3">
          <div className="flex items-center gap-4">
            <div className={cls('flex h-16 w-16 flex-col items-center justify-center rounded-xl', newsClass(result.news2))}><div className="text-[10px] uppercase">NEWS2</div><div className="text-2xl font-bold">{result.news2}</div></div>
            <div>
              <div className="font-semibold capitalize text-slate-800">{result.risk} clinical risk{result.trend !== null && result.trend !== undefined ? ` · trend ${result.trend >= 0 ? '+' : ''}${result.trend}` : ''}</div>
              <div className="text-sm text-slate-600">Next observations: {result.monitoring}</div>
            </div>
          </div>
          {result.escalation && (
            <div className={cls('flex gap-2 rounded-lg p-3 text-sm', result.escalation === 'emergency_response' ? 'bg-red-50 text-red-800' : 'bg-amber-50 text-amber-800')}>
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <div>
                {result.escalation === 'emergency_response' ? 'Emergency response triggered — doctors and nurses alerted.' : result.escalation === 'urgent_review' ? 'Urgent review requested from the ward doctor.' : 'Rising score — observation frequency increased.'}
                {result.request_id && <div className="mt-1"><Link to={`/agents?request=${result.request_id}`} onClick={onClose} className="inline-flex items-center gap-1 font-medium underline"><Bot className="h-3.5 w-3.5" />Agents are preparing an ICU transfer proposal → view</Link></div>}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="grid gap-5 md:grid-cols-[1fr_14rem]">
          <div className="grid grid-cols-3 gap-3">
            <Field label="Heart rate /min"><input className="input" type="number" value={v.hr} onChange={(e) => set('hr', e.target.value)} /></Field>
            <Field label="Resp. rate /min"><input className="input" type="number" value={v.rr} onChange={(e) => set('rr', e.target.value)} /></Field>
            <Field label="SpO₂ %"><input className="input" type="number" value={v.spo2} onChange={(e) => set('spo2', e.target.value)} /></Field>
            <Field label="Systolic BP"><input className="input" type="number" value={v.sbp} onChange={(e) => set('sbp', e.target.value)} /></Field>
            <Field label="Diastolic BP"><input className="input" type="number" value={v.dbp} onChange={(e) => set('dbp', e.target.value)} /></Field>
            <Field label="Temp °C"><input className="input" type="number" step="0.1" value={v.temp} onChange={(e) => set('temp', e.target.value)} /></Field>
            <Field label="ACVPU"><select className="input" value={v.consciousness} onChange={(e) => set('consciousness', e.target.value)}><option value="A">Alert</option><option value="C">New confusion</option><option value="V">Voice</option><option value="P">Pain</option><option value="U">Unresponsive</option></select></Field>
            <label className="col-span-2 flex items-end gap-2 pb-2 text-sm"><input type="checkbox" checked={v.on_oxygen} onChange={(e) => set('on_oxygen', e.target.checked)} />On supplemental oxygen</label>
          </div>
          {preview && (
            <div className="rounded-xl border border-slate-200 p-3">
              <div className="flex items-center gap-3">
                <div className={cls('flex h-12 w-12 items-center justify-center rounded-lg text-xl font-bold', newsClass(preview.news2))}>{preview.news2}</div>
                <div className="text-xs"><div className="font-semibold capitalize text-slate-700">{preview.clinical_risk} risk</div><div className="text-slate-500">live NEWS2</div></div>
              </div>
              <div className="mt-2 space-y-1">
                {Object.entries(preview.news2_components).map(([k, pts]: any) => (
                  <div key={k} className={cls('flex justify-between rounded px-2 py-0.5 text-[11px]', pts >= 3 ? 'bg-red-50 text-red-700' : pts >= 1 ? 'bg-amber-50 text-amber-800' : 'text-slate-500')}><span>{LABEL[k] || k}</span><b>{pts}</b></div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}
