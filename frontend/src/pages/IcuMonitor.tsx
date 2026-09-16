import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BellOff, HeartPulse, MonitorDot, Volume2, VolumeX } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import { Spinner } from '../components/ui'
import { useApi, useLive } from '../live'
import { cls } from '../utils'

/** Synthetic ECG (PQRST) and plethysmograph shapes for a phase in [0, 1). */
function ecg(p: number) {
  const g = (c: number, w: number, a: number) => a * Math.exp(-((p - c) ** 2) / (2 * w * w))
  return g(0.18, 0.025, 0.12) - g(0.36, 0.008, 0.12) + g(0.4, 0.012, 1.0) - g(0.44, 0.01, 0.25) + g(0.66, 0.05, 0.28)
}
function pleth(p: number) {
  return 0.85 * Math.exp(-((p - 0.25) ** 2) / 0.012) + 0.35 * Math.exp(-((p - 0.55) ** 2) / 0.02)
}

function Trace({ rate, color, kind }: { rate: number; color: string; kind: 'ecg' | 'pleth' }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const rateRef = useRef(rate)
  rateRef.current = rate
  useEffect(() => {
    const c = ref.current
    if (!c) return
    const ctx = c.getContext('2d')!
    let raf = 0, x = 0, phase = 0, last = performance.now(), prevY: number | null = null
    const resize = () => { c.width = c.clientWidth * devicePixelRatio; c.height = c.clientHeight * devicePixelRatio }
    resize()
    const draw = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      const W = c.width, H = c.height, speed = 70 * devicePixelRatio
      phase = (phase + dt * (Math.max(rateRef.current, 20) / 60)) % 1
      const nx = x + speed * dt
      const v = kind === 'ecg' ? ecg(phase) : pleth(phase)
      const y = H * (kind === 'ecg' ? 0.62 - v * 0.5 : 0.8 - v * 0.65)
      ctx.clearRect(nx, 0, 14 * devicePixelRatio, H)
      ctx.strokeStyle = color
      ctx.lineWidth = 1.6 * devicePixelRatio
      ctx.beginPath()
      ctx.moveTo(x, prevY ?? y)
      ctx.lineTo(nx, y)
      ctx.stroke()
      prevY = y
      x = nx
      if (x > W) { x = 0; prevY = null }
      raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(raf)
  }, [color, kind])
  return <canvas ref={ref} className="h-full w-full" />
}

