import { useEffect, useState } from 'react'
import { listTools, getPlatformConfig } from '../api/client'
import type { Tool, PlatformConfig } from '../api/client'
import { S, Badge, Spinner, ErrorBanner, SectionHeader, EmptyState } from '../components/ui'
import { ShieldCheck, Settings, Network, CheckCircle2, XCircle } from 'lucide-react'

export default function Admin() {
  const [tools, setTools] = useState<Tool[]>([])
  const [config, setConfig] = useState<PlatformConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [tab, setTab] = useState<'tools' | 'config' | 'policies'>('tools')

  useEffect(() => {
    const load = async () => {
      try {
        const [t, c] = await Promise.all([listTools(), getPlatformConfig()])
        setTools(t)
        setConfig(c)
      } catch {
        setError('Failed to load admin data')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const tabStyle = (active: boolean) => ({
    padding: '8px 18px',
    borderRadius: 7,
    border: 'none',
    background: active ? 'var(--color-accent)' : 'var(--color-surface2)',
    color: active ? '#fff' : 'var(--color-muted)',
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: active ? 600 : 400,
  } as React.CSSProperties)

  return (
    <div>
      <SectionHeader title="Admin" subtitle="Tool registry, platform configuration, and security policies" />

      {error && <ErrorBanner message={error} />}

      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        <button style={tabStyle(tab === 'tools')}   onClick={() => setTab('tools')}>Tools</button>
        <button style={tabStyle(tab === 'config')}  onClick={() => setTab('config')}>Configuration</button>
        <button style={tabStyle(tab === 'policies')} onClick={() => setTab('policies')}>Security Policies</button>
      </div>

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}><Spinner size={28} /></div>
      ) : (
        <>
          {/* ── Tools tab ── */}
          {tab === 'tools' && (
            <div style={S.card}>
              {tools.length === 0 ? <EmptyState message="No tools registered." /> : (
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      {['Tool ID', 'Name', 'Status', 'Permissions', 'Network', 'Approval'].map(h => (
                        <th key={h} style={{
                          textAlign: 'left', padding: '8px 12px', fontSize: 11,
                          fontWeight: 700, color: 'var(--color-muted)',
                          textTransform: 'uppercase', letterSpacing: '0.06em',
                          borderBottom: '1px solid var(--color-border)',
                        }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {tools.map(t => (
                      <tr key={t.tool_id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                        <td style={{ padding: '10px 12px', fontFamily: 'monospace', fontSize: 12, color: 'var(--color-accent-hover)' }}>
                          {t.tool_id}
                        </td>
                        <td style={{ padding: '10px 12px', fontSize: 13, color: 'var(--color-text)' }}>
                          {t.name}
                        </td>
                        <td style={{ padding: '10px 12px' }}>
                          <Badge label={t.status} />
                        </td>
                        <td style={{ padding: '10px 12px', fontSize: 12, color: 'var(--color-muted)' }}>
                          {t.required_permissions.join(', ')}
                        </td>
                        <td style={{ padding: '10px 12px' }}>
                          {t.requires_network
                            ? <XCircle size={15} color="#ef4444" />
                            : <CheckCircle2 size={15} color="#10b981" />}
                        </td>
                        <td style={{ padding: '10px 12px' }}>
                          {t.requires_human_approval
                            ? <Badge label="required" />
                            : <span style={{ fontSize: 12, color: 'var(--color-muted)' }}>—</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {/* ── Config tab ── */}
          {tab === 'config' && config && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              {Object.entries(config).map(([section, values]) => (
                <div key={section} style={S.card}>
                  <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--color-text)', marginBottom: 14, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    {section}
                  </h3>
                  {Object.entries(values as Record<string, unknown>).map(([k, v]) => (
                    <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--color-border)' }}>
                      <span style={{ fontSize: 12, color: 'var(--color-muted)' }}>{k}</span>
                      <span style={{ fontSize: 12, fontFamily: 'monospace', color: 'var(--color-text)' }}>
                        {Array.isArray(v) ? `[${v.join(', ')}]` : String(v)}
                      </span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}

          {/* ── Policies tab ── */}
          {tab === 'policies' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {[
                {
                  icon: <Network size={18} />,
                  title: 'Network Egress Policy',
                  items: [
                    { label: 'Default posture', value: 'DENY — no outbound connections from agent sandboxes' },
                    { label: 'Sandbox network mode', value: '--network=none (Docker)' },
                    { label: 'Explicit whitelist', value: 'Empty by default. Must be configured per tool.' },
                  ],
                },
                {
                  icon: <ShieldCheck size={18} />,
                  title: 'Sandbox Isolation',
                  items: [
                    { label: 'User', value: 'UID 65534 (nobody) — non-root enforced' },
                    { label: 'Filesystem', value: 'Read-only root, writable /workspace tmpfs only' },
                    { label: 'Capabilities', value: '--cap-drop ALL --security-opt no-new-privileges' },
                    { label: 'Resources', value: 'CPU quota + memory limit from execution policy' },
                  ],
                },
                {
                  icon: <Settings size={18} />,
                  title: 'Policy Engine',
                  items: [
                    { label: 'Default decision', value: 'DENY — first matching rule wins' },
                    { label: 'Decisions', value: 'ALLOW · DENY · ESCALATE (human approval)' },
                    { label: 'Roles', value: 'viewer · operator · admin' },
                    { label: 'Audit', value: 'Every decision logged to append-only JSONL audit trail' },
                  ],
                },
              ].map(section => (
                <div key={section.title} style={S.card}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16, color: 'var(--color-accent-hover)' }}>
                    {section.icon}
                    <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-text)', margin: 0 }}>{section.title}</h3>
                  </div>
                  {section.items.map(item => (
                    <div key={item.label} style={{ display: 'flex', gap: 16, padding: '8px 0', borderBottom: '1px solid var(--color-border)' }}>
                      <span style={{ fontSize: 12, color: 'var(--color-muted)', width: 180, flexShrink: 0 }}>{item.label}</span>
                      <span style={{ fontSize: 13, color: 'var(--color-text)', lineHeight: 1.5 }}>{item.value}</span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
