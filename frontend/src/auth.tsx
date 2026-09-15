import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, clearSession, getToken, loadUser, saveSession } from './api'

export type Role = 'admin' | 'doctor' | 'nurse' | 'receptionist' | 'lab' | 'pharmacist' | 'patient'

export interface User {
  id: number
  username: string
  full_name: string
  role: Role
  staff_id: number | null
  patient_id: number | null
  department_id: number | null
}

interface AuthCtx {
  user: User | null
  login: (username: string, password: string) => Promise<User>
  logout: () => void
}

const Ctx = createContext<AuthCtx>(null as unknown as AuthCtx)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => (getToken() ? loadUser<User>() : null))

  const logout = useCallback(() => {
    clearSession()
    setUser(null)
  }, [])

  useEffect(() => {
    const onLogout = () => setUser(null)
    window.addEventListener('auth:logout', onLogout)
    if (getToken()) api<User>('/api/auth/me').then(setUser).catch(() => {})
    return () => window.removeEventListener('auth:logout', onLogout)
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const res = await api<{ access_token: string; user: User }>('/api/auth/login', { body: { username, password } })
    saveSession(res.access_token, res.user)
    setUser(res.user)
    return res.user
  }, [])

  return <Ctx.Provider value={{ user, login, logout }}>{children}</Ctx.Provider>
}

export const useAuth = () => useContext(Ctx)

export const STAFF: Role[] = ['admin', 'doctor', 'nurse', 'receptionist', 'lab', 'pharmacist']
