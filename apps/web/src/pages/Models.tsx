import { useEffect, useState } from 'react'
import { listModels, loadModel, unloadModel, routeModel } from '../api/client'
import type { ModelStatus, RouteResult } from '../api/client'
import { S, Badge, Spinner, ErrorBanner, SectionHeader, EmptyState } from '../components/ui'
import { Play, Square, Zap } from 'lucide-react'

const CAPABILITIES = ['reasoning', 'text', 'coding', 'vision', 'document_understanding', 'summarisation', 'tool_generation', 'analysis']

export default function Models() {
  const [models, setModels] = useState<ModelStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string>('')
  const [error, setError] = useState('')
  const [capability, setCapability] = useState('reasoning')
  const [routeResult, setRouteResult] = useState<RouteResult | null>(null)
  const [routeError, setRouteError] = useState('')

  const reload = async () => {
    try {
      setModels(await listModels())
      setError('')
    } catch {
      setError('Failed to load models')
    }
  }

  useEffect(() => {
    reload().finally(() => setLoading(false))
  }, [])

  const handleLoad = async (id: string) => {
    setBusy(id)
    try { await loadModel(id); await reload() }
    catch (e: any) { setError(e?.response?.data?.detail ?? 'Load failed') }
    finally { setBusy('') }
  }

  const handleUnload = async (id: string) => {
    setBusy(id)
    try { await unloadModel(id); await reload() }
    catch (e: any) { setError(e?.response?.data?.detail ?? 'Unload failed') }
    finally { setBusy('') }
  }

  const handleRoute = async () => {
    setRouteError('')
    setRouteResult(null)
    try {
      setRouteResult(await routeModel(capability))
    } catch (e: any) {
      setRouteError(e?.response?.data?.detail ?? 'Routing failed')
    }
  }

  return (
    <div>
      <SectionHeader title="Models" subtitle="Manage local model residency and routing" />

      {error && <ErrorBanner message={error} />}

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}><Spinner size={28} /></div>
      ) : (
        <>
          {/* Model list */}
          <div style={S.card}>
            {models.length === 0 ? (
              <EmptyState message="No models configured. Add entries to configs/config.yaml." />
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    {['Model', 'Name', 'Status', 'VRAM', 'Capabilities', 'Actions'].map(h => (
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
                  {models.map(m => (
                    <tr key={m.model_id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                      <td style={{ padding: '10px 12px', fontFamily: 'monospace', fontSize: 13 }}>{m.model_id}</td>
                      <td style={{ padding: '10px 12px', fontSize: 13, color: 'var(--color-muted)' }}>{m.model_name}</td>
                      <td style={{ padding: '10px 12px' }}><Badge label={m.status} /></td>
                      <td style={{ padding: '10px 12px', fontSize: 13, color: 'var(--color-muted)' }}>{m.vram_limit_mb.toLocaleString()} MB</td>
                      <td style={{ padding: '10px 12px', fontSize: 12, color: 'var(--color-muted)', maxWidth: 220 }}>
                        {m.capabilities.join(', ')}
                      </td>
                      <td style={{ padding: '10px 12px' }}>
                        <div style={{ display: 'flex', gap: 8 }}>
                          {!m.is_loaded ? (
                            <button
                              style={{ ...S.btn, padding: '6px 12px', fontSize: 12 }}
                              onClick={() => handleLoad(m.model_id)}
                              disabled={busy === m.model_id}
                            >
                              {busy === m.model_id ? <Spinner size={12} /> : <Play size={12} />} Load
                            </button>
                          ) : (
                            <button
                              style={{ ...S.btnGhost, padding: '6px 12px', fontSize: 12 }}
                              onClick={() => handleUnload(m.model_id)}
                              disabled={busy === m.model_id}
                            >
                              {busy === m.model_id ? <Spinner size={12} /> : <Square size={12} />} Unload
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Router tester */}
          <div style={{ marginTop: 28 }}>
            <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 14, color: 'var(--color-text)' }}>
              Route Tester
            </h3>
            <div style={{ ...S.card, display: 'flex', gap: 12, alignItems: 'flex-end' }}>
              <div style={{ flex: 1 }}>
                <label style={S.label}>Required Capability</label>
                <select
                  value={capability}
                  onChange={e => setCapability(e.target.value)}
                  style={{ ...S.input, cursor: 'pointer' }}
                >
                  {CAPABILITIES.map(c => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>
              <button style={S.btn} onClick={handleRoute}>
                <Zap size={14} /> Find Best Model
              </button>
            </div>

            {routeError && <ErrorBanner message={routeError} />}

            {routeResult && (
              <div style={{ ...S.card, marginTop: 12 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 16 }}>
                  {[
                    ['Model ID',       routeResult.model_id],
                    ['Model Name',     routeResult.model_name],
                    ['Already Loaded', routeResult.already_loaded ? 'Yes' : 'No'],
                    ['Selection Reason', routeResult.reason],
                  ].map(([label, value]) => (
                    <div key={label as string}>
                      <div style={S.label}>{label}</div>
                      <div style={{ fontFamily: 'monospace', fontSize: 13, color: 'var(--color-text)' }}>{value}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
