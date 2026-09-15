import { useState } from 'react'
import { KeyRound, ShieldCheck, UserPlus } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import { Badge, Button, Card, Field, Modal, Spinner, useToast } from '../components/ui'
import { useAuth } from '../auth'
import { useApi } from '../live'
import { ago, cls } from '../utils'

const ROLES = ['admin', 'doctor', 'nurse', 'receptionist', 'lab', 'pharmacist', 'patient']
const ROLE_TONE: Record<string, any> = { admin: 'violet', doctor: 'blue', nurse: 'rose', receptionist: 'amber', lab: 'orange', pharmacist: 'emerald', patient: 'slate' }
const PERMISSIONS: [string, string[]][] = [
  ['Command center & agent console', ['admin', 'doctor', 'nurse', 'receptionist', 'lab', 'pharmacist']],
  ['Approve clinical actions (admit, orders, Rx override, discharge)', ['admin', 'doctor']],
  ['Approve theatre bookings', ['admin', 'doctor']],
  ['Approve bed placements', ['admin', 'nurse', 'receptionist']],
  ['Approve rosters & redeployment', ['admin']],
  ['Record observations / ER triage', ['admin', 'doctor', 'nurse']],
  ['Verify & dispense prescriptions', ['admin', 'pharmacist']],
  ['Report diagnostic results', ['admin', 'lab', 'doctor']],
  ['Audit log, users & policy settings', ['admin']],
  ['Patient portal (own record only)', ['patient']],
]

export default function Users() {
  const { user: me } = useAuth()
  const toast = useToast()
  const { data, loading, reload } = useApi<any[]>('/api/users')
  const staff = useApi<any[]>('/api/staff')
  const [open, setOpen] = useState(false)
  const [reset, setReset] = useState<any>(null)
  const [pw, setPw] = useState('')
  const [f, setF] = useState({ username: '', full_name: '', role: 'nurse', password: '', staff_id: '' })

  const create = async () => {
    try {
      await api('/api/users', { body: { ...f, staff_id: f.staff_id ? Number(f.staff_id) : null } })
      toast({ title: 'User created', message: f.username, level: 'success' })
      setOpen(false)
      setF({ username: '', full_name: '', role: 'nurse', password: '', staff_id: '' })
      reload()
    } catch (e: any) { toast({ title: 'Failed', message: e.message, level: 'critical' }) }
  }
  const patch = async (u: any, body: any, msg: string) => {
    try { await api(`/api/users/${u.id}`, { method: 'PATCH', body }); toast({ title: msg, level: 'success' }); reload() } catch (e: any) { toast({ title: 'Failed', message: e.message, level: 'critical' }) }
  }
  return (
    <div>
      <PageHeader title="Users & access control" icon={<ShieldCheck className="h-5 w-5" />} subtitle="Role-based access control — accounts, roles, activation and password resets (all changes audited)"
        actions={<Button icon={<UserPlus className="h-4 w-4" />} onClick={() => setOpen(true)}>New user</Button>} />
      <div className="grid gap-4 xl:grid-cols-[1fr_24rem]">
        <Card bodyClass="p-0">
          {loading && !data ? <Spinner /> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs text-slate-500"><tr><th className="px-4 py-2">Username</th><th className="px-4 py-2">Name</th><th className="px-4 py-2">Role</th><th className="px-4 py-2">Linked record</th><th className="px-4 py-2">Created</th><th className="px-4 py-2">Status</th><th className="px-4 py-2"></th></tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {(data || []).map((u) => (
                    <tr key={u.id} className={cls(!u.active && 'opacity-50')}>
                      <td className="px-4 py-2 font-mono text-xs">{u.username}</td>
                      <td className="px-4 py-2 font-medium">{u.full_name}</td>
                      <td className="px-4 py-2">
                        {u.id === me?.id ? <Badge tone={ROLE_TONE[u.role]}>{u.role}</Badge> : (
                          <select className="rounded border border-slate-200 bg-white px-1 py-0.5 text-xs" value={u.role} onChange={(e) => patch(u, { role: e.target.value }, 'Role updated')}>
                            {ROLES.map((r) => <option key={r}>{r}</option>)}
                          </select>
                        )}
                      </td>
                      <td className="px-4 py-2 text-xs text-slate-500">{u.staff_id ? `staff #${u.staff_id}` : u.patient_id ? `patient #${u.patient_id}` : '—'}</td>
                      <td className="px-4 py-2 text-xs text-slate-500">{ago(u.created_at)}</td>
                      <td className="px-4 py-2">
                        <button disabled={u.id === me?.id} onClick={() => patch(u, { active: !u.active }, u.active ? 'User deactivated' : 'User activated')}
                          className={cls('rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset disabled:cursor-not-allowed', u.active ? 'bg-emerald-50 text-emerald-700 ring-emerald-200' : 'bg-slate-100 text-slate-500 ring-slate-200')}>
                          {u.active ? 'active' : 'inactive'}
                        </button>
                      </td>
                      <td className="px-4 py-2 text-right"><Button size="sm" variant="ghost" icon={<KeyRound className="h-3.5 w-3.5" />} onClick={() => { setReset(u); setPw('') }}>Reset password</Button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        <Card title="Permission matrix" subtitle="Enforced server-side on every endpoint">
          <div className="space-y-2">
            {PERMISSIONS.map(([perm, roles]) => (
              <div key={perm} className="text-xs"><div className="font-medium text-slate-700">{perm}</div><div className="mt-0.5 flex flex-wrap gap-1">{roles.map((r) => <Badge key={r} tone={ROLE_TONE[r]}>{r}</Badge>)}</div></div>
            ))}
          </div>
        </Card>
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title="Create user" footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button onClick={create} disabled={f.username.length < 3 || f.password.length < 6 || f.full_name.length < 2}>Create</Button></>}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Username"><input className="input" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} /></Field>
          <Field label="Role"><select className="input" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{ROLES.map((r) => <option key={r}>{r}</option>)}</select></Field>
          <div className="col-span-2"><Field label="Full name"><input className="input" value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></Field></div>
          <div className="col-span-2"><Field label="Link to staff record (optional)"><select className="input" value={f.staff_id} onChange={(e) => setF({ ...f, staff_id: e.target.value })}><option value="">—</option>{(staff.data || []).map((s) => <option key={s.id} value={s.id}>{s.name} · {s.role} · {s.department}</option>)}</select></Field></div>
          <div className="col-span-2"><Field label="Initial password (min 6 characters)"><input className="input" type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field></div>
        </div>
      </Modal>
      <Modal open={!!reset} onClose={() => setReset(null)} title={`Reset password — ${reset?.username}`}
        footer={<><Button variant="secondary" onClick={() => setReset(null)}>Cancel</Button><Button disabled={pw.length < 6} onClick={() => { patch(reset, { password: pw }, 'Password reset'); setReset(null) }}>Reset</Button></>}>
        <Field label="New password (min 6 characters)"><input className="input" type="password" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
      </Modal>
    </div>
  )
}