export default function IcuMonitor() {
  const nav = useNavigate()
  const initial = useApi<any>('/api/telemetry')
  const [data, setData] = useState<any>(null)
  const [sound, setSound] = useState(false)
  const audio = useRef<AudioContext | null>(null)
  const alarmed = useRef(new Set<string>())
  useLive('telemetry', (d: any) => setData(d))
  const t = data || initial.data

  useEffect(() => {  // audible alert for newly raised critical alarms
    if (!t || !sound) return
    const now = new Set<string>()
    for (const b of t.beds) for (const a of b.alarms) if (a.level === 'critical' && !b.acked) now.add(`${b.patient_id}:${a.param}`)
    const fresh = [...now].some((k) => !alarmed.current.has(k))
    alarmed.current = now
    if (fresh) {
      audio.current ||= new AudioContext()
      const ctx = audio.current
      for (let i = 0; i < 3; i++) {
        const o = ctx.createOscillator(), g = ctx.createGain()
        o.frequency.value = 880
        g.gain.value = 0.08
        o.connect(g).connect(ctx.destination)
        o.start(ctx.currentTime + i * 0.25)
        o.stop(ctx.currentTime + i * 0.25 + 0.15)
      }
    }
  }, [t, sound])

  if (!t) return <Spinner label="Connecting to bedside monitors…" />
  const alarms = t.beds.reduce((n: number, b: any) => n + b.alarms.length, 0)
  const stats = t.stats || {}
  const ack = async (pid: number) => { await api(`/api/telemetry/${pid}/ack`, { method: 'POST' }) }

  return (
    <div>
      <PageHeader title="ICU central monitor" icon={<MonitorDot className="h-5 w-5" />}
        subtitle="Live bedside telemetry for ICU, CCU and HDU · smart alarms need 3 consecutive out-of-range readings, which filters transient artefacts"
        actions={<button onClick={() => setSound((s) => !s)} className={cls('inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium ring-1 ring-inset', sound ? 'bg-red-50 text-red-700 ring-red-200' : 'bg-white text-slate-600 ring-slate-200')}>
          {sound ? <Volume2 className="h-3.5 w-3.5" /> : <VolumeX className="h-3.5 w-3.5" />}{sound ? 'Alarm sound on' : 'Alarm sound off'}</button>} />
      <div className="rounded-2xl bg-slate-950 p-3 text-slate-200 shadow-inner">
        <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-1 px-1 text-xs">
          <span className="flex items-center gap-1.5"><span className="blink h-2 w-2 rounded-full bg-emerald-400" />LIVE · {t.beds.length} beds</span>
          <span className={alarms ? 'font-semibold text-red-400' : 'text-slate-400'}>{alarms} active alarm{alarms === 1 ? '' : 's'}</span>
          <span className="text-slate-400">readings {stats.readings?.toLocaleString?.() ?? 0}</span>
          <span className="text-slate-400">alarms raised {stats.alarms ?? 0}</span>
          <span className="text-emerald-400">transients suppressed {stats.suppressed ?? 0}{stats.alarms + stats.suppressed > 0 ? ` (${Math.round((100 * stats.suppressed) / (stats.alarms + stats.suppressed))}% fewer alarms)` : ''}</span>
          <span className="ml-auto text-slate-500">{new Date(t.ts).toLocaleTimeString()}</span>
        </div>
        <div className="grid gap-2.5 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {t.beds.map((b: any) => {
            const crit = b.alarms.some((a: any) => a.level === 'critical')
            const warn = b.alarms.length > 0
            return (
              <div key={b.patient_id} className={cls('overflow-hidden rounded-xl border bg-black/60', crit && !b.acked ? 'alarm-flash border-red-500' : warn ? 'border-amber-500/70' : 'border-slate-800')}>
                <button onClick={() => nav(`/patients/${b.patient_id}`)} className="flex w-full items-center gap-2 border-b border-slate-800 px-2.5 py-1.5 text-left hover:bg-white/5">
                  <span className="font-mono text-xs font-bold text-white">{b.bed}</span>
                  <span className="truncate text-xs text-slate-300">{b.name} · {b.age}{b.gender[0]}</span>
                  <span className={cls('ml-auto rounded px-1.5 text-[10px] font-bold', b.news2 >= 7 ? 'bg-red-600 text-white' : b.news2 >= 5 ? 'bg-orange-500 text-white' : 'bg-slate-800 text-slate-300')}>NEWS2 {b.news2}</span>
                </button>
                <div className="grid grid-cols-[1fr_5.5rem]">
                  <div className="space-y-0.5 p-1">
                    <div className="h-14"><Trace rate={b.hr} color="#22c55e" kind="ecg" /></div>
                    <div className="h-9"><Trace rate={b.hr} color="#22d3ee" kind="pleth" /></div>
                  </div>
                  <div className="flex flex-col justify-center gap-0.5 border-l border-slate-800 px-2 py-1 text-right">
                    <Vital label="HR" value={b.hr} unit="" cls="text-green-400" big bad={b.alarms.some((a: any) => a.param === 'hr')} />
                    <Vital label="SpO₂" value={b.spo2} unit="%" cls="text-cyan-300" big bad={b.alarms.some((a: any) => a.param === 'spo2')} />
                    <Vital label="NIBP" value={`${b.sbp}/${b.dbp}`} unit="" cls="text-slate-100" bad={b.alarms.some((a: any) => a.param === 'sbp')} />
                    <div className="flex justify-end gap-2 text-[11px]"><span className={cls('text-yellow-300', b.alarms.some((a: any) => a.param === 'rr') && 'text-red-400')}>RR {b.rr}</span><span className="text-orange-300">{b.temp}°</span></div>
                  </div>
                </div>
                {warn && (
                  <div className={cls('flex items-center gap-2 px-2.5 py-1 text-[11px] font-semibold', crit ? 'bg-red-600/90 text-white' : 'bg-amber-500/90 text-black')}>
                    <HeartPulse className="h-3 w-3" /><span className="truncate">{b.alarms.map((a: any) => a.message).join(' · ')}</span>
                    {!b.acked ? <button onClick={() => ack(b.patient_id)} className="ml-auto inline-flex items-center gap-1 rounded bg-black/30 px-1.5 py-0.5 text-[10px]"><BellOff className="h-3 w-3" />Ack</button> : <span className="ml-auto text-[10px] opacity-80">acknowledged</span>}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
      <p className="mt-2 text-xs text-slate-400">Simulated telemetry anchored on each patient's last charted observations (demo). Click a tile to open the patient's record.</p>
    </div>
  )
}

function Vital({ label, value, unit, cls: c, big, bad }: { label: string; value: any; unit: string; cls: string; big?: boolean; bad?: boolean }) {
  return (
    <div className="leading-none">
      <div className="text-[9px] uppercase text-slate-500">{label}</div>
      <div className={cls('font-mono font-bold tabular-nums', big ? 'text-2xl' : 'text-sm', bad ? 'text-red-400' : c)}>{value}<span className="text-[10px]">{unit}</span></div>
    </div>
  )
}
