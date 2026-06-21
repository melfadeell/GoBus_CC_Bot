import { useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate, Link } from 'react-router-dom'
import {
  Activity,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  LayoutDashboard,
  LogOut,
  MapPin,
  Menu,
  MessageSquare,
  Route,
  Settings,
  X,
} from 'lucide-react'
import { clearToken } from '@/api/client'
import LanguageToggle from '@/components/layout/LanguageToggle'
import { useLanguage } from '@/i18n/LanguageProvider'

const SIDEBAR_KEY = 'gobus_sidebar_collapsed'

export default function AdminLayout() {
  const navigate = useNavigate()
  const { t, dir } = useLanguage()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(SIDEBAR_KEY) === '1')

  useEffect(() => {
    localStorage.setItem(SIDEBAR_KEY, collapsed ? '1' : '0')
  }, [collapsed])

  const navItems = [
    { to: '/admin', label: t.nav.dashboard, icon: LayoutDashboard, end: true },
    { to: '/admin/kb', label: t.nav.kb, icon: BookOpen },
    { to: '/admin/stations', label: t.nav.stations, icon: MapPin },
    { to: '/admin/trips', label: t.nav.trips, icon: Route },
    { to: '/admin/conversations', label: t.nav.conversations, icon: MessageSquare },
    { to: '/admin/metrics', label: t.nav.metrics, icon: Activity },
    { to: '/admin/bot-settings', label: t.nav.botSettings, icon: Settings },
  ]

  function logout() {
    clearToken()
    navigate('/login')
  }

  const showLabels = !collapsed || mobileOpen
  const sidebarWidth = collapsed && !mobileOpen ? 'lg:w-[4.5rem]' : 'lg:w-64'
  const mainOffset = collapsed ? 'lg:ms-[4.5rem]' : 'lg:ms-64'
  const CollapseIcon = dir === 'rtl' ? (collapsed ? ChevronLeft : ChevronRight) : (collapsed ? ChevronRight : ChevronLeft)

  const sidebar = (
    <>
      <div className={`p-3 border-b border-white/10 flex items-center gap-2 ${collapsed && !mobileOpen ? 'justify-center' : 'gap-3'}`}>
        <img
          src="/gobus_logo.jpg"
          alt="GoBus"
          className={`rounded-full object-cover bg-white ring-2 ring-white/20 shrink-0 ${collapsed && !mobileOpen ? 'h-9 w-9' : 'h-10 w-10'}`}
        />
        {showLabels && (
          <div className="min-w-0 flex-1">
            <div className="font-bold text-sm truncate">GoBus Admin</div>
            <div className="text-xs opacity-75 truncate">{t.nav.adminSubtitle}</div>
          </div>
        )}
        <button
          type="button"
          className={`hidden lg:flex p-1.5 rounded-lg hover:bg-white/10 text-white/80 shrink-0 ${showLabels ? '' : ''}`}
          onClick={() => setCollapsed((c) => !c)}
          title={collapsed ? t.nav.expandSidebar : t.nav.collapseSidebar}
        >
          <CollapseIcon size={18} />
        </button>
        <button type="button" className="ms-auto lg:hidden text-white/80 shrink-0" onClick={() => setMobileOpen(false)}>
          <X size={20} />
        </button>
      </div>
      <nav className="flex-1 p-2 space-y-1 overflow-y-auto">
        {navItems.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            title={collapsed && !mobileOpen ? label : undefined}
            onClick={() => setMobileOpen(false)}
            className={({ isActive }) =>
              `flex items-center rounded-lg text-sm transition-colors ${
                collapsed && !mobileOpen ? 'justify-center px-2 py-2.5' : 'gap-3 px-3 py-2.5'
              } ${isActive ? 'bg-white/15 font-semibold' : 'hover:bg-white/10 opacity-90'}`
            }
          >
            <Icon size={18} className="shrink-0" />
            {showLabels && <span className="truncate">{label}</span>}
          </NavLink>
        ))}
      </nav>
      <div className="p-2 border-t border-white/10">
        <button
          type="button"
          onClick={logout}
          title={collapsed && !mobileOpen ? t.common.logout : undefined}
          className={`w-full flex items-center rounded-lg text-sm hover:bg-white/10 transition-colors ${
            collapsed && !mobileOpen ? 'justify-center px-2 py-2' : 'gap-2 px-3 py-2'
          }`}
        >
          <LogOut size={16} className="shrink-0" />
          {showLabels && <span>{t.common.logout}</span>}
        </button>
      </div>
    </>
  )

  return (
    <div className="min-h-screen flex flex-col lg:flex-row">
      {mobileOpen && (
        <button type="button" className="fixed inset-0 bg-black/40 z-40 lg:hidden" aria-label="Close menu" onClick={() => setMobileOpen(false)} />
      )}

      <aside
        className={`fixed inset-y-0 start-0 z-50 w-72 shrink-0 flex flex-col h-screen transform transition-all duration-200 ${sidebarWidth} ${
          mobileOpen
            ? 'translate-x-0'
            : dir === 'rtl'
              ? 'translate-x-full lg:translate-x-0'
              : '-translate-x-full lg:translate-x-0'
        }`}
        style={{ background: 'var(--color-brand-primary)', color: 'var(--color-text-inverse)' }}
      >
        {sidebar}
      </aside>

      <main className={`flex-1 min-w-0 flex flex-col ${mainOffset} min-h-screen transition-all duration-200`}>
        <header className="bg-white border-b px-4 lg:px-6 py-3.5 flex items-center justify-between gap-4 sticky top-0 z-30">
          <div className="flex items-center gap-3">
            <button type="button" className="lg:hidden p-2 rounded-lg hover:bg-[var(--color-surface-muted)]" onClick={() => setMobileOpen(true)}>
              <Menu size={20} />
            </button>
            <div>
              <h1 className="text-base lg:text-lg font-bold" style={{ color: 'var(--color-brand-primary)' }}>
                GoBus Chatbot
              </h1>
              <p className="text-xs text-[var(--color-text-muted)] hidden sm:block">{t.nav.headerSubtitle}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Link to="/chat" className="btn-accent text-sm flex items-center gap-2 px-3 py-2">
              <MessageSquare size={16} />
              <span className="hidden sm:inline">{t.nav.tryChat}</span>
            </Link>
            <LanguageToggle />
          </div>
        </header>
        <div className="p-4 lg:p-6 flex-1">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
