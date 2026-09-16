import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Bot, Languages, Loader2, Mic, MicOff, Send, Sparkles, X } from 'lucide-react'
import { api } from '../api'
import ApprovalCard from './ApprovalCard'
import { Badge } from './ui'
import { cls, label } from '../utils'

const SpeechRec: any = typeof window !== 'undefined' ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition : null

interface Turn {
  id: number
  role: 'user' | 'assistant'
  text?: string
  understood?: string | null
  assumed?: string | null
  requestId?: number
  status?: any
  options?: { patient_id: number; label: string; status: string }[]
  pendingText?: string
}

/** Floating conversational copilot: Hinglish-aware, remembers the patient under discussion, asks when unsure. */
export default function Copilot() {
  const location = useLocation()
  const [open, setOpen] = useState(false)
  const [turns, setTurns] = useState<Turn[]>([])
  const [text, setText] = useState('')
  const [cid, setCid] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [listening, setListening] = useState(false)
  const [lang, setLang] = useState<'en-IN' | 'hi-IN'>('en-IN')
  const recRef = useRef<any>(null)
  const boxRef = useRef<HTMLDivElement>(null)
  const pagePatient = (() => { const m = location.pathname.match(/^\/patients\/(\d+)/); return m ? Number(m[1]) : null })()

  useEffect(() => { if (open && !suggestions.length) api<string[]>('/api/copilot/suggestions').then(setSuggestions).catch(() => {}) }, [open, suggestions.length])
  useEffect(() => {  // deep link: ?ask=<message> opens the copilot and sends it
    const ask = new URLSearchParams(location.search).get('ask')
    if (ask) { setOpen(true); send(ask) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => { const b = boxRef.current; if (b) b.scrollTop = b.scrollHeight }, [turns])

  const patch = (id: number, p: Partial<Turn>) => setTurns((ts) => ts.map((t) => (t.id === id ? { ...t, ...p } : t)))

  const poll = async (turnId: number, rid: number, conv: string) => {
    for (let i = 0; i < 80; i++) {
      await new Promise((r) => setTimeout(r, 700))
      try {
        const s = await api(`/api/copilot/requests/${rid}?conversation_id=${conv}`)
        patch(turnId, { status: s })
        if (s.done) return
      } catch { /* keep polling */ }
    }
  }

  const send = async (message = text, patientId: number | null = null) => {
    if (!message.trim() || busy) return
    setText('')
    const uid = Date.now()
    setTurns((ts) => [...ts, { id: uid, role: 'user', text: message }])
    setBusy(true)
    try {
      const r = await api('/api/copilot/chat', { body: { message, conversation_id: cid, patient_id: patientId ?? pagePatient } })
      setCid(r.conversation_id)
      const aid = uid + 1
      if (r.type === 'clarify') {
        setTurns((ts) => [...ts, { id: aid, role: 'assistant', text: r.reply, understood: r.understood_as, options: r.options, pendingText: r.pending_text }])
      } else {
        setTurns((ts) => [...ts, { id: aid, role: 'assistant', understood: r.understood_as, assumed: r.assumed_patient, requestId: r.request_id }])
        poll(aid, r.request_id, r.conversation_id)
      }
    } catch (e: any) {
      setTurns((ts) => [...ts, { id: uid + 1, role: 'assistant', text: `Sorry — ${e.message}` }])
    } finally { setBusy(false) }
  }

  const refresh = async (t: Turn) => { if (t.requestId && cid) { const s = await api(`/api/copilot/requests/${t.requestId}?conversation_id=${cid}`); patch(t.id, { status: s }) } }

  const toggleVoice = () => {
    if (listening) { recRef.current?.stop(); return }
    const rec = new SpeechRec()
    rec.lang = lang
    rec.interimResults = true
    rec.onresult = (e: any) => setText(Array.from(e.results).map((x: any) => x[0].transcript).join(''))
    rec.onend = () => setListening(false)
    rec.onerror = () => setListening(false)
    recRef.current = rec
    rec.start()
    setListening(true)
  }

  return (
    <>
      {!open && (
        <button onClick={() => setOpen(true)} className="fixed bottom-4 right-4 z-40 flex items-center gap-2 rounded-full bg-gradient-to-br from-teal-600 to-teal-800 px-4 py-3 text-sm font-medium text-white shadow-lg ring-4 ring-teal-600/15 transition hover:scale-[1.03] print:hidden">
          <Sparkles className="h-4 w-4" />Copilot
        </button>
      )}
      {open && (
        <div className="fade-in fixed bottom-4 right-4 z-50 flex h-[min(640px,calc(100vh-2rem))] w-[420px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl print:hidden">
          <div className="flex items-center gap-2 bg-gradient-to-r from-teal-700 to-teal-600 px-4 py-3 text-white">
            <Bot className="h-5 w-5" />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold">MedOrchestra Copilot</div>
              <div className="text-[11px] text-teal-100">English · Hinglish · remembers the patient you're discussing</div>
            </div>
            <button onClick={() => { setTurns([]); setCid(null) }} className="rounded-md px-2 py-1 text-[11px] text-teal-100 hover:bg-white/10">New chat</button>
            <button onClick={() => setOpen(false)} aria-label="Close" className="rounded-md p-1 hover:bg-white/10"><X className="h-4 w-4" /></button>
          </div>
          <div ref={boxRef} className="flex-1 space-y-3 overflow-y-auto bg-slate-50 p-3">
            {!turns.length && (
              <div className="space-y-2">
                <div className="rounded-xl bg-white p-3 text-xs text-slate-600 shadow-sm">
                  Ask in plain English or Hinglish. I route your request through the specialist agents and bring back the result —
                  safety-critical actions still need your approval.{pagePatient ? ' I will assume you mean the patient on this page.' : ''}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {suggestions.map((s) => <button key={s} onClick={() => send(s)} className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-left text-[11px] text-slate-600 hover:border-teal-400 hover:text-teal-800">{s}</button>)}
                </div>
              </div>
            )}
            {turns.map((t) => t.role === 'user' ? (
              <div key={t.id} className="ml-10 rounded-2xl rounded-br-sm bg-teal-600 px-3 py-2 text-sm text-white">{t.text}</div>
            ) : (
              <div key={t.id} className="mr-4 space-y-2 rounded-2xl rounded-bl-sm bg-white p-3 text-sm text-slate-700 shadow-sm">
                {t.understood && <div className="flex items-start gap-1.5 text-[11px] text-slate-500"><Languages className="mt-0.5 h-3 w-3 shrink-0" />Understood as: <i>“{t.understood}”</i></div>}
                {t.assumed && <div className="text-[11px] text-slate-500">Assuming you mean <b>{t.assumed}</b>.</div>}
                {t.text && <div>{t.text}</div>}
                {t.options && (
                  <div className="flex flex-wrap gap-1.5">
                    {t.options.map((o) => <button key={o.patient_id} onClick={() => send(t.pendingText || 'status', o.patient_id)} className="rounded-lg border border-teal-200 bg-teal-50 px-2 py-1 text-xs text-teal-800 hover:bg-teal-100">{o.label} <span className="text-teal-600">({label(o.status)})</span></button>)}
                  </div>
                )}
                {t.requestId && <RequestResult t={t} onChanged={() => refresh(t)} />}
              </div>
            ))}
          </div>
          <div className="border-t border-slate-200 bg-white p-2">
            <div className="flex items-end gap-1.5">
              <textarea rows={1} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
                placeholder="e.g. ICU mein kitne bed khali hain?" className="input max-h-24 min-h-[38px] flex-1 resize-none py-2 text-sm" />
              {SpeechRec && (
                <>
                  <button onClick={() => setLang((l) => (l === 'en-IN' ? 'hi-IN' : 'en-IN'))} title="Voice language" className="rounded-lg border border-slate-200 px-1.5 py-2 text-[10px] font-semibold text-slate-500 hover:bg-slate-50">{lang === 'en-IN' ? 'EN' : 'हि'}</button>
                  <button onClick={toggleVoice} title="Speak" className={cls('rounded-lg p-2', listening ? 'bg-red-600 text-white' : 'border border-slate-200 text-slate-500 hover:bg-slate-50')}>{listening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}</button>
                </>
              )}
              <button onClick={() => send()} disabled={busy || !text.trim()} className="rounded-lg bg-teal-600 p-2 text-white disabled:opacity-50">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}</button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function RequestResult({ t, onChanged }: { t: Turn; onChanged: () => void }) {
  const s = t.status
  if (!s || !s.done) {
    return (
      <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-teal-600" />Agents working…
        {(s?.intents || []).map((i: any) => <Badge key={i.name} tone="teal">{label(i.name)}</Badge>)}
      </div>
    )
  }
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {(s.intents || []).slice(0, 3).map((i: any) => <Badge key={i.name} tone="teal">{label(i.name)}</Badge>)}
        {s.patient && <Badge tone="rose">{s.patient.name}</Badge>}
        <Link to={`/agents?request=${s.id}`} className="ml-auto text-[11px] text-teal-700 hover:underline">full trace #{s.id}</Link>
      </div>
      <div className="whitespace-pre-wrap text-[13px] leading-relaxed">{s.summary}</div>
      {s.executed?.length > 0 && <div className="text-[11px] text-emerald-700">✓ Done automatically: {s.executed.join('; ')}</div>}
      {s.approvals?.map((a: any) => <ApprovalCard key={a.id} approval={a} compact onDone={onChanged} />)}
    </div>
  )
}
