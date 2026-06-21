import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { getToken } from '@/api/client'
import AdminLayout from '@/components/layout/AdminLayout'
import { LanguageProvider } from '@/i18n/LanguageProvider'
import LoginPage from '@/pages/Login'
import DashboardPage from '@/pages/Dashboard'
import KnowledgeBaseListPage from '@/pages/KnowledgeBaseList'
import KnowledgeBaseEditPage from '@/pages/KnowledgeBaseEdit'
import StationsListPage from '@/pages/StationsList'
import StationEditPage from '@/pages/StationEdit'
import TripsListPage from '@/pages/TripsList'
import TripEditPage from '@/pages/TripEdit'
import BotSettingsPage from '@/pages/BotSettingsPage'
import ConversationsPage from '@/pages/ConversationsPage'
import MetricsPage from '@/pages/MetricsPage'
import PublicChatPage from '@/pages/PublicChat'

function RequireAuth({ children }: { children: React.ReactNode }) {
  if (!getToken()) return <Navigate to="/login" replace />
  return <>{children}</>
}

function AdminLanguageShell() {
  return (
    <LanguageProvider scope="admin" defaultLocale="en">
      <Outlet />
    </LanguageProvider>
  )
}

function ChatLanguageShell() {
  return (
    <LanguageProvider scope="chat" defaultLocale="ar">
      <Outlet />
    </LanguageProvider>
  )
}

export default function App() {
  return (
    <Routes>
      <Route element={<ChatLanguageShell />}>
        <Route path="/chat" element={<PublicChatPage />} />
      </Route>

      <Route element={<AdminLanguageShell />}>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/admin"
          element={
            <RequireAuth>
              <AdminLayout />
            </RequireAuth>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="kb" element={<KnowledgeBaseListPage />} />
          <Route path="kb/:id" element={<KnowledgeBaseEditPage />} />
          <Route path="stations" element={<StationsListPage />} />
          <Route path="stations/:id" element={<StationEditPage />} />
          <Route path="trips" element={<TripsListPage />} />
          <Route path="trips/:id" element={<TripEditPage />} />
          <Route path="conversations" element={<ConversationsPage />} />
          <Route path="metrics" element={<MetricsPage />} />
          <Route path="bot-settings" element={<BotSettingsPage />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  )
}
