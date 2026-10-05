import { useEffect, useState } from 'react'
import { listModels } from '../api/client'
import type { ModelStatus } from '../api/client'
import { S, StatCard, Badge, Spinner, ErrorBanner, SectionHeader } from '../components/ui'
import { CheckCircle2, XCircle, Cpu, Database, Shield } from 'lucide-react'

export default function Dashboard() {
  const [models, setModels] = useState<ModelStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [isOnline, setIsOnline] = useState(navigator.onLine)

  useEffect(() => {
    const handleOnline = () => setIsOnline(true)
    const handleOffline = () => setIsOnline(false)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  useEffect(() => {
    const load = async () => {
      try {
        const m = await listModels()
        setModels(m)
      } catch {
        setError('Could not reach NovaMindd API. Is the server running?')
      } finally {
        setLoading(false)
      }
    }
    load()
    const t = setInterval(load, 10_000)
    return () => clearInterval(t)
  }, [])

  const loaded = models.filter(m => m.is_loaded).length
  const total = models.length

  return (
    <div>
      <SectionHeader
        title="Dashboard"
        subtitle="Platform status and resource overview"
      />

      {error && <ErrorBanner message={error} />}

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
          <Spinner size={32} />
        </div>
      ) : (
        <>
          {/* Status bar */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '12px 16px',
              borderRadius: 9,
              background: isOnline ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)',
              border: `1px solid ${isOnline ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'}`,
              marginBottom: 24,
              fontSize: 13.5,
              fontWeight: 600,
              color: isOnline ? '#10b981' : '#ef4444',
            }}
          >
            {isOnline ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
            {isOnline ? 'Internet connection is active' : 'No internet connection'}
          </div>

          {/* Stat grid */}
          <div style={S.grid3}>
            <StatCard
              label="Internet"
              value={isOnline ? 'Connected' : 'Disconnected'}
              sub="Current network status"
              accent={isOnline}
            />
            <StatCard
              label="Models Loaded"
              value={`${loaded} / ${total}`}
              sub="In VRAM right now"
            />
            <StatCard
              label="Total Models"
              value={total}
              sub="Registered in platform"
            />
          </div>

          {/* Model table */}
          {models.length > 0 && (
            <div style={{ marginTop: 28 }}>
              <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-text)', marginBottom: 12 }}>
                Model Registry
              </h3>
              <div style={S.card}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      {['Model ID', 'Name', 'Status', 'VRAM', 'Capabilities'].map(h => (
                        <th
                          key={h}
                          style={{
                            textAlign: 'left',
                            padding: '8px 12px',
                            fontSize: 11,
                            fontWeight: 700,
                            color: 'var(--color-muted)',
                            textTransform: 'uppercase',
                            letterSpacing: '0.06em',
                            borderBottom: '1px solid var(--color-border)',
                          }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {models.map(m => (
                      <tr key={m.model_id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                        <td style={{ padding: '10px 12px', fontSize: 13, fontFamily: 'monospace', color: 'var(--color-text)' }}>
                          {m.model_id}
                        </td>
                        <td style={{ padding: '10px 12px', fontSize: 13, color: 'var(--color-muted)' }}>
                          {m.model_name}
                        </td>
                        <td style={{ padding: '10px 12px' }}>
                          <Badge label={m.status} />
                        </td>
                        <td style={{ padding: '10px 12px', fontSize: 13, color: 'var(--color-muted)' }}>
                          {m.vram_limit_mb.toLocaleString()} MB
                        </td>
                        <td style={{ padding: '10px 12px', fontSize: 12, color: 'var(--color-muted)' }}>
                          {m.capabilities.join(', ')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Principles */}
          <div style={{ marginTop: 28 }}>
            <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-text)', marginBottom: 12 }}>
              Platform Principles
            </h3>
            <div style={S.grid3}>
              {[
                { icon: <Cpu size={18} />, title: 'Intelligence Is Not Authority', body: 'The model proposes. NovaMindd authorizes.' },
                { icon: <Database size={18} />, title: 'Evidence Before Confidence', body: 'Traceable evidence preferred over fluent unsupported output.' },
                { icon: <Shield size={18} />, title: 'Fail Closed', body: 'Insufficient evidence stops the workflow rather than producing bad output.' },
              ].map(p => (
                <div key={p.title} style={S.card}>
                  <div style={{ color: 'var(--color-accent)', marginBottom: 10 }}>{p.icon}</div>
                  <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--color-text)', marginBottom: 6 }}>{p.title}</div>
                  <div style={{ fontSize: 12.5, color: 'var(--color-muted)', lineHeight: 1.5 }}>{p.body}</div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
