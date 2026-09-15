import { useParams } from 'react-router-dom'
import { Printer } from 'lucide-react'
import { useApi } from '../live'
import { fmtDate, fmtDateTime } from '../utils'

/** Printable discharge summary (opens in its own tab, no app chrome). */
export default function DischargeSummary() {
  const { id } = useParams()
  const { data, error } = useApi<any>(`/api/admissions/${id}/summary`)
  if (error) return <div className="p-10 text-center text-red-600">{error}</div>
  if (!data) return <div className="p-10 text-center text-slate-500">Preparing summary…</div>
  const p = data.patient, a = data.admission
  return (
    <div className="min-h-full bg-slate-100 py-6 print:bg-white print:py-0">
      <div className="mx-auto mb-4 flex max-w-3xl justify-end print:hidden">
        <button onClick={() => window.print()} className="inline-flex items-center gap-2 rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-teal-700"><Printer className="h-4 w-4" />Print / save as PDF</button>
      </div>
      <article className="mx-auto max-w-3xl bg-white p-10 text-sm leading-relaxed text-slate-800 shadow print:max-w-none print:p-0 print:shadow-none">
        <header className="flex items-start justify-between border-b-2 border-teal-700 pb-4">
          <div className="flex items-center gap-3"><img src="/icon.svg" className="h-12 w-12" alt="" /><div><div className="text-lg font-bold text-teal-800">{data.hospital}</div><div className="text-xs text-slate-500">Department of {a.ward || 'Inpatient Services'}</div></div></div>
          <div className="text-right"><div className="text-base font-semibold uppercase tracking-wide">Discharge Summary</div><div className="text-xs text-slate-500">Generated {fmtDateTime(data.generated_at)}</div></div>
        </header>

        <section className="mt-4 grid grid-cols-2 gap-x-8 gap-y-1 text-[13px]">
          <Row k="Patient" v={p.name} /><Row k="MRN" v={p.mrn} />
          <Row k="Age / Sex" v={`${p.age} / ${p.gender}`} /><Row k="Blood group" v={p.blood_group || '—'} />
          <Row k="Admitted" v={fmtDateTime(a.admitted_at)} /><Row k="Discharged" v={a.discharged_at ? fmtDateTime(a.discharged_at) : 'Planned'} />
          <Row k="Ward / bed" v={`${a.ward || '—'} / ${a.bed || '—'}`} /><Row k="Length of stay" v={`${data.los_days} day(s)`} />
          <Row k="Consultant" v={a.doctor || '—'} /><Row k="Allergies" v={p.allergies.length ? p.allergies.join(', ') : 'No known allergies'} />
        </section>

        <H>Diagnosis / reason for admission</H>
        <p>{a.reason || '—'}{p.conditions.length > 0 && <span className="text-slate-500"> · Comorbidities: {p.conditions.join(', ')}</span>}</p>
        <H>Clinical summary</H>
        <p>{data.narrative}</p>

        {data.procedures.length > 0 && (<><H>Procedures</H><ul className="list-disc pl-5">{data.procedures.map((s: any) => <li key={s.id}>{s.procedure} — {fmtDate(s.scheduled_start)} ({s.surgeon || 'surgeon'}, {s.anaesthesia})</li>)}</ul></>)}

        <H>Investigations</H>
        {data.investigations.length === 0 ? <p className="text-slate-500">None recorded.</p> : (
          <table className="w-full border-collapse text-[12px]"><thead><tr className="border-b text-left text-slate-500"><th className="py-1">Test</th><th>Date</th><th>Result</th></tr></thead>
            <tbody>{data.investigations.map((o: any) => <tr key={o.id} className="border-b border-slate-100 align-top"><td className="py-1 pr-2">{o.test_name}</td><td className="pr-2">{fmtDate(o.completed_at || o.created_at)}</td><td className={o.abnormal ? 'font-medium' : ''}>{o.result || o.status}</td></tr>)}</tbody></table>
        )}

        <H>Observations</H>
        <p>{data.vitals_first ? `On admission NEWS2 ${data.vitals_first.news2}; ` : ''}{data.vitals_last ? `latest NEWS2 ${data.vitals_last.news2} (HR ${data.vitals_last.hr}, RR ${data.vitals_last.rr}, SpO₂ ${data.vitals_last.spo2}%, BP ${data.vitals_last.sbp}/${data.vitals_last.dbp ?? '–'}, T ${data.vitals_last.temp}°C).` : 'No observations recorded.'}</p>

        <H>Medications on discharge</H>
        {data.medications.length === 0 ? <p className="text-slate-500">None.</p> : (
          <table className="w-full border-collapse text-[12px]"><thead><tr className="border-b text-left text-slate-500"><th className="py-1">Medicine</th><th>Dose</th><th>Frequency</th><th>Duration</th></tr></thead>
            <tbody>{data.medications.map((r: any) => <tr key={r.id} className="border-b border-slate-100"><td className="py-1">{r.medication}</td><td>{r.dose}</td><td>{r.frequency}</td><td>{r.duration_days} days</td></tr>)}</tbody></table>
        )}

        <H>Follow-up</H>
        <p>{data.follow_up ? `${fmtDateTime(data.follow_up.scheduled_at)} with ${data.follow_up.doctor} (${data.follow_up.department}).` : 'Review in the OPD in 7 days or earlier if symptoms recur.'}</p>
        <H>Advice</H>
        <ul className="list-disc pl-5">{data.advice.map((x: string) => <li key={x}>{x}</li>)}</ul>

        <footer className="mt-12 grid grid-cols-2 gap-8 text-xs text-slate-500">
          <div className="border-t border-slate-300 pt-1">Treating consultant: {a.doctor || '________________'}</div>
          <div className="border-t border-slate-300 pt-1 text-right">Patient / attendant signature</div>
        </footer>
        <p className="mt-6 text-center text-[10px] text-slate-400">Generated by MedOrchestra from the electronic record. Clinical content must be verified and signed by the treating consultant.</p>
      </article>
    </div>
  )
}

const H = ({ children }: { children: React.ReactNode }) => <h2 className="mt-5 mb-1 border-b border-slate-200 pb-0.5 text-[12px] font-bold uppercase tracking-wide text-teal-800">{children}</h2>
const Row = ({ k, v }: { k: string; v: string }) => <div className="flex gap-2"><span className="w-28 shrink-0 text-slate-500">{k}</span><span className="font-medium">{v}</span></div>
