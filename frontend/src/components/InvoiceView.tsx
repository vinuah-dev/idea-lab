import { useMemo, useState } from 'react'
import { CreditCard, Printer, Send, ShieldCheck } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, Empty, StatusBadge, useToast } from './ui'
import { cls, fmtDateTime, inr, PAYER_TONE } from '../utils'

export const CATEGORY_LABEL: Record<string, string> = {
  room: 'Room & bed', nursing: 'Nursing care', consultation: 'Consultations', diagnostic: 'Diagnostics', pharmacy: 'Pharmacy',
  procedure: 'Procedures & theatre', emergency: 'Emergency care', equipment: 'Equipment',
}

/** Itemised invoice with coverage breakdown; optional desk actions (collect payment, submit claim). */
export default function InvoiceView({ inv, canCollect, canClaim, onChanged, printHref }: {
  inv: any; canCollect?: boolean; canClaim?: boolean; onChanged?: () => void; printHref?: string
}) {
  const toast = useToast()
  const s = inv.summary
  const [amount, setAmount] = useState('')
  const [mode, setMode] = useState('upi')
  const [busy, setBusy] = useState<string | null>(null)
  const groups = useMemo(() => {
    const g: Record<string, any[]> = {}
    for (const c of inv.charges || []) (g[c.category] ||= []).push(c)
    return Object.entries(g).sort((a, b) => b[1].reduce((t, c) => t + c.amount, 0) - a[1].reduce((t, c) => t + c.amount, 0))
  }, [inv])
  const claim = inv.claims?.[inv.claims.length - 1]
  const claimable = canClaim && inv.payer !== 'self' && (!claim || claim.status === 'rejected') && s.coverage.covered > 0

  const run = async (key: string, fn: () => Promise<any>, ok: string) => {
    setBusy(key)
    try { await fn(); toast({ title: ok, level: 'success' }); setAmount(''); onChanged?.() }
    catch (e: any) { toast({ title: 'Action failed', message: e.message, level: 'critical' }) } finally { setBusy(null) }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_19rem]">
      <div className="min-w-0">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="font-mono text-sm font-semibold text-slate-800">{inv.number}</span>
          <Badge tone={PAYER_TONE[inv.payer] || 'slate'}>{inv.payer_label}</Badge>
          <StatusBadge status={inv.status} />
          <span className="text-xs text-slate-400">opened {fmtDateTime(inv.created_at)}</span>
          {printHref && <a href={printHref} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 text-xs text-teal-700 hover:underline"><Printer className="h-3.5 w-3.5" />Print</a>}
        </div>
        {!groups.length ? <Empty title="No charges captured yet" /> : (
          <div className="overflow-x-auto rounded-lg border border-slate-200">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs text-slate-500"><tr><th className="px-3 py-2">Item</th><th className="px-3 py-2 text-right">Qty</th><th className="px-3 py-2 text-right">Rate</th><th className="px-3 py-2 text-right">Amount</th></tr></thead>
              <tbody>
                {groups.map(([cat, items]) => (
                  <GroupRows key={cat} cat={cat} items={items} />
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-2 text-[11px] text-slate-400">Charges are captured automatically from clinical activity (bed-days, orders, dispensed medicines, procedures). Illustrative tariff.</p>
      </div>

      <div className="space-y-3">
        <div className="rounded-xl border border-slate-200 p-3 text-sm">
          <Row k="Gross charges" v={inr(s.gross)} />
          {s.discount > 0 && <Row k="Discount" v={`− ${inr(s.discount)}`} />}
          <Row k="Net" v={inr(s.net)} bold />
          <div className="my-2 border-t border-dashed border-slate-200" />
          <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-slate-600"><ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />{s.coverage.payer_label}</div>
          {s.coverage.package_name && <div className="mb-1 text-[11px] text-slate-500">{s.coverage.package_name}{s.coverage.package_code ? ` · ${s.coverage.package_code}` : ''}</div>}
          <Row k="Insurance / scheme" v={inr(s.expected_insurance)} />
          {s.coverage.adjustment > 0 && <Row k="Package adjustment (hospital)" v={inr(s.coverage.adjustment)} muted />}
          <Row k="Patient share" v={inr(s.patient_share)} />
          <Row k="Paid" v={inr(s.paid)} />
          <div className={cls('mt-2 flex items-center justify-between rounded-lg px-3 py-2', s.cleared ? 'bg-emerald-50 text-emerald-800' : 'bg-amber-50 text-amber-900')}>
            <span className="text-xs font-medium">{s.cleared ? 'Cleared' : 'Balance due'}</span>
            <span className="text-lg font-semibold tabular-nums">{inr(s.balance)}</span>
          </div>
          {s.coverage.note && <p className="mt-2 text-[11px] text-slate-400">{s.coverage.note}</p>}
        </div>
        {claim && (
          <div className="rounded-xl border border-slate-200 p-3 text-xs">
            <div className="flex items-center justify-between"><span className="font-medium text-slate-700">Claim #{claim.id}</span><StatusBadge status={claim.status} /></div>
            <div className="mt-1 text-slate-500">{claim.package_name}</div>
            <div className="mt-1">Claimed <b>{inr(claim.claimed_amount)}</b>{claim.approved_amount !== null && <> · approved <b>{inr(claim.approved_amount)}</b></>}</div>
            <div className="mt-1 flex flex-wrap gap-1">{(claim.documents || []).map((d: string) => <Badge key={d}>{d}</Badge>)}</div>
          </div>
        )}
        {canCollect && s.balance > 0 && (
          <div className="rounded-xl border border-slate-200 p-3">
            <div className="mb-2 text-xs font-medium text-slate-600">Collect payment</div>
            <div className="flex gap-2">
              <input className="input py-1.5 text-sm" type="number" placeholder={String(Math.round(s.balance))} value={amount} onChange={(e) => setAmount(e.target.value)} />
              <select className="input w-24 py-1.5 text-sm" value={mode} onChange={(e) => setMode(e.target.value)}><option value="upi">UPI</option><option value="card">Card</option><option value="cash">Cash</option></select>
            </div>
            <Button className="mt-2 w-full" size="sm" icon={<CreditCard className="h-3.5 w-3.5" />} loading={busy === 'pay'}
              onClick={() => run('pay', () => api(`/api/billing/invoices/${inv.id}/payments`, { body: { amount: Number(amount || s.balance), mode } }), 'Payment recorded')}>
              Record {inr(Number(amount || s.balance))}
            </Button>
          </div>
        )}
        {claimable && (
          <Button className="w-full" variant="secondary" icon={<Send className="h-3.5 w-3.5" />} loading={busy === 'claim'}
            onClick={() => run('claim', () => api(`/api/billing/invoices/${inv.id}/claim`, { method: 'POST' }), 'Claim submitted to insurer')}>
            Submit {inv.payer === 'pmjay' ? 'PM-JAY' : 'TPA'} claim ({inr(s.coverage.covered)})
          </Button>
        )}
        {inv.payments?.length > 0 && (
          <div className="rounded-xl border border-slate-200 p-3 text-xs">
            <div className="mb-1 font-medium text-slate-600">Payments</div>
            {inv.payments.map((p: any) => (
              <div key={p.id} className="flex justify-between py-0.5"><span className="text-slate-500">{fmtDateTime(p.created_at)} · {p.mode.toUpperCase()}</span><b className="tabular-nums">{inr(p.amount)}</b></div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function GroupRows({ cat, items }: { cat: string; items: any[] }) {
  const total = items.reduce((t, c) => t + c.amount, 0)
  return (
    <>
      <tr className="border-t border-slate-100 bg-slate-50/60"><td className="px-3 py-1.5 text-xs font-semibold text-slate-600" colSpan={3}>{CATEGORY_LABEL[cat] || cat}</td><td className="px-3 py-1.5 text-right text-xs font-semibold tabular-nums text-slate-700">{inr(total)}</td></tr>
      {items.map((c) => (
        <tr key={c.id} className="border-t border-slate-50">
          <td className="px-3 py-1.5 text-slate-700">{c.description}</td>
          <td className="px-3 py-1.5 text-right tabular-nums text-slate-500">{Number(c.quantity).toLocaleString('en-IN')}</td>
          <td className="px-3 py-1.5 text-right tabular-nums text-slate-500">{inr(c.unit_price)}</td>
          <td className="px-3 py-1.5 text-right tabular-nums text-slate-800">{inr(c.amount)}</td>
        </tr>
      ))}
    </>
  )
}

function Row({ k, v, bold, muted }: { k: string; v: string; bold?: boolean; muted?: boolean }) {
  return <div className={cls('flex justify-between py-0.5', muted && 'text-slate-400')}><span className="text-slate-500">{k}</span><span className={cls('tabular-nums', bold && 'font-semibold text-slate-900')}>{v}</span></div>
}
