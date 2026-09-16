import { useEffect, useRef, useState } from 'react'
import { Megaphone, Volume2 } from 'lucide-react'
import { api } from '../api'

/** Waiting-room TV board (public, no login): tokens and doctors only — never patient names. */
export default function QueueDisplay() {
  const [data, setData] = useState<any>(null)
  const [voice, setVoice] = useState(false)
  const [clock, setClock] = useState(new Date())
  const lastCall = useRef<string | null>(null)

  useEffect(() => {
    const load = () => api('/api/public/queue').then(setData).catch(() => {})
    load()
    const a = setInterval(load, 5000), b = setInterval(() => setClock(new Date()), 1000)
    return () => { clearInterval(a); clearInterval(b) }
  }, [])

  useEffect(() => {  // announce newly called tokens (English + Hindi)
    const top = data?.announcements?.[0]
    if (!top) return
    const key = `${top.token}@${top.at}`
    if (lastCall.current && lastCall.current !== key && voice && 'speechSynthesis' in window) {
      const spoken = top.token.replace('-', ' ')
      const en = new SpeechSynthesisUtterance(`Token ${spoken}, please proceed to room ${top.room.replace('-', ' ')}.`)
      en.lang = 'en-IN'
      const hi = new SpeechSynthesisUtterance(`टोकन ${spoken}, कृपया कमरा ${top.room.replace('-', ' ')} में जाएँ।`)
      hi.lang = 'hi-IN'
      speechSynthesis.speak(en)
      speechSynthesis.speak(hi)
    }
    lastCall.current = key
  }, [data, voice])

  const top = data?.announcements?.[0]
  return (
    <div className="flex min-h-full flex-col bg-slate-950 p-6 text-white">
      <div className="flex items-center gap-4">
        <img src="/icon.svg" className="h-12 w-12" alt="" />
        <div>
          <div className="text-2xl font-semibold">{data?.hospital || 'Hospital'}</div>
          <div className="text-sm text-teal-300">OPD token display · ओपीडी टोकन</div>
        </div>
        <div className="ml-auto text-right">
          <div className="font-mono text-4xl font-semibold tabular-nums">{clock.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
          <div className="text-xs text-slate-400">{clock.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' })}</div>
        </div>
        {!voice && <button onClick={() => setVoice(true)} className="ml-4 inline-flex items-center gap-2 rounded-lg bg-teal-600 px-3 py-2 text-sm"><Volume2 className="h-4 w-4" />Enable announcements</button>}
      </div>
      <div className="mt-6 grid flex-1 gap-6 xl:grid-cols-[1fr_24rem]">
        <div className="overflow-hidden rounded-2xl ring-1 ring-white/10">
          <table className="w-full">
            <thead className="bg-white/5 text-left text-sm uppercase tracking-wider text-slate-400"><tr><th className="px-5 py-3">Doctor</th><th className="px-5 py-3">Room</th><th className="px-5 py-3">Now serving</th><th className="px-5 py-3">Next</th></tr></thead>
            <tbody className="divide-y divide-white/5">
              {(data?.rows || []).map((r: any) => (
                <tr key={r.doctor}>
                  <td className="px-5 py-3"><div className="text-lg font-medium">{r.doctor}</div><div className="text-xs text-slate-400">{r.department}</div></td>
                  <td className="px-5 py-3 font-mono text-lg text-slate-300">{r.room}</td>
                  <td className="px-5 py-3"><span className="rounded-lg bg-teal-500/20 px-3 py-1 font-mono text-3xl font-bold text-teal-300">{r.now_serving || '—'}</span></td>
                  <td className="px-5 py-3 font-mono text-lg text-slate-300">{r.next.join('  ·  ') || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!data?.rows?.length && <div className="p-10 text-center text-slate-500">No patients waiting right now.</div>}
        </div>
        <div className="flex flex-col gap-4">
          <div className="rounded-2xl bg-gradient-to-br from-teal-600 to-teal-800 p-6 text-center shadow-lg">
            <div className="flex items-center justify-center gap-2 text-sm uppercase tracking-widest text-teal-100"><Megaphone className="h-4 w-4" />Now calling</div>
            <div className="mt-3 font-mono text-7xl font-bold">{top?.token || '—'}</div>
            <div className="mt-2 text-xl">{top ? `Room ${top.room}` : ''}</div>
            <div className="text-sm text-teal-100">{top?.doctor}</div>
          </div>
          <div className="rounded-2xl bg-white/5 p-5 text-center ring-1 ring-white/10">
            <div className="text-5xl font-semibold tabular-nums">{data?.total_waiting ?? '—'}</div>
            <div className="text-sm text-slate-400">patients waiting</div>
          </div>
          <div className="mt-auto rounded-2xl bg-white/5 p-4 text-sm text-slate-300 ring-1 ring-white/10">
            Have an appointment? Check in at the self-service kiosk with your MRN — no queue at the desk.<br />
            <span className="text-slate-400">अपॉइंटमेंट है? कियोस्क पर अपने MRN से चेक-इन करें।</span>
          </div>
        </div>
      </div>
    </div>
  )
}
