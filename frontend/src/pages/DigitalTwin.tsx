import { useEffect, useState } from 'react'
import { Area, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Boxes, FlaskConical, Lightbulb, Play, RotateCcw, Sparkles } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import { Badge, Button, Card, Empty, Spinner, useToast } from '../components/ui'
import { useApi } from '../live'
import { cls } from '../utils'

const DEFAULT: any = {
  horizon_hours: 72, surge_pct: 50, surge_start_hour: 0, surge_duration_hours: 0, mass_casualty_patients: 0, mass_casualty_hour: 6,
  closed_critical_beds: 0, closed_general_beds: 0, staff_absent_pct: 0, extra_critical_beds: 0, extra_general_beds: 0,
  los_reduction_pct: 0, discharge_lounge: false, fast_cleaning: false, defer_electives: false, replications: 30,
}
const KPIS: [string, string, 'pct' | 'num'][] = [
  ['boarding_patient_hours', 'ED boarding (patient-hours)', 'num'], ['max_boarding', 'Max patients boarding', 'num'],
  ['p90_boarding_hours', 'P90 wait for a bed (h)', 'num'], ['peak_critical_occupancy', 'Peak critical-care occupancy', 'pct'],
  ['peak_general_occupancy', 'Peak ward occupancy', 'pct'], ['hours_critical_full', 'Hours critical care full', 'num'],
  ['ed_saturated_hours', 'Hours ED saturated', 'num'], ['mean_ed_wait_minutes', 'Mean wait for ED bay (min)', 'num'],
  ['electives_cancelled', 'Electives cancelled', 'num'], ['ed_arrivals', 'ED arrivals', 'num'], ['admissions', 'Admissions', 'num'],
]
const LEVER_KEYS = new Set(['extra_critical_beds', 'extra_general_beds', 'discharge_lounge', 'fast_cleaning', 'los_reduction_pct', 'defer_electives'])

