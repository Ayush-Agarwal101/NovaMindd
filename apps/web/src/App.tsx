import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Models from './pages/Models'
import Knowledge from './pages/Knowledge'
import Agent from './pages/Agent'
import Artifacts from './pages/Artifacts'
import Admin from './pages/Admin'
import {
  LayoutDashboard,
  Cpu,
  BookOpen,
  BotMessageSquare,
  FileDown,
  ShieldCheck,
} from 'lucide-react'

const NAV = [
  { to: '/',          label: 'Dashboard',  Icon: LayoutDashboard },
  { to: '/models',    label: 'Models',     Icon: Cpu },
  { to: '/knowledge', label: 'Knowledge',  Icon: BookOpen },
  { to: '/agent',     label: 'Agent',      Icon: BotMessageSquare },
  { to: '/artifacts', label: 'Artifacts',  Icon: FileDown },
  { to: '/admin',     label: 'Admin',      Icon: ShieldCheck },
]

function Sidebar() {
  return (
    <aside
      style={{
        width: 220,
        minWidth: 220,
        background: 'var(--color-surface)',
        borderRight: '1px solid var(--color-border)',
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        position: 'sticky',
        top: 0,
      }}
    >
      {/* Logo */}
      <div
        style={{
          padding: '20px 20px 16px',
          borderBottom: '1px solid var(--color-border)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              background: 'var(--color-accent)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <ShieldCheck size={18} color="#fff" />
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--color-text)', letterSpacing: '-0.3px' }}>
              NovaMindd
            </div>
            <div style={{ fontSize: 11, color: 'var(--color-muted)' }}>Sovereign AI</div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav style={{ padding: '12px 10px', flex: 1 }}>
        {NAV.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '9px 12px',
              borderRadius: 8,
              textDecoration: 'none',
              fontSize: 13.5,
              fontWeight: isActive ? 600 : 400,
              color: isActive ? '#fff' : 'var(--color-muted)',
              background: isActive ? 'var(--color-accent)' : 'transparent',
              marginBottom: 2,
              transition: 'all 0.15s',
            })}
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div
        style={{
          padding: '12px 16px',
          borderTop: '1px solid var(--color-border)',
          fontSize: 11,
          color: 'var(--color-muted)',
        }}
      >
        v0.1.0 · Local-first
      </div>
    </aside>
  )
}

function Header({ title }: { title: string }) {
  return (
    <header
      style={{
        height: 56,
        borderBottom: '1px solid var(--color-border)',
        display: 'flex',
        alignItems: 'center',
        padding: '0 24px',
        background: 'var(--color-surface)',
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}
    >
      <h1 style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-text)' }}>{title}</h1>
    </header>
  )
}

const PAGE_TITLES: Record<string, string> = {
  '/':          'Dashboard',
  '/models':    'Models',
  '/knowledge': 'Knowledge Base',
  '/agent':     'Agent',
  '/artifacts': 'Artifacts',
  '/admin':     'Admin',
}

function Main() {
  // Derive title from path
  const path = window.location.pathname
  const title = PAGE_TITLES[path] ?? 'NovaMindd'

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <Header title={title} />
      <div style={{ flex: 1, overflow: 'auto', padding: 24 }}>
        <Routes>
          <Route path="/"          element={<Dashboard />} />
          <Route path="/models"    element={<Models />} />
          <Route path="/knowledge" element={<Knowledge />} />
          <Route path="/agent"     element={<Agent />} />
          <Route path="/artifacts" element={<Artifacts />} />
          <Route path="/admin"     element={<Admin />} />
          <Route path="*"          element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
        <Sidebar />
        <Main />
      </div>
    </BrowserRouter>
  )
}
