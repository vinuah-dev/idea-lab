import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Cpu, Users } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import { Badge, Button, Card, Progress, Spinner, Tabs, useToast } from '../components/ui'
import { useAuth } from '../auth'
import { useApi } from '../live'
import { cls } from '../utils'

type Tab = 'staff' | 'roster'
const SHIFT_STYLE: Record<string, string> = { morning: 'bg-sky-100 text-sky-800', evening: 'bg-amber-100 text-amber-800', night: 'bg-indigo-100 text-indigo-800' }

export default function StaffPage() {
  const { user } = useAuth()
  const nav = useNavigate()
  const toast = useToast()
  const [tab, setTab] = useState<Tab>('staff')
  const [role, setRole] = useState('')
  const [dept, setDept] = useState('')
  const staff = useApi<any[]>(`/api/staff?${role ? `role=${role}&` : ''}${dept ? `department_id=${dept}` : ''}`, ['staff'])
  const depts = useApi<any[]>('/api/departments')
  const [busy, setBusy] = useState(false)

  const optimise = async () => {
    setBusy(true)
    try {
      const r = await api('/api/agents/requests', { body: { text: 'Generate an optimized staff roster for next week' } })
      toast({ title: 'Roster optimisation started', message: 'The Staff Scheduling Agent is solving with OR-Tools CP-SAT…', level: 'info' })
      nav(`/agents?request=${r.id}`)
    } catch (e: any) { toast({ title: 'Failed', message: e.message, level: 'critical' }) } finally { setBusy(false) }
  }
  const toggleDuty = async (s: any) => {
    await api(`/api/staff/${s.id}`, { method: 'PATCH', body: { on_duty: !s.on_duty } })
    staff.reload()
  }
  return (
    <div>
      <PageHeader title="Staff & rosters" icon={<Users className="h-5 w-5" />} subtitle="Availability, workload balancing and constraint-optimised shift scheduling"
        actions={<>
          <Tabs<Tab> value={tab} onChange={setTab} tabs={[{ id: 'staff', label: 'Staff & workload' }, { id: 'roster', label: 'Weekly roster' }]} />
          <Button icon={<Cpu className="h-4 w-4" />} loading={busy} onClick={optimise}>Optimise roster (AI)</Button>
        </>} />
      <div className="mb-3 flex flex-wrap gap-2">
        <select className="input w-40" value={role} onChange={(e) => setRole(e.target.value)}><option value="">All roles</option>{['doctor', 'nurse', 'technician', 'pharmacist'].map((r) => <option key={r} value={r}>{r}</option>)}</select>
        <select className="input w-56" value={dept} onChange={(e) => setDept(e.target.value)}><option value="">All departments</option>{(depts.data || []).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
      </div>
      {tab === 'staff' ? (
        staff.loading && !staff.data ? <Spinner /> : (
          <Card bodyClass="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs text-slate-500"><tr><th className="px-4 py-2">Name</th><th className="px-4 py-2">Role</th><th className="px-4 py-2">Department</th><th className="px-4 py-2">Specialisation / skills</th><th className="px-4 py-2">Seniority</th><th className="w-48 px-4 py-2">Workload</th><th className="px-4 py-2">Duty</th></tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {(staff.data || []).map((s) => (
                    <tr key={s.id} className="hover:bg-slate-50">
                      <td className="px-4 py-2 font-medium text-slate-800">{s.name}</td>
                      <td className="px-4 py-2 capitalize text-slate-600">{s.role}</td>
                      <td className="px-4 py-2 text-slate-600">{s.department}</td>
                      <td className="px-4 py-2"><div className="text-xs text-slate-600">{s.specialization}</div><div className="mt-0.5 flex flex-wrap gap-1">{s.skills.slice(0, 3).map((k: string) => <Badge key={k}>{k}</Badge>)}</div></td>
                      <td className="px-4 py-2 text-xs capitalize text-slate-500">{s.seniority}</td>
                      <td className="px-4 py-2"><div className="mb-1 text-[11px] text-slate-500">{s.current_load}/{s.max_patients} patients</div><Progress value={s.current_load} max={s.max_patients} /></td>
                      <td className="px-4 py-2">
                        {user?.role === 'admin' ? (
                          <button onClick={() => toggleDuty(s)} className={cls('rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset', s.on_duty ? 'bg-emerald-50 text-emerald-700 ring-emerald-200' : 'bg-slate-100 text-slate-500 ring-slate-200')}>{s.on_duty ? 'On duty' : 'Off duty'}</button>
                        ) : <Badge tone={s.on_duty ? 'green' : 'slate'}>{s.on_duty ? 'On duty' : 'Off duty'}</Badge>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )
      ) : <Roster staff={staff.data || []} dept={dept} />}
    </div>
  )
}

function Roster({ staff, dept }: { staff: any[]; dept: string }) {
  const today = new Date()
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1).toISOString().slice(0, 10)
  const [from, setFrom] = useState(start)
  const shifts = useApi<any[]>(`/api/shifts?start=${from}&days=7${dept ? `&department_id=${dept}` : ''}`, ['staff'])
  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => { const d = new Date(from); d.setDate(d.getDate() + i); return d.toISOString().slice(0, 10) }), [from])
  const byStaff = useMemo(() => {
    const m: Record<number, Record<string, string>> = {}
    for (const s of shifts.data || []) (m[s.staff_id] ||= {})[s.date] = s.shift
    return m
  }, [shifts.data])
  const people = staff.filter((s) => ['doctor', 'nurse'].includes(s.role))
  const generated = (shifts.data || []).some((s) => s.generated_by === 'optimizer')
  const coverage = days.map((d) => ({ d, m: (shifts.data || []).filter((s) => s.date === d && s.shift === 'morning').length, e: (shifts.data || []).filter((s) => s.date === d && s.shift === 'evening').length, n: (shifts.data || []).filter((s) => s.date === d && s.shift === 'night').length }))
  return (
    <Card title="Shift roster" subtitle={generated ? 'Generated by OR-Tools CP-SAT optimiser (coverage, rest rules, fairness)' : 'Current rotation — run “Optimise roster (AI)” to generate an optimal one'}
      actions={<input type="date" className="input w-40 py-1 text-xs" value={from} onChange={(e) => setFrom(e.target.value)} />} bodyClass="p-0">
      {shifts.loading && !shifts.data ? <Spinner /> : (
        <div className="max-h-[65vh] overflow-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 z-10 bg-slate-50 text-slate-500">
              <tr><th className="sticky left-0 bg-slate-50 px-3 py-2 text-left">Staff</th>{days.map((d) => <th key={d} className="px-2 py-2">{new Date(d).toLocaleDateString([], { weekday: 'short', day: '2-digit' })}</th>)}</tr>
              <tr className="text-[10px]"><th className="sticky left-0 bg-slate-50 px-3 pb-2 text-left font-normal">Coverage M/E/N</th>{coverage.map((c) => <th key={c.d} className="px-2 pb-2 font-normal">{c.m}/{c.e}/{c.n}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {people.map((s) => (
                <tr key={s.id}>
                  <td className="sticky left-0 bg-white px-3 py-1.5"><div className="font-medium text-slate-700">{s.name}</div><div className="text-[10px] text-slate-400">{s.role} · {s.department}</div></td>
                  {days.map((d) => {
                    const sh = byStaff[s.id]?.[d]
                    return <td key={d} className="px-1 py-1 text-center">{sh ? <span className={cls('inline-block w-full rounded px-1 py-0.5 text-[10px] font-semibold uppercase', SHIFT_STYLE[sh])}>{sh[0]}</span> : <span className="text-slate-300">off</span>}</td>
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
