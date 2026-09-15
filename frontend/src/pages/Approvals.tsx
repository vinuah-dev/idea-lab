import { useState } from 'react'
import { ClipboardCheck } from 'lucide-react'
import ApprovalCard from '../components/ApprovalCard'
import PageHeader from '../components/PageHeader'
import { Empty, Spinner, Tabs } from '../components/ui'
import { useApi, useLive } from '../live'

type Tab = 'pending' | 'executed' | 'rejected' | 'all'

export default function Approvals() {
  const [tab, setTab] = useState<Tab>('pending')
  const { data, loading, reload } = useApi<any[]>(`/api/approvals${tab === 'all' ? '?status=' : `?status=${tab}`}`)
  useLive('approval', () => reload())
  const mine = (data || []).filter((a) => a.can_decide)
  const others = (data || []).filter((a) => !a.can_decide)
  return (
    <div>
      <PageHeader title="Human-in-the-loop approvals" icon={<ClipboardCheck className="h-5 w-5" />}
        subtitle="Agents propose; people decide. Safety-critical actions are executed only after an authorised role approves them — optionally with modifications."
        actions={<Tabs<Tab> value={tab} onChange={setTab} tabs={[{ id: 'pending', label: 'Pending' }, { id: 'executed', label: 'Executed' }, { id: 'rejected', label: 'Rejected' }, { id: 'all', label: 'All' }]} />} />
      {loading && !data ? <Spinner /> : !data?.length ? <Empty icon={<ClipboardCheck className="h-10 w-10" />} title={tab === 'pending' ? 'Nothing waiting for approval' : 'No approvals'} hint="Run a scenario in the AI Agent Console to generate proposals" /> : (
        <div className="space-y-6">
          {tab === 'pending' && mine.length > 0 && (
            <section>
              <h2 className="mb-2 text-sm font-semibold text-slate-700">Needs your decision ({mine.length})</h2>
              <div className="grid gap-3 xl:grid-cols-2">{mine.map((a) => <ApprovalCard key={a.id} approval={a} onDone={reload} />)}</div>
            </section>
          )}
          {(tab !== 'pending' ? data : others).length > 0 && (
            <section>
              {tab === 'pending' && <h2 className="mb-2 text-sm font-semibold text-slate-700">Awaiting other roles ({others.length})</h2>}
              <div className="grid gap-3 xl:grid-cols-2">{(tab !== 'pending' ? data : others).map((a) => <ApprovalCard key={a.id} approval={a} onDone={reload} />)}</div>
            </section>
          )}
        </div>
      )}
    </div>
  )
}
