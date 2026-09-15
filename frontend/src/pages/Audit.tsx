import { useState } from 'react'
import { ScrollText } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { Badge, Card, Spinner, Tabs } from '../components/ui'
import { useApi } from '../live'
import { fmtDateTime } from '../utils'

type Filter = '' | 'user' | 'agent' | 'system'

export default function Audit() {
  const [type, setType] = useState<Filter>('')
  const [open, setOpen] = useState<number | null>(null)
  const { data, loading } = useApi<any[]>(`/api/audit?limit=300${type ? `&actor_type=${type}` : ''}`, ['all'], 10000)
  return (
    <div>
      <PageHeader title="Audit log" icon={<ScrollText className="h-5 w-5" />} subtitle="Every human decision and every agent action is recorded for accountability and compliance"
        actions={<Tabs<Filter> value={type} onChange={setType} tabs={[{ id: '', label: 'All' }, { id: 'user', label: 'Humans' }, { id: 'agent', label: 'AI agents' }, { id: 'system', label: 'System' }]} />} />
      <Card bodyClass="p-0">
        {loading && !data ? <Spinner /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs text-slate-500"><tr><th className="px-4 py-2">Time</th><th className="px-4 py-2">Actor</th><th className="px-4 py-2">Action</th><th className="px-4 py-2">Entity</th><th className="px-4 py-2">Details</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {(data || []).map((a) => (
                  <tr key={a.id} className="align-top hover:bg-slate-50">
                    <td className="whitespace-nowrap px-4 py-2 text-xs tabular-nums text-slate-500">{fmtDateTime(a.timestamp)}</td>
                    <td className="px-4 py-2"><div className="flex items-center gap-2"><Badge tone={a.actor_type === 'agent' ? 'teal' : a.actor_type === 'user' ? 'blue' : 'slate'}>{a.actor_type}</Badge><span className="text-slate-700">{a.actor}</span></div></td>
                    <td className="px-4 py-2 font-mono text-xs text-slate-700">{a.action}</td>
                    <td className="px-4 py-2 text-xs text-slate-500">{a.entity}{a.entity_id ? ` #${a.entity_id}` : ''}</td>
                    <td className="max-w-md px-4 py-2">
                      <button onClick={() => setOpen(open === a.id ? null : a.id)} className="w-full text-left font-mono text-[11px] text-slate-500 hover:text-slate-800">
                        {open === a.id ? <pre className="whitespace-pre-wrap break-all">{JSON.stringify(a.details, null, 2)}</pre> : <span className="line-clamp-1 break-all">{JSON.stringify(a.details)}</span>}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
