import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { api, getToken } from './api'
import { useAuth } from './auth'

type Handler = (data: any) => void

interface LiveCtx {
  connected: boolean
  subscribe: (type: string, fn: Handler) => () => void
}

const Ctx = createContext<LiveCtx>({ connected: false, subscribe: () => () => {} })

/** WebSocket connection to the backend event bus with automatic reconnect. */
export function LiveProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const [connected, setConnected] = useState(false)
  const handlers = useRef(new Map<string, Set<Handler>>())

  useEffect(() => {
    if (!user) return
    let ws: WebSocket | null = null
    let stop = false
    let retry: ReturnType<typeof setTimeout>
    let ping: ReturnType<typeof setInterval>
    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(getToken() || '')}`)
      ws.onopen = () => {
        setConnected(true)
        ping = setInterval(() => ws?.readyState === 1 && ws.send('ping'), 25000)
      }
      ws.onclose = () => {
        setConnected(false)
        clearInterval(ping)
        if (!stop) retry = setTimeout(connect, 2500)
      }
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          handlers.current.get(msg.type)?.forEach((fn) => fn(msg.data))
          handlers.current.get('*')?.forEach((fn) => fn(msg))
        } catch { /* ignore malformed */ }
      }
    }
    connect()
    return () => {
      stop = true
      clearTimeout(retry)
      clearInterval(ping)
      ws?.close()
    }
  }, [user])

  const subscribe = useCallback((type: string, fn: Handler) => {
    if (!handlers.current.has(type)) handlers.current.set(type, new Set())
    handlers.current.get(type)!.add(fn)
    return () => { handlers.current.get(type)?.delete(fn) }
  }, [])

  return <Ctx.Provider value={{ connected, subscribe }}>{children}</Ctx.Provider>
}

export const useLiveStatus = () => useContext(Ctx).connected

export function useLive(type: string, fn: Handler) {
  const { subscribe } = useContext(Ctx)
  const ref = useRef(fn)
  ref.current = fn
  useEffect(() => subscribe(type, (d) => ref.current(d)), [type, subscribe])
}

/**
 * Fetch JSON from the API; re-fetches when the backend broadcasts a `refresh` event for one of `scopes`
 * (and optionally on an interval).
 */
export function useApi<T = any>(path: string | null, scopes: string[] = [], intervalMs?: number) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)

  const load = useCallback(async () => {
    if (!path) return
    try {
      const d = await api<T>(path)
      setData(d)
      setError(null)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [path])

  useEffect(() => {
    setLoading(true)
    load()
  }, [load])

  useEffect(() => {
    if (!intervalMs) return
    const id = setInterval(load, intervalMs)
    return () => clearInterval(id)
  }, [load, intervalMs])

  const key = scopes.join(',')
  useLive('refresh', (d: { scope: string[] }) => {
    if (!key) return
    const wanted = key.split(',')
    if (d.scope.includes('all') || d.scope.some((s) => wanted.includes(s))) {
      clearTimeout(timer.current)
      timer.current = setTimeout(load, 300)
    }
  })

  return { data, error, loading, reload: load, setData }
}
