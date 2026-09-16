import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Printer } from 'lucide-react'
import { api } from '../api'
import { useAuth } from '../auth'
import { CATEGORY_LABEL } from '../components/InvoiceView'
import { Spinner } from '../components/ui'
import { fmtDateTime, inr } from '../utils'

/** Printable itemised bill (staff: any invoice; patients: their own current bill). */
export default function InvoicePrint() {
  const { id } = useParams()
  const { user } = useAuth()
  const [inv, setInv] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const load = user?.role === 'patient' ? api('/api/portal/bill').then((r) => r.invoice) : api(`/api/billing/invoices/${id}`)
    load.then(setInv).catch((e) => setError(e.message))
  }, [id, user])
  if (error) return <div className="p-8 text-red-600">{error}</div>
  if (!inv) return <Spinner />
  const s = inv.summary
  const groups: Record<string, any[]> = {}
  for (const c of inv.charges) (groups[c.category] ||= []).push(c)
  return (
    <div className="mx-auto max-w-3xl bg-white p-8 text-sm text-slate-800">
      <button onClick={() => window.print()} className="mb-4 inline-flex items-center gap-1.5 rounded-lg bg-teal-600 px-3 py-1.5 text-xs text-white print:hidden"><Printer className="h-3.5 w-3.5" />Print / save as PDF</button>
      <div className="flex items-start justify-between border-b-2 border-teal-700 pb-3">
        <div><div className="text-lg font-semibold">{inv.hospital || 'CityCare Multispeciality Hospital'}</div><div className="text-xs text-slate-500">Itemised hospital bill</div></div>
        <div className="text-right text-xs"><div className="font-mono text-sm font-semibold">{inv.number}</div><div>{fmtDateTime(inv.created_at)}</div><div className="capitalize">Status: {inv.status}</div></div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div><b>Patient:</b> {inv.patient?.name} ({inv.patient?.mrn})</div>
        <div><b>Payer:</b> {inv.payer_label}</div>
      </div>
      <table className="mt-4 w-full border-collapse text-xs">
        <thead><tr className="border-b border-slate-300 text-left"><th className="py-1">Description</th><th className="py-1 text-right">Qty</th><th className="py-1 text-right">Rate</th><th className="py-1 text-right">Amount</th></tr></thead>
        <tbody>
          {Object.entries(groups).map(([cat, items]) => (
            <>
              <tr key={cat}><td colSpan={4} className="pt-2 font-semibold text-slate-600">{CATEGORY_LABEL[cat] || cat}</td></tr>
              {items.map((c) => <tr key={c.id} className="border-b border-slate-100"><td className="py-1">{c.description}</td><td className="py-1 text-right">{c.quantity}</td><td className="py-1 text-right">{inr(c.unit_price)}</td><td className="py-1 text-right">{inr(c.amount)}</td></tr>)}
            </>
          ))}
        </tbody>
      </table>
      <div className="ml-auto mt-4 w-72 space-y-1 text-xs">
        <div className="flex justify-between"><span>Gross</span><b>{inr(s.gross)}</b></div>
        <div className="flex justify-between"><span>{s.coverage.payer_label}</span><span>− {inr(s.expected_insurance)}</span></div>
        <div className="flex justify-between"><span>Patient share</span><span>{inr(s.patient_share)}</span></div>
        <div className="flex justify-between"><span>Paid</span><span>− {inr(s.paid)}</span></div>
        <div className="flex justify-between border-t border-slate-300 pt-1 text-sm"><span>Balance due</span><b>{inr(s.balance)}</b></div>
      </div>
      <p className="mt-8 text-[10px] text-slate-400">Computer-generated bill from the MedOrchestra demo system. Tariffs and package rates are illustrative.</p>
    </div>
  )
}
