import { useEffect, useRef, useState } from 'react'
import { ingestDocument, runAgent } from '../api/client'
import type { IngestResult } from '../api/client'
import { S, Spinner, ErrorBanner } from '../components/ui'
import { Upload, Send, FileText, X, RotateCcw } from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────────────

interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  text: string
  evidence?: number   // evidence_count from agent
  error?: boolean
}

let _msgId = 0
function nextId() { return ++_msgId }

// ── Sub-components ────────────────────────────────────────────────────────────

function UploadZone({
  file,
  ingesting,
  ingestResult,
  ingestError,
  onPickFile,
  onIngest,
  onReset,
  fileRef,
}: {
  file: File | null
  ingesting: boolean
  ingestResult: IngestResult | null
  ingestError: string
  onPickFile: () => void
  onIngest: () => void
  onReset: () => void
  fileRef: React.RefObject<HTMLInputElement>
}) {
  const done = !!ingestResult

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 16 }}>
      {/* Drop / file zone */}
      <div
        onClick={done ? undefined : onPickFile}
        style={{
          border: `2px dashed ${done ? 'var(--color-success)' : file ? 'var(--color-accent)' : 'var(--color-border)'}`,
          borderRadius: 10,
          padding: '28px 20px',
          textAlign: 'center',
          cursor: done ? 'default' : 'pointer',
          transition: 'border-color 0.15s',
          flexShrink: 0,
        }}
      >
        <Upload size={28} color={done ? 'var(--color-success)' : 'var(--color-muted)'} style={{ marginBottom: 8 }} />
        {file ? (
          <div>
            <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--color-text)' }}>{file.name}</div>
            <div style={{ fontSize: 12, color: 'var(--color-muted)', marginTop: 4 }}>
              {(file.size / 1024).toFixed(1)} KB
            </div>
          </div>
        ) : (
          <div style={{ fontSize: 13, color: 'var(--color-muted)' }}>
            Click to select a file<br />
            <span style={{ fontSize: 11 }}>PDF, TXT, MD supported</span>
          </div>
        )}
      </div>

      {!done && (
        <button
          style={{ ...S.btn, width: '100%', justifyContent: 'center' }}
          onClick={onIngest}
          disabled={!file || ingesting}
        >
          {ingesting ? <Spinner size={14} /> : <Upload size={14} />}
          {ingesting ? 'Ingesting…' : 'Ingest Document'}
        </button>
      )}

      {ingestError && <ErrorBanner message={ingestError} />}

      {done && ingestResult && (
        <div style={{
          background: 'rgba(16,185,129,0.08)',
          border: '1px solid rgba(16,185,129,0.25)',
          borderRadius: 8,
          padding: '12px 14px',
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-success)', marginBottom: 10 }}>
            ✓ Document ingested
          </div>
          {[
            ['Document ID', ingestResult.document_id],
            ['Chunks', String(ingestResult.chunks_created)],
            ['OCR pages', ingestResult.ocr_needed_pages.length > 0 ? ingestResult.ocr_needed_pages.join(', ') : 'None'],
          ].map(([l, v]) => (
            <div key={l} style={{ marginBottom: 6 }}>
              <div style={{ fontSize: 11, color: 'var(--color-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{l}</div>
              <div style={{ fontSize: 12.5, fontFamily: 'monospace', color: 'var(--color-text)', marginTop: 2, wordBreak: 'break-all' }}>{v}</div>
            </div>
          ))}
        </div>
      )}

      {done && (
        <button
          style={{ ...S.btnGhost, width: '100%', justifyContent: 'center', marginTop: 'auto' }}
          onClick={onReset}
        >
          <RotateCcw size={13} />
          Upload another document
        </button>
      )}

      {/* Tips */}
      <div style={{
        marginTop: done ? 0 : 'auto',
        padding: '12px 14px',
        background: 'var(--color-surface2)',
        borderRadius: 8,
        border: '1px solid var(--color-border)',
      }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--color-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
          Tips
        </div>
        {[
          'Ask questions grounded in the document',
          'Request summaries, key points, or clauses',
          'Ctrl+Enter to send',
        ].map(t => (
          <div key={t} style={{ fontSize: 12, color: 'var(--color-muted)', marginBottom: 4, paddingLeft: 8, borderLeft: '2px solid var(--color-border)' }}>
            {t}
          </div>
        ))}
      </div>
    </div>
  )
}

function ChatPane({
  messages,
  thinking,
  disabled,
  docName,
  onSend,
  onClear,
}: {
  messages: ChatMessage[]
  thinking: boolean
  disabled: boolean
  docName: string | null
  onSend: (text: string) => void
  onClear: () => void
}) {
  const [draft, setDraft] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, thinking])

  const submit = () => {
    const t = draft.trim()
    if (!t || thinking || disabled) return
    setDraft('')
    onSend(t)
    setTimeout(() => textareaRef.current?.focus(), 50)
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      background: 'var(--color-surface)',
      border: '1px solid var(--color-border)',
      borderRadius: 10,
      overflow: 'hidden',
    }}>
      {/* Toolbar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '10px 16px',
        borderBottom: '1px solid var(--color-border)',
        flexShrink: 0,
        background: 'var(--color-surface2)',
      }}>
        <FileText size={14} color="var(--color-accent)" />
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {docName ?? 'No document loaded'}
        </span>
        {messages.length > 0 && (
          <button
            onClick={onClear}
            title="Clear chat"
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-muted)', padding: 4, display: 'flex', alignItems: 'center' }}
          >
            <X size={14} />
          </button>
        )}
      </div>

      {/* Message list */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 16px 8px' }}>
        {!docName && (
          <div style={{ textAlign: 'center', paddingTop: 60, color: 'var(--color-muted)', fontSize: 13 }}>
            Upload and ingest a document to start chatting
          </div>
        )}

        {docName && messages.length === 0 && (
          <div style={{ textAlign: 'center', paddingTop: 60, color: 'var(--color-muted)', fontSize: 13 }}>
            Ask anything about <span style={{ color: 'var(--color-accent-hover)', fontWeight: 600 }}>{docName}</span>
          </div>
        )}

        {messages.map(msg => (
          <div
            key={msg.id}
            style={{
              display: 'flex',
              flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
              gap: 10,
              marginBottom: 14,
            }}
          >
            {/* Avatar */}
            <div style={{
              flexShrink: 0,
              width: 28,
              height: 28,
              borderRadius: '50%',
              background: msg.role === 'user' ? 'var(--color-accent)' : 'var(--color-surface2)',
              border: '1px solid var(--color-border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 11,
              fontWeight: 700,
              color: msg.role === 'user' ? '#fff' : 'var(--color-muted)',
            }}>
              {msg.role === 'user' ? 'U' : 'AI'}
            </div>

            {/* Bubble */}
            <div style={{
              maxWidth: '72%',
              background: msg.role === 'user' ? 'var(--color-accent)' : 'var(--color-surface2)',
              border: `1px solid ${msg.error ? 'rgba(239,68,68,0.4)' : 'var(--color-border)'}`,
              borderRadius: msg.role === 'user' ? '12px 4px 12px 12px' : '4px 12px 12px 12px',
              padding: '10px 14px',
            }}>
              <div style={{
                fontSize: 13.5,
                lineHeight: 1.65,
                color: msg.error ? '#ef4444' : msg.role === 'user' ? '#fff' : 'var(--color-text)',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}>
                {msg.text}
              </div>
              {msg.role === 'assistant' && !msg.error && msg.evidence !== undefined && msg.evidence > 0 && (
                <div style={{ fontSize: 11, color: 'var(--color-muted)', marginTop: 6 }}>
                  {msg.evidence} evidence chunk{msg.evidence !== 1 ? 's' : ''} used
                </div>
              )}
            </div>
          </div>
        ))}

        {thinking && (
          <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
            <div style={{
              width: 28, height: 28, borderRadius: '50%',
              background: 'var(--color-surface2)', border: '1px solid var(--color-border)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 11, fontWeight: 700, color: 'var(--color-muted)', flexShrink: 0,
            }}>AI</div>
            <div style={{
              background: 'var(--color-surface2)', border: '1px solid var(--color-border)',
              borderRadius: '4px 12px 12px 12px', padding: '10px 14px',
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <Spinner size={13} />
              <span style={{ fontSize: 13, color: 'var(--color-muted)' }}>Thinking…</span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div style={{
        borderTop: '1px solid var(--color-border)',
        padding: '12px 14px',
        background: 'var(--color-surface2)',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end' }}>
          <textarea
            ref={textareaRef}
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); submit() }
            }}
            disabled={disabled || thinking}
            placeholder={disabled ? 'Ingest a document first…' : 'Ask about this document…'}
            rows={2}
            style={{
              ...S.input,
              resize: 'none',
              fontFamily: 'inherit',
              lineHeight: 1.5,
              opacity: disabled ? 0.5 : 1,
            }}
          />
          <button
            onClick={submit}
            disabled={!draft.trim() || thinking || disabled}
            style={{
              ...S.btn,
              flexShrink: 0,
              padding: '10px 14px',
              opacity: (!draft.trim() || thinking || disabled) ? 0.5 : 1,
            }}
          >
            <Send size={15} />
          </button>
        </div>
        <div style={{ fontSize: 11, color: 'var(--color-muted)', marginTop: 6 }}>
          Ctrl+Enter to send · Answers are grounded in the ingested document
        </div>
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Knowledge() {
  const [file, setFile] = useState<File | null>(null)
  const [ingesting, setIngesting] = useState(false)
  const [ingestResult, setIngestResult] = useState<IngestResult | null>(null)
  const [ingestError, setIngestError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [thinking, setThinking] = useState(false)

  const docName = ingestResult ? (file?.name ?? 'document') : null

  const handlePickFile = () => fileRef.current?.click()

  // Sync actual file from the hidden input
  const handleFileChange = (picked: File) => setFile(picked)

  const handleIngest = async () => {
    if (!file) return
    setIngesting(true)
    setIngestError('')
    setIngestResult(null)
    try {
      setIngestResult(await ingestDocument(file))
    } catch (e: any) {
      setIngestError(e?.response?.data?.detail ?? 'Ingestion failed')
    } finally {
      setIngesting(false)
    }
  }

  const handleReset = () => {
    setFile(null)
    setIngestResult(null)
    setIngestError('')
    setMessages([])
    if (fileRef.current) fileRef.current.value = ''
  }

  const handleSend = async (text: string) => {
    const userMsg: ChatMessage = { id: nextId(), role: 'user', text }
    setMessages(prev => [...prev, userMsg])
    setThinking(true)
    try {
      const result = await runAgent({
        task: text,
        capability: 'document_understanding',
        user_id: 'web-user',
        user_roles: ['operator'],
        max_tool_calls: 3,
      })
      const aiMsg: ChatMessage = {
        id: nextId(),
        role: 'assistant',
        text: result.answer ?? '(No answer returned)',
        evidence: result.evidence_count,
        error: result.status === 'failed' || !!result.error,
      }
      setMessages(prev => [...prev, aiMsg])
    } catch (e: any) {
      setMessages(prev => [...prev, {
        id: nextId(),
        role: 'assistant',
        text: e?.response?.data?.detail ?? 'Request failed. Is the agent service running?',
        error: true,
      }])
    } finally {
      setThinking(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 56px)', overflow: 'hidden' }}>
      {/* Title row */}
      <div style={{ marginBottom: 16, flexShrink: 0 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--color-text)', marginBottom: 2 }}>Knowledge Base</h2>
        <p style={{ fontSize: 13, color: 'var(--color-muted)' }}>Upload a document, then chat with it — grounded, private, local</p>
      </div>

      {/* Two-column Codex layout */}
      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '300px 1fr', gap: 20, overflow: 'hidden' }}>
        {/* Left: upload panel */}
        <div style={{ overflow: 'auto' }}>
          <UploadZone
            file={file}
            ingesting={ingesting}
            ingestResult={ingestResult}
            ingestError={ingestError}
            onPickFile={handlePickFile}
            onIngest={handleIngest}
            onReset={handleReset}
            fileRef={fileRef as React.RefObject<HTMLInputElement>}
          />
          {/* Hidden input wired to state */}
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.txt,.md"
            style={{ display: 'none' }}
            onChange={e => { const f = e.target.files?.[0]; if (f) handleFileChange(f) }}
          />
        </div>

        {/* Right: chat pane */}
        <ChatPane
          messages={messages}
          thinking={thinking}
          disabled={!ingestResult}
          docName={docName}
          onSend={handleSend}
          onClear={() => setMessages([])}
        />
      </div>
    </div>
  )
}
