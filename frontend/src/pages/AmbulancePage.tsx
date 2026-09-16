import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { Ambulance, ChevronsRight, Dices, MapPin, PhoneCall, Radio, Siren, XCircle } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import { Badge, Button, Card, Empty, Field, Spinner, Stat, StatusBadge, useToast } from '../components/ui'
import { useApi, useLive } from '../live'
import { cls, label, TRIAGE_COLORS } from '../utils'

const STATUS_COLOR: Record<string, string> = {
  available: '#059669', to_scene: '#ea580c', on_scene: '#dc2626', to_hospital: '#2563eb', returning: '#0284c7', at_hospital: '#2563eb', maintenance: '#64748b',
}
const STAGES = [{ key: 'to_scene', label: 'Unit en route' }, { key: 'on_scene', label: 'On scene' }, { key: 'to_hospital', label: 'Transporting · ED pre-alerted' }, { key: 'arrived', label: 'Arrived' }]

export default function AmbulancePage() {
  const toast = useToast()
  const fleet = useApi<any>('/api/ambulance/fleet', ['ambulance', 'emergency'])
  const [live, setLive] = useState<any>(null)
  const [form, setForm] = useState({ locality: 'Sitabuldi', complaint: '', caller: '' })
  const [busy, setBusy] = useState<string | null>(null)
  const [lastReq, setLastReq] = useState<number | null>(null)
  useLive('fleet', (d: any) => setLive(d))
  useEffect(() => { setLive(null) }, [fleet.data])
  const data = fleet.data
  const ambulances = live?.ambulances || data?.ambulances || []
  const dispatches = live?.dispatches || data?.dispatches || []

  const call = async (random = false) => {
    setBusy(random ? 'random' : 'call')
    try {
      const r = await api('/api/ambulance/calls', { body: { ...form, random_call: random } })
      setLastReq(r.request_id)
      toast({ title: `108 call registered — ${r.locality}`, message: `${r.complaint}. The Ambulance Dispatch Agent is selecting the nearest capable unit.`, level: 'info' })
      setForm({ ...form, complaint: '' })
      setTimeout(fleet.reload, 1500)
    } catch (e: any) { toast({ title: 'Call failed', message: e.message, level: 'critical' }) } finally { setBusy(null) }
  }
  const act = async (d: any, action: 'advance' | 'cancel') => {
    try { await api(`/api/ambulance/dispatches/${d.id}/${action}`, { method: 'POST' }); fleet.reload() }
    catch (e: any) { toast({ title: 'Failed', message: e.message, level: 'critical' }) }
  }

  if (fleet.loading && !data) return <Spinner />
  if (!data) return <Empty title="Fleet unavailable" />
  const st = data.stats
  return (
    <div>
      <PageHeader title="Ambulance & pre-hospital coordination" icon={<Ambulance className="h-5 w-5" />}
        subtitle="108-style dispatch: severity pre-triage → nearest capable unit → live tracking → ED pre-alert so the bay and team are ready before arrival" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Units available" value={`${ambulances.filter((a: any) => a.status === 'available').length}/${ambulances.length}`} sub="ALS + BLS fleet" icon={<Ambulance className="h-5 w-5" />} tone="emerald" />
        <Stat label="Active calls" value={dispatches.length} sub="en route / on scene / transporting" icon={<Siren className="h-5 w-5" />} tone="red" />
        <Stat label="Completed runs" value={st.completed} sub={st.avg_response_min ? `avg response ${st.avg_response_min} min` : 'no runs yet'} icon={<ChevronsRight className="h-5 w-5" />} tone="blue" />
        <Stat label="ED pre-alerts sent" value={st.pre_alerted} sub="bay held before arrival" icon={<Radio className="h-5 w-5" />} tone="violet" />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_24rem]">
        <Card bodyClass="p-0" title="Live fleet map" subtitle="Nagpur (demo geography) · positions stream over WebSocket" icon={<MapPin className="h-4 w-4" />}>
          <FleetMap hospital={data.hospital} localities={data.localities} ambulances={ambulances} dispatches={dispatches} onPick={(n) => setForm((f) => ({ ...f, locality: n }))} />
        </Card>
        <div className="space-y-4">
          <Card title="New 108 call" icon={<PhoneCall className="h-4 w-4" />}>
            <div className="space-y-2.5">
              <Field label="Pickup locality (or click a grey dot on the map)"><select className="input" value={form.locality} onChange={(e) => setForm({ ...form, locality: e.target.value })}>{data.localities.map((l: any) => <option key={l.name}>{l.name}</option>)}</select></Field>
              <Field label="Complaint"><input className="input" value={form.complaint} onChange={(e) => setForm({ ...form, complaint: e.target.value })} placeholder="e.g. elderly man collapsed with chest pain" /></Field>
              <div className="flex flex-wrap gap-1">{data.scenarios.slice(0, 5).map((s: string) => <button key={s} onClick={() => setForm({ ...form, complaint: s })} className="rounded-full border border-slate-200 px-2 py-0.5 text-[10px] text-slate-600 hover:border-fuchsia-300 hover:bg-fuchsia-50">{s.split(' — ')[0].slice(0, 34)}</button>)}</div>
              <div className="flex gap-2">
                <Button className="flex-1" variant="danger" loading={busy === 'call'} disabled={form.complaint.length < 3} onClick={() => call(false)} icon={<Siren className="h-4 w-4" />}>Dispatch</Button>
                <Button variant="secondary" loading={busy === 'random'} onClick={() => call(true)} icon={<Dices className="h-4 w-4" />}>Random call</Button>
              </div>
              {lastReq && <Link to={`/agents?request=${lastReq}`} className="block text-xs text-teal-700 hover:underline">View the agents' decision trace (request #{lastReq}) →</Link>}
            </div>
          </Card>
          <Card title="Active calls" subtitle="Advance stage = manual demo control (the tracker also moves units automatically)" bodyClass="space-y-3 p-3">
            {!dispatches.length ? <Empty title="No active calls" hint="Register a call or click Random call" /> : dispatches.map((d: any) => <DispatchCard key={d.id} d={d} onAct={act} />)}
          </Card>
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="Fleet" bodyClass="p-0">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500"><tr>{['Unit', 'Type', 'Status', 'Base', 'Crew'].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-slate-100">
              {ambulances.map((a: any) => (
                <tr key={a.id}><td className="px-3 py-2 font-mono text-xs font-semibold">{a.code}</td><td className="px-3 py-2"><Badge tone={a.vehicle_type === 'ALS' ? 'violet' : 'sky'}>{a.vehicle_type}</Badge></td>
                  <td className="px-3 py-2"><span className="inline-flex items-center gap-1.5 text-xs"><span className="h-2 w-2 rounded-full" style={{ background: STATUS_COLOR[a.status] }} />{label(a.status)}</span></td>
                  <td className="px-3 py-2 text-xs text-slate-600">{a.base}</td><td className="px-3 py-2 text-[11px] text-slate-500">{a.crew.join(', ')}</td></tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Recent runs" bodyClass="p-0">
          {!data.recent.length ? <Empty title="No completed runs yet" /> : (
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs text-slate-500"><tr>{['Unit', 'From', 'Complaint', 'Severity', 'Outcome'].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr></thead>
              <tbody className="divide-y divide-slate-100">
                {data.recent.map((d: any) => <tr key={d.id}><td className="px-3 py-2 font-mono text-xs">{d.ambulance}</td><td className="px-3 py-2 text-xs">{d.locality}</td><td className="px-3 py-2 text-xs text-slate-600">{d.complaint}</td><td className="px-3 py-2"><Badge tone={d.severity <= 2 ? 'red' : 'amber'}>L{d.severity}</Badge></td><td className="px-3 py-2"><StatusBadge status={d.status} /></td></tr>)}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </div>
  )
}

function DispatchCard({ d, onAct }: { d: any; onAct: (d: any, a: 'advance' | 'cancel') => void }) {
  const idx = STAGES.findIndex((s) => s.key === d.status)
  const t = TRIAGE_COLORS[d.severity]
  return (
    <div className="rounded-xl border border-slate-200 p-3">
      <div className="flex items-center gap-2">
        <div className={cls('flex h-9 w-9 items-center justify-center rounded-lg text-xs font-bold text-white', t?.bg)}>L{d.severity}</div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-slate-800">{d.ambulance} ({d.vehicle_type}) → {d.locality}</div>
          <div className="truncate text-[11px] text-slate-500">{d.complaint}</div>
        </div>
        <div className="text-right"><div className="text-lg font-semibold tabular-nums text-slate-900">{Math.ceil(d.minutes_to_hospital)}′</div><div className="text-[10px] text-slate-400">to hospital</div></div>
      </div>
      <div className="mt-2 grid grid-cols-4 gap-1">
        {STAGES.map((s, i) => (
          <div key={s.key}>
            <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
              <div className={cls('h-full rounded-full', i < idx ? 'bg-teal-500' : i === idx ? 'bg-fuchsia-500' : '')} style={{ width: i < idx ? '100%' : i === idx ? `${Math.max(8, d.progress * 100)}%` : '0%' }} />
            </div>
            <div className={cls('mt-1 text-[9px] leading-tight', i <= idx ? 'font-medium text-slate-700' : 'text-slate-400')}>{s.label}</div>
          </div>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500">
        {Object.entries(d.vitals || {}).filter(([k]) => ['hr', 'spo2', 'sbp', 'rr'].includes(k)).map(([k, v]) => <span key={k} className="rounded bg-slate-50 px-1.5 py-0.5">{k.toUpperCase()} <b className="text-slate-700">{String(v)}</b></span>)}
        {d.request_id && <Link to={`/agents?request=${d.request_id}`} className="rounded bg-violet-50 px-1.5 py-0.5 font-medium text-violet-700 hover:underline">ED pre-alert · request #{d.request_id}</Link>}
      </div>
      <div className="mt-2 flex gap-2">
        <Button size="sm" variant="secondary" onClick={() => onAct(d, 'advance')} icon={<ChevronsRight className="h-3.5 w-3.5" />}>Advance stage</Button>
        <Button size="sm" variant="ghost" onClick={() => onAct(d, 'cancel')} icon={<XCircle className="h-3.5 w-3.5" />}>Cancel</Button>
      </div>
    </div>
  )
}

function FleetMap({ hospital, localities, ambulances, dispatches, onPick }: { hospital: any; localities: any[]; ambulances: any[]; dispatches: any[]; onPick: (n: string) => void }) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const layer = useRef<L.LayerGroup | null>(null)
  const [ready, setReady] = useState(0)  // bumps when the map (and its marker layer) is (re)created → forces a redraw
  const pick = useRef(onPick)
  pick.current = onPick

  useEffect(() => {  // create the map once; data refreshes only redraw markers
    if (!el.current || map.current) return
    const m = L.map(el.current, { zoomControl: true, attributionControl: true }).setView([hospital.lat, hospital.lng], 12)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, attribution: '&copy; OpenStreetMap contributors' }).addTo(m)
    L.marker([hospital.lat, hospital.lng], { icon: L.divIcon({ className: '', html: '<div class="map-hospital">🏥</div>', iconSize: [34, 34], iconAnchor: [17, 17] }) })
      .bindTooltip(hospital.name).addTo(m)
    for (const l of localities) {
      L.circleMarker([l.lat, l.lng], { radius: 5, color: '#64748b', weight: 1, fillColor: '#cbd5e1', fillOpacity: 0.9 })
        .bindTooltip(l.name).on('click', () => pick.current(l.name)).addTo(m)
    }
    layer.current = L.layerGroup().addTo(m)
    map.current = m
    setReady((r) => r + 1)
    return () => { m.remove(); map.current = null; layer.current = null }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const key = useMemo(() => JSON.stringify([ambulances.map((a) => [a.id, a.lat, a.lng, a.status]), dispatches.map((d) => [d.id, d.status])]), [ambulances, dispatches])
  useEffect(() => {
    const g = layer.current
    if (!g) return
    g.clearLayers()
    for (const d of dispatches) {
      const amb = ambulances.find((a) => a.id === d.ambulance_id)
      L.marker([d.pickup.lat, d.pickup.lng], { icon: L.divIcon({ className: '', html: `<div class="map-pickup">L${d.severity}</div>`, iconSize: [26, 26], iconAnchor: [13, 26] }) })
        .bindTooltip(`${d.locality}: ${d.complaint}`).addTo(g)
      if (amb) {
        const pts: [number, number][] = d.status === 'to_scene' ? [[amb.lat, amb.lng], [d.pickup.lat, d.pickup.lng], [hospital.lat, hospital.lng]] : [[amb.lat, amb.lng], [hospital.lat, hospital.lng]]
        L.polyline(pts, { color: STATUS_COLOR[amb.status] || '#c026d3', weight: 3, dashArray: '6 6', opacity: 0.8 }).addTo(g)
      }
    }
    for (const a of ambulances) {
      L.marker([a.lat, a.lng], { zIndexOffset: 1000, icon: L.divIcon({ className: '', html: `<div class="map-amb" style="background:${STATUS_COLOR[a.status] || '#475569'}">🚑 ${a.code.replace('AMB-', '')}</div>`, iconSize: [52, 22], iconAnchor: [26, 11] }) })
        .bindTooltip(`${a.code} (${a.vehicle_type}) — ${a.status.replace(/_/g, ' ')}`).addTo(g)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, ready])

  return <div ref={el} className="h-[520px] w-full rounded-b-xl" />
}
