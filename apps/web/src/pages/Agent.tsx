import { useState } from 'react'
import { runAgent } from '../api/client'
import type { AgentRunResult } from '../api/client'
import { S, Spinner, ErrorBanner, SectionHeader, Badge } from '../components/ui'
import { BotMessageSquare, Wrench, AlertTriangle } from 'lucide-react'

const CAPABILITIES = ['reasoning', 'text', 'coding', 'vision', 'document_understanding', 'summarisation', 'analysis']
const ROLES = ['viewer', 'operator', 'admin']

export default function Agent() {
  const [task, setTask] = useState('')
  const [capability, setCapability] = useState('reasoning')
  const [role, setRole] = useState('operator')
  const [maxTools, setMaxTools] = useState(5)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<AgentRunResult | null>(null)
  const [error, setError] = useState('')

  const handleRun = async () => {
    if (!task.trim()) return
    setRunning(true)
    setError('')
    setResult(null)
    try {
      setResult(await runAgent({ task: task.trim(), capability, user_roles: [role], max_tool_calls: maxTools }))
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Agent run failed')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div>
      <SectionHeader title="Agent" subtitle="Run a controlled reasoning task with evidence grounding" />

      {error && <ErrorBanner message={error} />}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.8fr', gap: 24, alignItems: 'start' }}>

        {/* ── Config panel ── */}
        <div style={S.card}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-text)', marginBottom: 16 }}>
            Task Configuration
          </h3>

          <div style={{ marginBottom: 14 }}>
            <label style={S.label}>Task</label>
            <textarea
              value={task}
              onChange={e => setTask(e.target.value)}
              placeholder="Describe the task to perform using internal knowledge…"
              rows={6}
              style={{ ...S.input, resize: 'vertical', fontFamily: 'inherit', lineHeight: 1.6 }}
            />
          </div>

          <div style={{ marginBottom: 14 }}>
            <label style={S.label}>Capability</label>
            <select value={capability} onChange={e => setCapability(e.target.value)} style={{ ...S.input, cursor: 'pointer' }}>
              {CAPABILITIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          <div style={{ marginBottom: 14 }}>
            <label style={S.label}>User Role</label>
            <select value={role} onChange={e => setRole(e.target.value)} style={{ ...S.input, cursor: 'pointer' }}>
              {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>

          <div style={{ marginBottom: 20 }}>
            <label style={S.label}>Max Tool Calls</label>
            <input
              type="number" min={0} max={10}
              value={maxTools}
              onChange={e => setMaxTools(Number(e.target.value))}
              style={S.input}
            />
          </div>

          <button
            style={{ ...S.btn, width: '100%', justifyContent: 'center' }}
            onClick={handleRun}
            disabled={!task.trim() || running}
          >
            {running ? <Spinner size={14} /> : <BotMessageSquare size={14} />}
            {running ? 'Running…' : 'Run Agent'}
          </button>
        </div>

        {/* ── Results panel ── */}
        <div>
          {running && (
            <div style={{ ...S.card, display: 'flex', alignItems: 'center', gap: 14 }}>
              <Spinner size={20} />
              <span style={{ color: 'var(--color-muted)', fontSize: 13 }}>
                Agent is reasoning over your knowledge base…
              </span>
            </div>
          )}

          {result && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {/* Status */}
              <div style={S.card}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                  <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-text)' }}>Result</span>
                  <Badge label={result.status} />
                </div>

                {result.status === 'fail_closed' && (
                  <div style={{
                    display: 'flex', gap: 10, padding: '12px 14px',
                    background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.25)',
                    borderRadius: 8, marginBottom: 14,
                  }}>
                    <AlertTriangle size={16} color="#f59e0b" style={{ flexShrink: 0, marginTop: 2 }} />
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: '#f59e0b', marginBottom: 4 }}>Fail-Closed</div>
                      <div style={{ fontSize: 13, color: 'var(--color-muted)', lineHeight: 1.5 }}>{result.error}</div>
                    </div>
                  </div>
                )}

                {result.answer && (
                  <div>
                    <div style={S.label}>Answer</div>
                    <div style={{
                      background: 'var(--color-surface2)',
                      border: '1px solid var(--color-border)',
                      borderRadius: 8, padding: 14,
                      fontSize: 14, lineHeight: 1.7,
                      color: 'var(--color-text)',
                      whiteSpace: 'pre-wrap',
                    }}>
                      {result.answer}
                    </div>
                  </div>
                )}

                <div style={{ marginTop: 14, display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
                  {[
                    ['Request ID', result.request_id ?? '—'],
                    ['Evidence Used', result.evidence_count],
                    ['Tool Calls', result.tool_calls.length],
                  ].map(([l, v]) => (
                    <div key={l as string}>
                      <div style={S.label}>{l}</div>
                      <div style={{ fontSize: 13, fontFamily: 'monospace', color: 'var(--color-text)' }}>{v}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Tool calls */}
              {result.tool_calls.length > 0 && (
                <div style={S.card}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                    <Wrench size={14} color="var(--color-muted)" />
                    <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-text)' }}>
                      Tool Calls ({result.tool_calls.length})
                    </span>
                  </div>
                  {result.tool_calls.map((tc, i) => (
                    <div key={i} style={{
                      background: 'var(--color-surface2)',
                      border: '1px solid var(--color-border)',
                      borderRadius: 8, padding: 12, marginBottom: 10,
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                        <code style={{ fontSize: 12, color: 'var(--color-accent-hover)' }}>{tc.tool_id}</code>
                        <Badge label={tc.success ? 'success' : 'failed'} />
                      </div>
                      {tc.output && (
                        <pre style={{
                          fontSize: 12, margin: 0, padding: '8px 12px',
                          background: 'var(--color-bg)', borderRadius: 6,
                          color: 'var(--color-text)', overflowX: 'auto',
                          fontFamily: 'monospace', lineHeight: 1.5,
                        }}>
                          {JSON.stringify(tc.output, null, 2)}
                        </pre>
                      )}
                      {tc.error && (
                        <div style={{ fontSize: 12, color: '#ef4444', marginTop: 6 }}>{tc.error}</div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {!running && !result && (
            <div style={{ ...S.card, textAlign: 'center', padding: '48px 24px' }}>
              <BotMessageSquare size={36} color="var(--color-muted)" style={{ margin: '0 auto 14px' }} />
              <div style={{ fontSize: 14, color: 'var(--color-muted)', lineHeight: 1.7 }}>
                Configure a task and click <strong>Run Agent</strong>.<br />
                The agent will retrieve evidence, select a model, and reason over your knowledge base.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