export default function DigitalTwin() {
  const toast = useToast()
  const presets = useApi<any>('/api/twin/presets')
  const [sc, setSc] = useState<any>(DEFAULT)
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState(false)

  const run = async (scenario = sc) => {
    setBusy(true)
    try { setRes(await api('/api/twin/simulate', { body: scenario })) }
    catch (e: any) { toast({ title: 'Simulation failed', message: e.message, level: 'critical' }) } finally { setBusy(false) }
  }
  useEffect(() => { run(DEFAULT) }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const applyPreset = (p: any) => { const next = { ...DEFAULT, surge_pct: 0, ...p }; delete next.label; setSc(next); run(next) }
  const applyLever = (r: any) => { const next = { ...sc, [r.lever]: r.value }; setSc(next); run(next) }
  const set = (k: string, v: any) => setSc({ ...sc, [k]: v })

  return (
    <div>
      <PageHeader title="Hospital digital twin" icon={<Boxes className="h-5 w-5" />}
        subtitle="Monte-Carlo discrete-event simulation that starts from the live hospital state — test surges, closures and staff shortages before they happen, and get prescriptive recommendations" />
      <div className="grid gap-4 xl:grid-cols-[22rem_1fr]">
        <div className="space-y-4">
          <Card title="Scenario presets" icon={<FlaskConical className="h-4 w-4" />}>
            <div className="flex flex-col gap-1.5">
              {Object.entries(presets.data || {}).map(([k, p]: any) => (
                <button key={k} onClick={() => applyPreset(p)} className="rounded-lg border border-slate-200 px-3 py-2 text-left text-xs text-slate-700 transition hover:border-teal-400 hover:bg-teal-50">{p.label}</button>
              ))}
            </div>
          </Card>
          <Card title="What-if parameters" actions={<button onClick={() => setSc(DEFAULT)} className="text-xs text-slate-500 hover:text-teal-700"><RotateCcw className="inline h-3 w-3" /> reset</button>}>
            <Slider label="Horizon" unit="h" min={24} max={168} step={12} value={sc.horizon_hours} onChange={(v) => set('horizon_hours', v)} />
            <Slider label="ED arrival surge" unit="%" min={0} max={150} step={5} value={sc.surge_pct} onChange={(v) => set('surge_pct', v)} />
            <Slider label="Mass-casualty patients" unit="" min={0} max={40} step={1} value={sc.mass_casualty_patients} onChange={(v) => set('mass_casualty_patients', v)} />
            {sc.mass_casualty_patients > 0 && <Slider label="…arriving at hour" unit="h" min={0} max={Math.min(48, sc.horizon_hours - 1)} step={1} value={sc.mass_casualty_hour} onChange={(v) => set('mass_casualty_hour', v)} />}
            <Slider label="Critical-care beds closed" unit="" min={0} max={10} step={1} value={sc.closed_critical_beds} onChange={(v) => set('closed_critical_beds', v)} />
            <Slider label="Ward beds closed" unit="" min={0} max={30} step={1} value={sc.closed_general_beds} onChange={(v) => set('closed_general_beds', v)} />
            <Slider label="Nursing staff absent" unit="%" min={0} max={50} step={5} value={sc.staff_absent_pct} onChange={(v) => set('staff_absent_pct', v)} />
            <div className="mb-2 mt-4 text-[11px] font-semibold uppercase tracking-wide text-teal-700">Interventions</div>
            <Slider label="Surge critical-care beds" unit="" min={0} max={10} step={1} value={sc.extra_critical_beds} onChange={(v) => set('extra_critical_beds', v)} />
            <Slider label="Surge ward beds" unit="" min={0} max={30} step={2} value={sc.extra_general_beds} onChange={(v) => set('extra_general_beds', v)} />
            <Slider label="Length-of-stay reduction" unit="%" min={0} max={30} step={5} value={sc.los_reduction_pct} onChange={(v) => set('los_reduction_pct', v)} />
            {([['discharge_lounge', 'Discharge lounge'], ['fast_cleaning', 'Rapid bed turnaround'], ['defer_electives', 'Defer elective admissions']] as const).map(([k, l]) => (
              <label key={k} className="mt-1.5 flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={sc[k]} onChange={(e) => set(k, e.target.checked)} />{l}</label>
            ))}
            <Slider label="Monte-Carlo replications" unit="" min={10} max={60} step={5} value={sc.replications} onChange={(v) => set('replications', v)} />
            <Button className="mt-3 w-full" loading={busy} onClick={() => run()} icon={<Play className="h-4 w-4" />}>Run simulation</Button>
          </Card>
        </div>

        <div className="min-w-0 space-y-4">
          {!res ? <Spinner label="Simulating the next hours…" /> : (
            <>
              <Card>
                <div className="flex items-start gap-3">
                  <div className="rounded-xl bg-teal-50 p-2 text-teal-700"><Sparkles className="h-5 w-5" /></div>
                  <div className="min-w-0">
                    <div className="text-sm leading-relaxed text-slate-800">{res.headline}</div>
                    <div className="mt-1.5 flex flex-wrap gap-1.5 text-[11px]">
                      <Badge tone="slate">{res.replications} replications × 2</Badge><Badge tone="slate">start state: {res.state.occupied.critical}/{res.state.capacity.critical} critical, {res.state.occupied.general}/{res.state.capacity.general} ward beds occupied</Badge>
                      <Badge tone="slate">{res.state.boarding.critical + res.state.boarding.general} boarding in ED</Badge><Badge tone="slate">{res.state.ed_arrivals_per_day} ED arrivals/day</Badge>
                      {busy && <Badge tone="blue">re-running…</Badge>}
                    </div>
                  </div>
                </div>
              </Card>
              <div className="grid gap-4 2xl:grid-cols-2">
                <Card title="Critical-care occupancy (% of staffed beds)" subtitle="Baseline vs scenario · shaded band = P10–P90 across replications"><Occ data={res.timeline} k="critical" /></Card>
                <Card title="Ward occupancy (% of staffed beds)" subtitle="Baseline vs scenario · shaded band = P10–P90"><Occ data={res.timeline} k="general" /></Card>
              </div>
              <div className="grid gap-4 2xl:grid-cols-[1fr_24rem]">
                <Card title="ED boarding (admitted patients waiting for a bed)" subtitle="Mean patients boarding, with P10–P90 band">
                  <div className="h-60">
                    <ResponsiveContainer>
                      <ComposedChart data={res.timeline} margin={{ left: -15, right: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                        <XAxis dataKey="hour" tick={{ fontSize: 10 }} tickFormatter={(h) => `${h}h`} interval={11} />
                        <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                        <Tooltip labelFormatter={(h) => `+${h} h`} />
                        <Legend />
                        <Area dataKey="boarding_scn_band" name="Scenario P10–P90" stroke="none" fill="#f97316" fillOpacity={0.15} />
                        <Line dataKey="boarding_base" name="Baseline" stroke="#64748b" dot={false} strokeWidth={2} />
                        <Line dataKey="boarding_scn" name="Scenario" stroke="#ea580c" dot={false} strokeWidth={2.5} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                </Card>
                <Card title="Prescriptive recommendations" subtitle="Each lever tested in the twin — click to apply and re-run" icon={<Lightbulb className="h-4 w-4" />}>
                  <div className="space-y-2">
                    {res.recommendations.map((r: any, i: number) => (
                      <div key={i} className="rounded-lg border border-slate-100 p-2.5">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-medium text-slate-800">{r.title}</span>
                          {r.impact > 0 && <Badge tone="green">−{Math.round(r.impact * 100)}% pressure</Badge>}
                        </div>
                        <div className="mt-0.5 text-xs text-slate-500">{r.detail}</div>
                        {r.impact > 0 && <div className="mt-1.5 h-1.5 rounded-full bg-slate-100"><div className="h-full rounded-full bg-emerald-500" style={{ width: `${Math.min(100, r.impact * 100)}%` }} /></div>}
                        {r.lever && LEVER_KEYS.has(r.lever) && <button onClick={() => applyLever(r)} className="mt-1.5 text-[11px] font-medium text-teal-700 hover:underline">Apply in twin & re-run →</button>}
                      </div>
                    ))}
                  </div>
                </Card>
              </div>
              <Card title="Scenario vs baseline" subtitle="Mean across replications (P10–P90 for the scenario)" bodyClass="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50 text-left text-xs text-slate-500"><tr><th className="px-4 py-2">Indicator</th><th className="px-4 py-2 text-right">Baseline</th><th className="px-4 py-2 text-right">Scenario</th><th className="px-4 py-2 text-right">P10–P90</th><th className="px-4 py-2 text-right">Change</th></tr></thead>
                    <tbody className="divide-y divide-slate-100">
                      {KPIS.map(([k, l, kind]) => {
                        const b = res.kpis.baseline[k], s = res.kpis.scenario[k]
                        const fmt = (v: number) => (kind === 'pct' ? `${Math.round(v * 100)}%` : v.toLocaleString('en-IN', { maximumFractionDigits: 1 }))
                        const d = s.mean - b.mean
                        const worse = !['ed_arrivals', 'admissions'].includes(k) && d > 0.0001
                        return (
                          <tr key={k}><td className="px-4 py-2 text-slate-700">{l}</td><td className="px-4 py-2 text-right tabular-nums text-slate-500">{fmt(b.mean)}</td>
                            <td className="px-4 py-2 text-right font-medium tabular-nums">{fmt(s.mean)}</td><td className="px-4 py-2 text-right text-xs tabular-nums text-slate-400">{fmt(s.p10)}–{fmt(s.p90)}</td>
                            <td className={cls('px-4 py-2 text-right text-xs font-medium tabular-nums', Math.abs(d) < 0.001 ? 'text-slate-400' : worse ? 'text-red-600' : 'text-emerald-600')}>{d >= 0 ? '+' : ''}{fmt(d)}</td></tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </Card>
              <Card title="Model assumptions">
                <ul className="list-disc space-y-1 pl-5 text-xs text-slate-600">{res.assumptions.map((a: string) => <li key={a}>{a}</li>)}</ul>
              </Card>
            </>
          )}
          {!res && !busy && <Empty title="Run a scenario" />}
        </div>
      </div>
    </div>
  )
}

function Occ({ data, k }: { data: any[]; k: 'critical' | 'general' }) {
  return (
    <div className="h-56">
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ left: -15, right: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="hour" tick={{ fontSize: 10 }} tickFormatter={(h) => `${h}h`} interval={11} />
          <YAxis tick={{ fontSize: 10 }} domain={[40, 105]} tickFormatter={(v) => `${v}%`} />
          <Tooltip labelFormatter={(h) => `+${h} h`} formatter={(v: any) => (Array.isArray(v) ? `${v[0]}–${v[1]}%` : `${v}%`)} />
          <ReferenceLine y={100} stroke="#dc2626" strokeDasharray="4 4" />
          <ReferenceLine y={85} stroke="#f59e0b" strokeDasharray="2 4" />
          <Area dataKey={`${k}_scn_band`} name="Scenario P10–P90" stroke="none" fill="#0d9488" fillOpacity={0.15} />
          <Line dataKey={`${k}_base`} name="Baseline" stroke="#64748b" dot={false} strokeWidth={2} />
          <Line dataKey={`${k}_scn`} name="Scenario" stroke="#0d9488" dot={false} strokeWidth={2.5} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

function Slider({ label, unit, min, max, step, value, onChange }: { label: string; unit: string; min: number; max: number; step: number; value: number; onChange: (v: number) => void }) {
  return (
    <label className="mt-2 block">
      <div className="flex justify-between text-xs"><span className="text-slate-600">{label}</span><span className="font-medium tabular-nums text-slate-800">{value}{unit}</span></div>
      <input type="range" className="w-full accent-teal-600" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </label>
  )
}
