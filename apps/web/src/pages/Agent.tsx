import { useRef, useState } from 'react'
import { runAgent } from '../api/client'
import type { AgentRunResult } from '../api/client'
import { S, Spinner, ErrorBanner, SectionHeader, Badge } from '../components/ui'
import {
  BotMessageSquare, Paperclip, Wrench, AlertTriangle,
  X, FileText, Download, Cpu, ChevronRight,
} from 'lucide-react'

const CAPABILITIES = [
  'reasoning', 'text', 'coding', 'vision',
  'document_understanding', 'summarisation', 'analysis',
]
const ROLES = ['viewer', 'operator', 'admin']
const ACCEPTED_TYPES = '.pdf,.txt,.md,.csv,.png,.jpg,.jpeg,.tiff,.bmp,.webp'

// Capability → colour chip
const CAP_COLORS: Record<string, string> = {
  coding:               '#7c5cd8',
  vision:               '#0ea5e9',
  document_understanding: '#0ea5e9',
  reasoning:            '#3b82d4',
  text:                 '#3b82d4',
  summarisation:        '#10b981',
  analysis:             '#f59e0b',
}

function capColor(cap: string): string {
  return CAP_COLORS[cap] ?? '#57606a'
}

export default function Agent() {
  const [task, setTask]           = useState('')
  const [capability, setCapability] = useState('reasoning')
  const [role, setRole]           = useState('operator')
  const [maxTools, setMaxTools]   = useState(5)
  const [files, setFiles]         = useState<File[]>([])
  const [running, setRunning]     = useState(false)
  const [result, setResult]       = useState<AgentRunResult | null>(null)
  const [error, setError]         = useState('')
  const fileInputRef              = useRef<HTMLInputElement>(null)

  // ── File helpers ────────────────────────────────────────────────────
  const addFiles = (incoming: FileList | null) => {
    if (!incoming) return
    setFiles(prev => {
      const existing = new Set(prev.map(f => f.name + f.size))
      return [...prev, ...Array.from(incoming).filter(f => !existing.has(f.name + f.size))]
    })
  }
  const removeFile = (idx: number) => setFiles(prev => prev.filter((_, i) => i !== idx))
  const handleDrop = (e: React.DragEvent) => { e.preventDefault(); addFiles(e.dataTransfer.files) }

  // ── Run ─────────────────────────────────────────────────────────────
  const handleRun = async () => {
    if (!task.trim()) return
    setRunning(true); setError(''); setResult(null)
    try {
      setResult(await runAgent({ task: task.trim(), capability, user_roles: [role], max_tool_calls: maxTools, files }))
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Agent run failed')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div>
      <SectionHeader
        title="Agent"
        subtitle="Attach files and describe a task. The agent selects the best model for each reasoning step, switches models automatically, and saves the output as TXT and PDF."
      />

      {error && <ErrorBanner message={error} />}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.8fr', gap: 24, alignItems: 'start' }}>

        {/* ── Config panel ───────────────────────────────────────────── */}
        <div style={S.card}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-text)', marginBottom: 16 }}>
            Task Configuration
          </h3>

          {/* Task */}
          <div style={{ marginBottom: 14 }}>
            <label style={S.label}>Task</label>
            <textarea
              value={task}
              onChange={e => setTask(e.target.value)}
              placeholder="e.g. Generate an audit report from the maintenance logs attached, run the code and show the output, summarise the PDF…"
              rows={6}
              style={{ ...S.input, resize: 'vertical', fontFamily: 'inherit', lineHeight: 1.6 }}
            />
          </div>

          {/* File upload */}
          <div style={{ marginBottom: 14 }}>
            <label style={S.label}>
              Attach files <span style={{ color: 'var(--color-muted)', fontWeight: 400 }}>(optional)</span>
            </label>
            <div
              onDragOver={e => e.preventDefault()} onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              style={{
                border: '1.5px dashed var(--color-border)', borderRadius: 8,
                padding: '14px 16px', display: 'flex', alignItems: 'center',
                gap: 10, cursor: 'pointer', background: 'var(--color-surface2)',
              }}
            >
              <Paperclip size={16} color="var(--color-muted)" />
              <span style={{ fontSize: 13, color: 'var(--color-muted)' }}>
                Click or drag — PDF, images, text, CSV
              </span>
            </div>
            <input ref={fileInputRef} type="file" multiple accept={ACCEPTED_TYPES}
              style={{ display: 'none' }} onChange={e => addFiles(e.target.files)} />
            {files.length > 0 && (
              <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
                {files.map((f, i) => (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px',
                    background: 'var(--color-surface2)', border: '1px solid var(--color-border)',
                    borderRadius: 6,
                  }}>
                    <FileText size={13} color="var(--color-muted)" style={{ flexShrink: 0 }} />
                    <span style={{ fontSize: 12, color: 'var(--color-text)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {f.name}
                    </span>
                    <span style={{ fontSize: 11, color: 'var(--color-muted)', flexShrink: 0 }}>
                      {(f.size / 1024).toFixed(1)} KB
                    </span>
                    <button onClick={e => { e.stopPropagation(); removeFile(i) }}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2, display: 'flex', alignItems: 'center' }}>
                      <X size={12} color="var(--color-muted)" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Capability */}
          <div style={{ marginBottom: 14 }}>
            <label style={S.label}>Initial Capability</label>
            <select value={capability} onChange={e => setCapability(e.target.value)} style={{ ...S.input, cursor: 'pointer' }}>
              {CAPABILITIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          {/* Role */}
          <div style={{ marginBottom: 14 }}>
            <label style={S.label}>User Role</label>
            <select value={role} onChange={e => setRole(e.target.value)} style={{ ...S.input, cursor: 'pointer' }}>
              {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>

          {/* Max tools */}
          <div style={{ marginBottom: 20 }}>
            <label style={S.label}>Max Tool Calls</label>
            <input type="number" min={0} max={10} value={maxTools}
              onChange={e => setMaxTools(Number(e.target.value))} style={S.input} />
          </div>

          <button style={{ ...S.btn, width: '100%', justifyContent: 'center' }}
            onClick={handleRun} disabled={!task.trim() || running}>
            {running ? <Spinner size={14} /> : <BotMessageSquare size={14} />}
            {running ? 'Running…' : 'Run Agent'}
          </button>
        </div>

        {/* ── Results panel ──────────────────────────────────────────── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

          {running && (
            <div style={{ ...S.card, display: 'flex', alignItems: 'center', gap: 14 }}>
              <Spinner size={20} />
              <span style={{ color: 'var(--color-muted)', fontSize: 13 }}>
                {files.length > 0
                  ? `Ingesting ${files.length} file${files.length > 1 ? 's' : ''}, decomposing task, switching models…`
                  : 'Decomposing task, selecting models, reasoning…'}
              </span>
            </div>
          )}

          {result && (
            <>
              {/* ── Status + answer ── */}
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
                  <div style={{ marginBottom: 14 }}>
                    <div style={S.label}>Answer</div>
                    <div style={{
                      background: 'var(--color-surface2)', border: '1px solid var(--color-border)',
                      borderRadius: 8, padding: 14, fontSize: 14, lineHeight: 1.7,
                      color: 'var(--color-text)', whiteSpace: 'pre-wrap',
                    }}>
                      {result.answer}
                    </div>
                  </div>
                )}

                {/* Stats grid */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
                  {([
                    ['Request ID', result.request_id ?? '—'],
                    ['Evidence', result.evidence_count],
                    ['Tool Calls', result.tool_calls.length],
                    ['Files Ingested', result.files_ingested],
                  ] as [string, string | number][]).map(([l, v]) => (
                    <div key={l}>
                      <div style={S.label}>{l}</div>
                      <div style={{ fontSize: 13, fontFamily: 'monospace', color: 'var(--color-text)' }}>{v}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* ── Model switching steps ── */}
              {result.sub_steps && result.sub_steps.length > 0 && (
                <div style={S.card}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                    <Cpu size={14} color="var(--color-muted)" />
                    <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-text)' }}>
                      Model Steps ({result.sub_steps.length})
                    </span>
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
                    {result.sub_steps.map((s, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        {i > 0 && <ChevronRight size={14} color="var(--color-muted)" />}
                        <div style={{
                          padding: '5px 10px', borderRadius: 20,
                          background: `${capColor(s.capability)}18`,
                          border: `1px solid ${capColor(s.capability)}40`,
                        }}>
                          <div style={{ fontSize: 11, fontWeight: 600, color: capColor(s.capability) }}>
                            {s.capability}
                          </div>
                          <div style={{ fontSize: 10, color: 'var(--color-muted)', marginTop: 1 }}>
                            {s.model_name}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* ── Output file downloads ── */}
              {Object.keys(result.download_urls ?? {}).length > 0 && (
                <div style={S.card}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                    <Download size={14} color="var(--color-muted)" />
                    <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-text)' }}>
                      Download Output
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                    {Object.entries(result.download_urls).map(([fmt, url]) => (
                      <a
                        key={fmt}
                        href={url}
                        download
                        style={{
                          ...S.btn,
                          textDecoration: 'none',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 6,
                          padding: '7px 14px',
                        }}
                      >
                        <FileText size={13} />
                        Download .{fmt.toUpperCase()}
                      </a>
                    ))}
                  </div>
                </div>
              )}

              {/* ── Tool calls ── */}
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
                      background: 'var(--color-surface2)', border: '1px solid var(--color-border)',
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
            </>
          )}

          {!running && !result && (
            <div style={{ ...S.card, textAlign: 'center', padding: '48px 24px' }}>
              <BotMessageSquare size={36} color="var(--color-muted)" style={{ margin: '0 auto 14px' }} />
              <div style={{ fontSize: 14, color: 'var(--color-muted)', lineHeight: 1.8 }}>
                Configure a task and click <strong>Run Agent</strong>.<br />
                Attach <strong>PDFs, images, CSV, or text files</strong> — maintenance logs,
                audit records, code, reports — and the agent will:<br />
                <span style={{ color: 'var(--color-text)', fontWeight: 500 }}>
                  decompose the task → switch to the right model per step →
                  reason over your data → save output as TXT &amp; PDF
                </span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
