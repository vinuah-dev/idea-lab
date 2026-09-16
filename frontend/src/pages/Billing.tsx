import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { BadgeIndianRupee, Calculator, Check, FileStack, Receipt, ShieldCheck, Wallet, X } from 'lucide-react'
import { api } from '../api'
import InvoiceView, { CATEGORY_LABEL } from '../components/InvoiceView'
import PageHeader from '../components/PageHeader'
import { Badge, Button, Card, Empty, Field, Modal, Spinner, Stat, StatusBadge, Tabs, useToast } from '../components/ui'
import { useAuth } from '../auth'
import { useApi } from '../live'
import { cls, fmtDateTime, inr, PAYER_TONE } from '../utils'

type Tab = 'invoices' | 'claims' | 'estimate' | 'tariff'

export default function Billing() {
  const { user } = useAuth()
  const desk = ['admin', 'receptionist'].includes(user!.role)
  const [tab, setTab] = useState<Tab>('invoices')
  const [payer, setPayer] = useState('')
  const [openId, setOpenId] = useState<number | null>(null)
  const summary = useApi<any>('/api/billing/summary', ['billing', 'pharmacy', 'diagnostics', 'beds'], 30000)
  const invoices = useApi<any[]>(`/api/billing/invoices${payer ? `?payer=${payer}` : ''}`, ['billing'])
  const s = summary.data
  const cats = useMemo(() => Object.entries(s?.by_category || {}).map(([k, v]) => ({ name: CATEGORY_LABEL[k] || k, amount: v })), [s])

  return (
    <div>
      <PageHeader title="Billing & Insurance" icon={<Receipt className="h-5 w-5" />}
        subtitle="Charges captured automatically from clinical activity · PM-JAY (Ayushman Bharat) & TPA claims · LOS-aware cost estimates" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <Stat label="Gross billed (open episodes)" value={inr(s?.gross_billed)} sub={`${s?.invoices ?? '—'} invoices`} icon={<FileStack className="h-5 w-5" />} />
        <Stat label="Outstanding (patient share)" value={inr(s?.outstanding)} sub="to collect at desk / portal" icon={<Wallet className="h-5 w-5" />} tone="amber" />
        <Stat label="Collected today" value={inr(s?.collected_today)} sub="cash · UPI · card · insurer" icon={<BadgeIndianRupee className="h-5 w-5" />} tone="emerald" />
        <Stat label="Claims pending" value={s?.claims_pending ?? '—'} sub={inr(s?.claims_pending_amount)} icon={<ShieldCheck className="h-5 w-5" />} tone="violet" onClick={() => setTab('claims')} />
        <Stat label="PM-JAY package adjustments" value={inr(s?.pmjay_adjustments)} sub="tariff above package rate" icon={<Calculator className="h-5 w-5" />} tone="slate" />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card title="Revenue by category" subtitle="Current episodes" className="xl:col-span-2">
          <div className="h-52">
            <ResponsiveContainer>
              <BarChart data={cats} margin={{ left: 10, right: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `₹${Math.round(v / 1000)}k`} />
                <Tooltip formatter={(v: any) => inr(Number(v))} />
                <Bar dataKey="amount" fill="#0d9488" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="Payer mix" subtitle="Share of invoices">
          <div className="space-y-3">
            {Object.entries(s?.payer_mix || {}).map(([k, v]: any) => {
              const total = Object.values(s.payer_mix).reduce((a: any, b: any) => a + b, 0) as number
              return (
                <div key={k}>
                  <div className="mb-1 flex justify-between text-xs"><Badge tone={PAYER_TONE[k] || 'slate'}>{k === 'pmjay' ? 'PM-JAY' : k === 'private' ? 'Private / TPA' : 'Self-pay'}</Badge><span className="tabular-nums text-slate-500">{v} · {Math.round((100 * v) / total)}%</span></div>
                  <div className="h-2 rounded-full bg-slate-100"><div className={cls('h-full rounded-full', k === 'pmjay' ? 'bg-emerald-500' : k === 'private' ? 'bg-indigo-500' : 'bg-slate-400')} style={{ width: `${(100 * v) / total}%` }} /></div>
                </div>
              )
            })}
            <p className="text-[11px] text-slate-400">PM-JAY is cashless for the patient; the Billing Agent maps each stay to a medical per-day or surgical package.</p>
          </div>
        </Card>
      </div>

      <div className="mt-4">
        <Tabs<Tab> value={tab} onChange={setTab} tabs={[{ id: 'invoices', label: 'Invoices' }, { id: 'claims', label: 'Insurance claims' }, { id: 'estimate', label: 'Cost estimator' }, { id: 'tariff', label: 'Tariff' }]} />
        {tab === 'invoices' && (
          <Card className="mt-3" bodyClass="p-0" title="Invoices" subtitle="Sorted by outstanding balance"
            actions={<select className="input w-44 py-1 text-xs" value={payer} onChange={(e) => setPayer(e.target.value)}><option value="">All payers</option><option value="self">Self-pay</option><option value="pmjay">PM-JAY</option><option value="private">Private / TPA</option></select>}>
            {invoices.loading && !invoices.data ? <Spinner /> : !invoices.data?.length ? <Empty title="No invoices" /> : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-left text-xs text-slate-500"><tr>{['Invoice', 'Patient', 'Payer', 'Gross', 'Insurance', 'Patient share', 'Paid', 'Balance', 'Status', ''].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr></thead>
                  <tbody className="divide-y divide-slate-100">
                    {invoices.data.map((i) => (
                      <tr key={i.id} className="hover:bg-slate-50">
                        <td className="px-3 py-2 font-mono text-xs">{i.number}</td>
                        <td className="px-3 py-2"><Link className="font-medium text-slate-800 hover:text-teal-700" to={`/patients/${i.patient?.id}`}>{i.patient?.name}</Link><div className="text-[11px] text-slate-400">{i.patient?.mrn}</div></td>
                        <td className="px-3 py-2"><Badge tone={PAYER_TONE[i.payer] || 'slate'}>{i.payer === 'pmjay' ? 'PM-JAY' : i.payer === 'private' ? 'TPA' : 'Self'}</Badge></td>
                        <td className="px-3 py-2 tabular-nums">{inr(i.summary.gross)}</td>
                        <td className="px-3 py-2 tabular-nums text-emerald-700">{inr(i.summary.expected_insurance)}</td>
                        <td className="px-3 py-2 tabular-nums">{inr(i.summary.patient_share)}</td>
                        <td className="px-3 py-2 tabular-nums">{inr(i.summary.paid)}</td>
                        <td className={cls('px-3 py-2 font-semibold tabular-nums', i.summary.balance > 0 ? 'text-amber-700' : 'text-emerald-700')}>{inr(i.summary.balance)}</td>
                        <td className="px-3 py-2"><StatusBadge status={i.summary.claim_status || i.status} /></td>
                        <td className="px-3 py-2"><Button size="sm" variant="secondary" onClick={() => setOpenId(i.id)}>Open</Button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        )}
        {tab === 'claims' && <Claims admin={user!.role === 'admin'} />}
        {tab === 'estimate' && <Estimator />}
        {tab === 'tariff' && <Tariff />}
      </div>
      {openId && <InvoiceModal id={openId} desk={desk} onClose={() => { setOpenId(null); invoices.reload(); summary.reload() }} />}
    </div>
  )
}

function InvoiceModal({ id, desk, onClose }: { id: number; desk: boolean; onClose: () => void }) {
  const inv = useApi<any>(`/api/billing/invoices/${id}`, ['billing'])
  return (
    <Modal open wide onClose={onClose} title={inv.data ? `${inv.data.number} — ${inv.data.patient?.name}` : 'Invoice'}>
      {!inv.data ? <Spinner /> : <InvoiceView inv={inv.data} canCollect={desk} canClaim={desk} onChanged={inv.reload} printHref={`/print/invoice/${id}`} />}
    </Modal>
  )
}

function Claims({ admin }: { admin: boolean }) {
  const toast = useToast()
  const claims = useApi<any[]>('/api/billing/claims', ['billing'])
  const [amt, setAmt] = useState<Record<number, string>>({})
  const decide = async (c: any, approve: boolean) => {
    try {
      await api(`/api/billing/claims/${c.id}/decide`, { body: { approve, approved_amount: amt[c.id] ? Number(amt[c.id]) : null, note: approve ? 'Approved by TPA' : 'Rejected — documents insufficient' } })
      toast({ title: approve ? 'Claim settled' : 'Claim rejected', level: approve ? 'success' : 'warning' })
      claims.reload()
    } catch (e: any) { toast({ title: 'Failed', message: e.message, level: 'critical' }) }
  }
  return (
    <Card className="mt-3" bodyClass="p-0" title="Insurance & PM-JAY claims" subtitle={admin ? 'Record the insurer / TPA response (simulated in this demo)' : 'Claim pipeline'}>
      {!claims.data?.length ? <Empty title="No claims yet" hint="Claims are prepared by the Billing Agent and submitted after desk verification" /> : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500"><tr>{['Claim', 'Patient', 'Scheme', 'Package', 'Claimed', 'Approved', 'Submitted', 'Status', ''].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-slate-100">
              {claims.data.map((c) => (
                <tr key={c.id}>
                  <td className="px-3 py-2 font-mono text-xs">#{c.id} · {c.invoice}</td>
                  <td className="px-3 py-2">{c.patient?.name}</td>
                  <td className="px-3 py-2"><Badge tone={PAYER_TONE[c.scheme] || 'slate'}>{c.scheme === 'pmjay' ? 'PM-JAY' : 'TPA'}</Badge></td>
                  <td className="px-3 py-2 text-xs text-slate-600">{c.package_name}<div className="font-mono text-[10px] text-slate-400">{c.package_code}</div></td>
                  <td className="px-3 py-2 tabular-nums">{inr(c.claimed_amount)}</td>
                  <td className="px-3 py-2 tabular-nums">{c.approved_amount !== null ? inr(c.approved_amount) : '—'}</td>
                  <td className="px-3 py-2 text-xs text-slate-500">{fmtDateTime(c.submitted_at)}</td>
                  <td className="px-3 py-2"><StatusBadge status={c.status} /></td>
                  <td className="px-3 py-2">
                    {admin && c.status === 'submitted' && (
                      <div className="flex items-center gap-1">
                        <input className="input w-24 py-1 text-xs" type="number" placeholder={String(Math.round(c.claimed_amount))} value={amt[c.id] || ''} onChange={(e) => setAmt({ ...amt, [c.id]: e.target.value })} />
                        <Button size="sm" variant="success" icon={<Check className="h-3 w-3" />} onClick={() => decide(c, true)}>Settle</Button>
                        <Button size="sm" variant="secondary" icon={<X className="h-3 w-3" />} onClick={() => decide(c, false)}>Reject</Button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

const WARDS = ['general', 'hdu', 'cardiac', 'icu', 'isolation', 'pediatric', 'maternity']

function Estimator() {
  const tariff = useApi<any>('/api/billing/tariff')
  const [f, setF] = useState<any>({ age: 58, ward_type: 'icu', acuity: 'high', comorbidities: 1, emergency: true, procedure: '', tests: ['CBC', 'ECG'], payer: 'self', ventilator: false })
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const run = async () => {
    setBusy(true)
    try { setRes(await api('/api/billing/estimate', { body: { ...f, age: Number(f.age), comorbidities: Number(f.comorbidities), procedure: f.procedure || null } })) } finally { setBusy(false) }
  }
  const toggleTest = (c: string) => setF({ ...f, tests: f.tests.includes(c) ? f.tests.filter((x: string) => x !== c) : [...f.tests, c] })
  return (
    <div className="mt-3 grid gap-4 xl:grid-cols-[26rem_1fr]">
      <Card title="Pre-admission cost estimate" subtitle="Stay length from the LOS model's 80% interval" icon={<Calculator className="h-4 w-4" />}>
        <div className="grid grid-cols-2 gap-2.5">
          <Field label="Age"><input className="input" type="number" value={f.age} onChange={(e) => setF({ ...f, age: e.target.value })} /></Field>
          <Field label="Comorbidities"><input className="input" type="number" min={0} max={6} value={f.comorbidities} onChange={(e) => setF({ ...f, comorbidities: e.target.value })} /></Field>
          <Field label="Level of care"><select className="input" value={f.ward_type} onChange={(e) => setF({ ...f, ward_type: e.target.value })}>{WARDS.map((w) => <option key={w}>{w}</option>)}</select></Field>
          <Field label="Acuity"><select className="input" value={f.acuity} onChange={(e) => setF({ ...f, acuity: e.target.value })}>{['low', 'moderate', 'high', 'critical'].map((w) => <option key={w}>{w}</option>)}</select></Field>
          <div className="col-span-2"><Field label="Procedure (optional)"><select className="input" value={f.procedure} onChange={(e) => setF({ ...f, procedure: e.target.value })}><option value="">— none —</option>{(tariff.data?.procedures || []).map((p: any) => <option key={p.key} value={p.key}>{p.name}</option>)}</select></Field></div>
          <div className="col-span-2"><Field label="Payer"><select className="input" value={f.payer} onChange={(e) => setF({ ...f, payer: e.target.value })}><option value="self">Self-pay</option><option value="pmjay">PM-JAY (Ayushman Bharat)</option><option value="private">Private insurance (TPA)</option></select></Field></div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.emergency} onChange={(e) => setF({ ...f, emergency: e.target.checked })} />Emergency admission</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.ventilator} onChange={(e) => setF({ ...f, ventilator: e.target.checked })} />Ventilator</label>
        </div>
        <div className="mt-3 text-xs font-medium text-slate-600">Investigations</div>
        <div className="mt-1 flex flex-wrap gap-1">
          {(tariff.data?.tests || []).map((t: any) => <button key={t.code} onClick={() => toggleTest(t.code)} className={cls('rounded-full border px-2 py-0.5 text-[11px]', f.tests.includes(t.code) ? 'border-teal-400 bg-teal-50 text-teal-800' : 'border-slate-200 text-slate-500')}>{t.code}</button>)}
        </div>
        <Button className="mt-4 w-full" loading={busy} onClick={run} icon={<Calculator className="h-4 w-4" />}>Estimate</Button>
      </Card>
      <Card title="Estimate" subtitle={res ? res.assumptions : 'Fill the form and click Estimate'}>
        {!res ? <Empty title="No estimate yet" /> : (
          <div>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl bg-slate-50 p-3 text-center"><div className="text-xs text-slate-500">Optimistic (P10 stay)</div><div className="text-lg font-semibold tabular-nums">{inr(res.low)}</div><div className="text-[11px] text-slate-400">{res.los.low} days</div></div>
              <div className="rounded-xl bg-teal-50 p-3 text-center ring-1 ring-teal-200"><div className="text-xs text-teal-700">Expected</div><div className="text-2xl font-semibold tabular-nums text-teal-800">{inr(res.expected)}</div><div className="text-[11px] text-teal-600">{res.los.days} days predicted</div></div>
              <div className="rounded-xl bg-slate-50 p-3 text-center"><div className="text-xs text-slate-500">Prolonged (P90 stay)</div><div className="text-lg font-semibold tabular-nums">{inr(res.high)}</div><div className="text-[11px] text-slate-400">{res.los.high} days</div></div>
            </div>
            <div className="mt-4 space-y-1.5">
              {res.breakdown.map((b: any) => <div key={b.item} className="flex justify-between border-b border-slate-50 pb-1 text-sm"><span className="text-slate-600">{b.item}</span><span className="tabular-nums">{inr(b.amount)}</span></div>)}
            </div>
            <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm">
              <div className="font-medium text-emerald-900">{res.coverage.payer_label}{res.coverage.package_name ? ` — ${res.coverage.package_name}` : ''}</div>
              <div className="mt-1 flex flex-wrap gap-x-6 text-emerald-800"><span>Covered: <b>{inr(res.coverage.covered)}</b></span><span>Patient pays (expected): <b>{inr(res.coverage.patient_share)}</b></span></div>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}

function Tariff() {
  const t = useApi<any>('/api/billing/tariff')
  if (!t.data) return <Spinner />
  return (
    <div className="mt-3 grid gap-4 xl:grid-cols-3">
      <Card title="Room tariff (per day)">{Object.entries(t.data.room).map(([k, v]: any) => <div key={k} className="flex justify-between py-0.5 text-sm"><span className="capitalize text-slate-600">{k}</span><span className="tabular-nums">{inr(v)}</span></div>)}</Card>
      <Card title="Procedures" subtitle="Hospital tariff vs PM-JAY package">{t.data.procedures.map((p: any) => <div key={p.key} className="flex justify-between gap-2 py-0.5 text-sm"><span className="truncate text-slate-600">{p.name}</span><span className="shrink-0 tabular-nums">{inr(p.price)} <span className="text-emerald-600">/ {inr(p.pmjay_package)}</span></span></div>)}</Card>
      <Card title="PM-JAY medical packages (per day)" subtitle={t.data.note}>{t.data.pmjay_medical.map((p: any) => <div key={p.code} className="flex justify-between py-0.5 text-sm"><span className="text-slate-600">{p.name}</span><span className="tabular-nums">{inr(p.per_day)}</span></div>)}</Card>
    </div>
  )
}
