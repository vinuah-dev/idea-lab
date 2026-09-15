import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell, CheckCheck } from 'lucide-react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import { Badge, Button, Card, Empty, Spinner, Tabs } from '../components/ui'
import { useApi, useLive } from '../live'
import { ago, cls } from '../utils'

type Filter = 'all' | 'unread' | 'critical'

export default function Notifications() {
  const nav = useNavigate()
  const [filter, setFilter] = useState<Filter>('all')
  const { data, loading, reload } = useApi<any>('/api/notifications?limit=150')
  useLive('notification', () => reload())
  const items = (data?.items || []).filter((n: any) => filter === 'all' || (filter === 'unread' ? !n.read : n.level === 'critical'))
  const open = async (n: any) => {
    if (!n.read) await api(`/api/notifications/${n.id}/read`, { method: 'POST' })
    if (n.link) nav(n.link)
    else reload()
  }
  return (
    <div>
      <PageHeader title="Notifications" icon={<Bell className="h-5 w-5" />} subtitle="Role-based alerts routed by the Notification Agent (in-app, SMS and e-mail channels are simulated)"
        actions={<><Tabs<Filter> value={filter} onChange={setFilter} tabs={[{ id: 'all', label: 'All' }, { id: 'unread', label: `Unread (${data?.unread ?? 0})` }, { id: 'critical', label: 'Critical' }]} />
          <Button variant="secondary" icon={<CheckCheck className="h-4 w-4" />} onClick={async () => { await api('/api/notifications/read-all', { method: 'POST' }); reload() }}>Mark all read</Button></>} />
      <Card bodyClass="p-0">
        {loading && !data ? <Spinner /> : !items.length ? <Empty title="No notifications" /> : (
          <div className="divide-y divide-slate-100">
            {items.map((n: any) => (
              <button key={n.id} onClick={() => open(n)} className={cls('flex w-full gap-3 px-4 py-3 text-left hover:bg-slate-50', !n.read && 'bg-teal-50/40')}>
                <span className={cls('mt-1.5 h-2 w-2 shrink-0 rounded-full', n.level === 'critical' ? 'bg-red-500' : n.level === 'warning' ? 'bg-amber-500' : n.level === 'success' ? 'bg-emerald-500' : 'bg-sky-500')} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-slate-800">{n.title}</span>
                    <Badge>{n.category}</Badge>
                    {n.channel !== 'in-app' && <Badge tone="violet">{n.channel}</Badge>}
                    {n.role && <Badge tone="slate">to: {n.role}s</Badge>}
                  </div>
                  <div className="mt-0.5 text-sm text-slate-600">{n.message}</div>
                </div>
                <span className="shrink-0 text-xs text-slate-400">{ago(n.created_at)}</span>
              </button>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
