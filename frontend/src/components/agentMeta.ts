import { BedDouble, BellRing, CalendarClock, Cpu, HeartPulse, Microscope, Network, Pill, Siren, UserCheck, Users, type LucideIcon } from 'lucide-react'

export interface AgentMeta { short: string; name: string; icon: LucideIcon; color: string }

export const AGENT_META: Record<string, AgentMeta> = {
  orchestrator: { short: 'Orchestrator', name: 'AI Agent Orchestrator', icon: Network, color: '#0f766e' },
  bed: { short: 'Bed Mgmt', name: 'Bed Management Agent', icon: BedDouble, color: '#0284c7' },
  appointment: { short: 'Appointments', name: 'Appointment & Queue Agent', icon: CalendarClock, color: '#4f46e5' },
  staff: { short: 'Staffing', name: 'Staff Scheduling Agent', icon: Users, color: '#7c3aed' },
  diagnostic: { short: 'Diagnostics', name: 'Diagnostic Coordination Agent', icon: Microscope, color: '#d97706' },
  pharmacy: { short: 'Pharmacy', name: 'Pharmacy Agent', icon: Pill, color: '#059669' },
  care: { short: 'Patient Care', name: 'Patient Care Coordinator Agent', icon: HeartPulse, color: '#e11d48' },
  emergency: { short: 'Emergency', name: 'Emergency Support Agent', icon: Siren, color: '#dc2626' },
  optimization: { short: 'Optimizer', name: 'Resource Optimization Agent', icon: Cpu, color: '#0d9488' },
  notification: { short: 'Notify', name: 'Notification Agent', icon: BellRing, color: '#ea580c' },
  human: { short: 'Human', name: 'Human reviewer', icon: UserCheck, color: '#334155' },
}

export const AGENT_ORDER = ['emergency', 'bed', 'staff', 'optimization', 'diagnostic', 'pharmacy', 'appointment', 'care', 'notification']

export const meta = (key?: string | null): AgentMeta => AGENT_META[key || 'orchestrator'] || AGENT_META.orchestrator
