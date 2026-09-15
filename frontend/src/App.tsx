import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import AgentConsole from './pages/AgentConsole'
import Approvals from './pages/Approvals'
import Patients from './pages/Patients'
import PatientDetail from './pages/PatientDetail'
import Inpatients from './pages/Inpatients'
import Beds from './pages/Beds'
import OperationTheatres from './pages/OperationTheatres'
import Opd from './pages/Opd'
import StaffPage from './pages/Staff'
import Diagnostics from './pages/Diagnostics'
import Pharmacy from './pages/Pharmacy'
import Emergency from './pages/Emergency'
import Analytics from './pages/Analytics'
import Notifications from './pages/Notifications'
import Audit from './pages/Audit'
import Users from './pages/Users'
import Portal from './pages/Portal'
import SystemPage from './pages/System'
import DischargeSummary from './pages/DischargeSummary'

export default function App() {
  const { user } = useAuth()
  if (!user) return <Login />
  if (user.role === 'patient') {
    return (
      <Routes>
        <Route path="/print/discharge/:id" element={<DischargeSummary />} />
        <Route element={<Layout />}>
          <Route path="/portal" element={<Portal />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="*" element={<Navigate to="/portal" replace />} />
        </Route>
      </Routes>
    )
  }
  return (
    <Routes>
      <Route path="/print/discharge/:id" element={<DischargeSummary />} />
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/agents" element={<AgentConsole />} />
        <Route path="/approvals" element={<Approvals />} />
        <Route path="/emergency" element={<Emergency />} />
        <Route path="/inpatients" element={<Inpatients />} />
        <Route path="/patients" element={<Patients />} />
        <Route path="/patients/:id" element={<PatientDetail />} />
        <Route path="/beds" element={<Beds />} />
        <Route path="/theatres" element={<OperationTheatres />} />
        <Route path="/opd" element={<Opd />} />
        <Route path="/staff" element={<StaffPage />} />
        <Route path="/diagnostics" element={<Diagnostics />} />
        <Route path="/pharmacy" element={<Pharmacy />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/audit" element={<Audit />} />
        <Route path="/users" element={<Users />} />
        <Route path="/system" element={<SystemPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
