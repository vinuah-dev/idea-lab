import { useEffect, useState } from 'react'
import { CheckCircle2, Delete, Loader2, Printer } from 'lucide-react'
import { api } from '../api'
import { cls } from '../utils'

const T = {
  en: { title: 'Self check-in', sub: 'Enter your MRN and the last 4 digits of your registered mobile number', mrn: 'MRN number', phone: 'Last 4 digits of mobile',
    go: 'Check in', token: 'Your token', room: 'Room', ahead: 'Position in queue', wait: 'Estimated wait', minutes: 'min', done: 'Done', print: 'Print token',
    lang: 'हिंदी' },
  hi: { title: 'स्वयं चेक-इन', sub: 'अपना MRN और पंजीकृत मोबाइल नंबर के अंतिम 4 अंक दर्ज करें', mrn: 'MRN नंबर', phone: 'मोबाइल के अंतिम 4 अंक',
    go: 'चेक-इन करें', token: 'आपका टोकन', room: 'कमरा', ahead: 'कतार में स्थान', wait: 'अनुमानित प्रतीक्षा', minutes: 'मिनट', done: 'पूर्ण', print: 'टोकन प्रिंट करें',
    lang: 'English' },
}

/** Touch-friendly OPD self check-in kiosk (public). Verifies MRN + phone digits; failed attempts are rate-limited. */
export default function Kiosk() {
  const [lang, setLang] = useState<'en' | 'hi'>('en')
  const [mrn, setMrn] = useState('')
  const [phone, setPhone] = useState('')
  const [field, setField] = useState<'mrn' | 'phone'>('mrn')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ok, setOk] = useState<any>(null)
  const t = T[lang]

  useEffect(() => {
    if (!ok) return
    const id = setTimeout(() => { setOk(null); setMrn(''); setPhone(''); setField('mrn') }, 25000)
    return () => clearTimeout(id)
  }, [ok])

  const press = (k: string) => {
    setError(null)
    const set = field === 'mrn' ? setMrn : setPhone
    const cur = field === 'mrn' ? mrn : phone
    if (k === 'del') set(cur.slice(0, -1))
    else if (field === 'phone' ? cur.length < 4 : cur.length < 6) set(cur + k)
  }
  const submit = async () => {
    setBusy(true)
    setError(null)
    try { setOk(await api('/api/public/kiosk/checkin', { body: { mrn, phone_last4: phone } })) } catch (e: any) { setError(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-gradient-to-br from-teal-700 via-teal-800 to-slate-900 p-6">
      <div className="w-full max-w-xl rounded-3xl bg-white p-8 shadow-2xl">
        <div className="flex items-center gap-3">
          <img src="/icon.svg" className="h-10 w-10" alt="" />
          <div className="flex-1"><div className="text-xl font-semibold text-slate-900">{t.title}</div><div className="text-sm text-slate-500">{t.sub}</div></div>
          <button onClick={() => setLang(lang === 'en' ? 'hi' : 'en')} className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600">{t.lang}</button>
        </div>
        {ok ? (
          <div className="mt-8 text-center print:mt-0">
            <CheckCircle2 className="mx-auto h-14 w-14 text-emerald-500 print:hidden" />
            <div className="mt-2 text-lg text-slate-700">{ok.greeting}</div>
            <div className="mt-4 text-sm uppercase tracking-widest text-slate-400">{t.token}</div>
            <div className="font-mono text-7xl font-bold text-teal-700">{ok.token}</div>
            <div className="mt-2 text-slate-600">{ok.doctor} · {ok.department}</div>
            <div className="mt-5 grid grid-cols-3 gap-3 text-center">
              <div className="rounded-xl bg-slate-50 p-3"><div className="text-xs text-slate-500">{t.room}</div><div className="text-xl font-semibold">{ok.room}</div></div>
              <div className="rounded-xl bg-slate-50 p-3"><div className="text-xs text-slate-500">{t.ahead}</div><div className="text-xl font-semibold">{ok.position}</div></div>
              <div className="rounded-xl bg-slate-50 p-3"><div className="text-xs text-slate-500">{t.wait}</div><div className="text-xl font-semibold">{ok.estimated_wait_minutes} {t.minutes}</div></div>
            </div>
            <div className="mt-6 flex gap-3 print:hidden">
              <button onClick={() => window.print()} className="flex flex-1 items-center justify-center gap-2 rounded-xl border border-slate-200 py-3 text-slate-700"><Printer className="h-5 w-5" />{t.print}</button>
              <button onClick={() => { setOk(null); setMrn(''); setPhone(''); setField('mrn') }} className="flex-1 rounded-xl bg-teal-600 py-3 font-medium text-white">{t.done}</button>
            </div>
          </div>
        ) : (
          <>
            <div className="mt-6 grid grid-cols-2 gap-3">
              <button onClick={() => setField('mrn')} className={cls('rounded-xl border-2 p-3 text-left', field === 'mrn' ? 'border-teal-500 bg-teal-50' : 'border-slate-200')}>
                <div className="text-xs text-slate-500">{t.mrn}</div><div className="font-mono text-2xl font-semibold text-slate-900">MRN-{mrn || '____'}</div>
              </button>
              <button onClick={() => setField('phone')} className={cls('rounded-xl border-2 p-3 text-left', field === 'phone' ? 'border-teal-500 bg-teal-50' : 'border-slate-200')}>
                <div className="text-xs text-slate-500">{t.phone}</div><div className="font-mono text-2xl font-semibold tracking-[0.3em] text-slate-900">{phone.padEnd(4, '•')}</div>
              </button>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2">
              {['1', '2', '3', '4', '5', '6', '7', '8', '9', '', '0', 'del'].map((k, i) => k === '' ? <div key={i} /> : (
                <button key={k} onClick={() => press(k)} className="flex h-16 items-center justify-center rounded-xl bg-slate-100 text-2xl font-semibold text-slate-800 active:bg-slate-200">{k === 'del' ? <Delete className="h-6 w-6" /> : k}</button>
              ))}
            </div>
            {error && <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
            <button disabled={busy || mrn.length < 3 || phone.length !== 4} onClick={submit}
              className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-teal-600 py-4 text-lg font-semibold text-white disabled:opacity-40">
              {busy && <Loader2 className="h-5 w-5 animate-spin" />}{t.go}
            </button>
            <p className="mt-3 text-center text-[11px] text-slate-400">Your details are only used to find today's appointment. Repeated wrong attempts are temporarily blocked.</p>
          </>
        )}
      </div>
    </div>
  )
}
