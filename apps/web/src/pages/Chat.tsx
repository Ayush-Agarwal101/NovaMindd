import { useEffect, useRef, useState } from 'react'
import { ingestDocument, listModels, runAgent } from '../api/client'
import type { IngestResult, ModelStatus } from '../api/client'
import { S, Spinner } from '../components/ui'
import { Plus, Send, X, FileText, ChevronDown, Paperclip, Upload } from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────────────

interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  text: string
  attachedDoc?: string   // filename shown in user bubble
  evidence?: number
  error?: boolean
}

interface AttachedDoc {
  file: File
  result: IngestResult
}

let _id = 0
const uid = () => ++_id

// ── Capability options ────────────────────────────────────────────────────────

const CAPS = [
  { value: 'reasoning',             label: 'Reasoning' },
  { value: 'text',                  label: 'Text' },
  { value: 'coding',                label: 'Coding' },
  { value: 'analysis',              label: 'Analysis' },
  { value: 'summarisation',         label: 'Summarise' },
  { value: 'document_understanding',label: 'Document Q&A' },
]

// ── Small helpers ─────────────────────────────────────────────────────────────

function Select({
  value,
  onChange,
  options,
  style,
}: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
  style?: React.CSSProperties
}) {
  return (
    <div style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', ...style }}>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{
          background: 'var(--color-surface2)',
          border: '1px solid var(--color-border)',
          borderRadius: 7,
          color: 'var(--color-text)',
          fontSize: 12.5,
          fontWeight: 500,
          padding: '5px 28px 5px 10px',
          appearance: 'none',
          cursor: 'pointer',
          outline: 'none',
        }}
      >
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <ChevronDown size={11} color="var(--color-muted)" style={{ position: 'absolute', right: 8, pointerEvents: 'none' }} />
    </div>
  )
}

// ── Attach popover ─────────────────────────────────────────────────────────────

function AttachPopover({
  onClose,
  onAttached,
}: {
  onClose: () => void
  onAttached: (doc: AttachedDoc) => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [state, setState] = useState<'idle' | 'ingesting' | 'done' | 'error'>('idle')
  const [errMsg, setErrMsg] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const pickFile = () => fileRef.current?.click()

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const f = e.dataTransfer.files[0]
    if (f) setFile(f)
  }

  const handleIngest = async () => {
    if (!file) return
    setState('ingesting')
    setErrMsg('')
    try {
      const result = await ingestDocument(file)
      setState('done')
      onAttached({ file, result })
    } catch (e: any) {
      setErrMsg(e?.response?.data?.detail ?? 'Ingestion failed')
      setState('error')
    }
  }

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{ position: 'fixed', inset: 0, zIndex: 40 }}
      />

      {/* Popover card */}
      <div style={{
        position: 'absolute',
        bottom: 'calc(100% + 10px)',
        left: 0,
        zIndex: 50,
        width: 300,
        background: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        borderRadius: 10,
        boxShadow: '0 8px 32px rgba(0,0,0,0.45)',
        overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '10px 14px',
          borderBottom: '1px solid var(--color-border)',
          background: 'var(--color-surface2)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <Paperclip size={13} color="var(--color-accent)" />
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text)' }}>Attach Document</span>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-muted)', display: 'flex', alignItems: 'center' }}>
            <X size={14} />
          </button>
        </div>

        <div style={{ padding: 14 }}>
          {state === 'done' ? (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 10,
              background: 'rgba(16,185,129,0.08)',
              border: '1px solid rgba(16,185,129,0.25)',
              borderRadius: 8, padding: '10px 12px',
            }}>
              <FileText size={14} color="var(--color-success)" />
              <div>
                <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--color-success)' }}>Attached!</div>
                <div style={{ fontSize: 11.5, color: 'var(--color-muted)', marginTop: 2 }}>{file?.name}</div>
              </div>
            </div>
          ) : (
            <>
              {/* Drop zone */}
              <div
                onClick={pickFile}
                onDragOver={e => e.preventDefault()}
                onDrop={handleDrop}
                style={{
                  border: `2px dashed ${file ? 'var(--color-accent)' : 'var(--color-border)'}`,
                  borderRadius: 8,
                  padding: '18px 12px',
                  textAlign: 'center',
                  cursor: 'pointer',
                  marginBottom: 12,
                  transition: 'border-color 0.15s',
                }}
              >
                <Upload size={22} color={file ? 'var(--color-accent)' : 'var(--color-muted)'} style={{ marginBottom: 6 }} />
                {file ? (
                  <>
                    <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--color-text)' }}>{file.name}</div>
                    <div style={{ fontSize: 11, color: 'var(--color-muted)', marginTop: 3 }}>{(file.size / 1024).toFixed(1)} KB</div>
                  </>
                ) : (
                  <div style={{ fontSize: 12, color: 'var(--color-muted)' }}>
                    Click or drag a file here<br />
                    <span style={{ fontSize: 11 }}>PDF · TXT · MD</span>
                  </div>
                )}
              </div>

              <input
                ref={fileRef}
                type="file"
                accept=".pdf,.txt,.md"
                style={{ display: 'none' }}
                onChange={e => setFile(e.target.files?.[0] ?? null)}
              />

              {state === 'error' && (
                <div style={{
                  fontSize: 12, color: 'var(--color-danger)',
                  background: 'rgba(239,68,68,0.08)',
                  border: '1px solid rgba(239,68,68,0.25)',
                  borderRadius: 6, padding: '8px 10px', marginBottom: 10,
                }}>
                  {errMsg}
                </div>
              )}

              <button
                style={{ ...S.btn, width: '100%', justifyContent: 'center', fontSize: 13 }}
                disabled={!file || state === 'ingesting'}
                onClick={handleIngest}
              >
                {state === 'ingesting' ? <Spinner size={13} /> : <Upload size={13} />}
                {state === 'ingesting' ? 'Ingesting…' : 'Ingest & Attach'}
              </button>
            </>
          )}
        </div>
      </div>
    </>
  )
}

// ── Message bubble ────────────────────────────────────────────────────────────

function Bubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user'
  return (
    <div style={{
      display: 'flex',
      flexDirection: isUser ? 'row-reverse' : 'row',
      gap: 10,
      marginBottom: 16,
      alignItems: 'flex-start',
    }}>
      {/* Avatar */}
      <div style={{
        flexShrink: 0, width: 30, height: 30, borderRadius: '50%',
        background: isUser ? 'var(--color-accent)' : 'var(--color-surface2)',
        border: '1px solid var(--color-border)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 11, fontWeight: 700,
        color: isUser ? '#fff' : 'var(--color-muted)',
      }}>
        {isUser ? 'U' : 'AI'}
      </div>

      <div style={{ maxWidth: '74%', display: 'flex', flexDirection: 'column', gap: 5, alignItems: isUser ? 'flex-end' : 'flex-start' }}>
        {/* Attached doc pill (user messages) */}
        {msg.attachedDoc && (
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 5,
            background: 'rgba(99,102,241,0.12)',
            border: '1px solid rgba(99,102,241,0.3)',
            borderRadius: 20, padding: '3px 10px',
            fontSize: 11, color: 'var(--color-accent-hover)',
          }}>
            <Paperclip size={10} />
            {msg.attachedDoc}
          </div>
        )}

        {/* Bubble */}
        <div style={{
          background: isUser ? 'var(--color-accent)' : 'var(--color-surface2)',
          border: `1px solid ${msg.error ? 'rgba(239,68,68,0.4)' : 'var(--color-border)'}`,
          borderRadius: isUser ? '14px 4px 14px 14px' : '4px 14px 14px 14px',
          padding: '10px 14px',
        }}>
          <div style={{
            fontSize: 13.5, lineHeight: 1.7,
            color: msg.error ? 'var(--color-danger)' : isUser ? '#fff' : 'var(--color-text)',
            whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          }}>
            {msg.text}
          </div>
          {!isUser && !msg.error && msg.evidence !== undefined && msg.evidence > 0 && (
            <div style={{ fontSize: 11, color: 'var(--color-muted)', marginTop: 5 }}>
              {msg.evidence} evidence chunk{msg.evidence !== 1 ? 's' : ''} used
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Thinking indicator ────────────────────────────────────────────────────────

function Thinking() {
  return (
    <div style={{ display: 'flex', gap: 10, marginBottom: 16, alignItems: 'flex-start' }}>
      <div style={{
        flexShrink: 0, width: 30, height: 30, borderRadius: '50%',
        background: 'var(--color-surface2)', border: '1px solid var(--color-border)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 11, fontWeight: 700, color: 'var(--color-muted)',
      }}>AI</div>
      <div style={{
        background: 'var(--color-surface2)', border: '1px solid var(--color-border)',
        borderRadius: '4px 14px 14px 14px', padding: '10px 14px',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <span style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          {[0, 1, 2].map(i => (
            <span key={i} style={{
              width: 6, height: 6, borderRadius: '50%',
              background: 'var(--color-muted)',
              animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
              display: 'inline-block',
            }} />
          ))}
        </span>
      </div>
    </div>
  )
}

// ── Main Chat page ────────────────────────────────────────────────────────────

export default function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState('')
  const [thinking, setThinking] = useState(false)

  // Model / capability
  const [models, setModels] = useState<ModelStatus[]>([])
  const [capability, setCapability] = useState('reasoning')

  // Attached document (set via popover)
  const [attachedDoc, setAttachedDoc] = useState<AttachedDoc | null>(null)
  const [showAttach, setShowAttach] = useState(false)

  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const attachAnchorRef = useRef<HTMLDivElement>(null)

  // Load models for display
  useEffect(() => {
    listModels().then(setModels).catch(() => {})
  }, [])

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, thinking])

  // Inject pulse keyframes once
  useEffect(() => {
    if (document.getElementById('chat-pulse-kf')) return
    const s = document.createElement('style')
    s.id = 'chat-pulse-kf'
    s.textContent = `@keyframes pulse { 0%,80%,100%{opacity:0.3;transform:scale(0.8)} 40%{opacity:1;transform:scale(1)} }`
    document.head.appendChild(s)
  }, [])

  const submit = async () => {
    const text = draft.trim()
    if (!text || thinking) return

    const docName = attachedDoc?.file.name ?? undefined

    const userMsg: ChatMessage = { id: uid(), role: 'user', text, attachedDoc: docName }
    setMessages(prev => [...prev, userMsg])
    setDraft('')
    // Clear attachment after first use
    const usedDoc = attachedDoc
    setAttachedDoc(null)
    setShowAttach(false)
    setThinking(true)

    try {
      // When a doc is attached, use document_understanding; otherwise use chosen capability
      const cap = usedDoc ? 'document_understanding' : capability
      const result = await runAgent({
        task: text,
        capability: cap,
        user_id: 'web-user',
        user_roles: ['operator'],
        max_tool_calls: 5,
      })
      setMessages(prev => [...prev, {
        id: uid(),
        role: 'assistant',
        text: result.answer ?? '(No answer returned)',
        evidence: result.evidence_count,
        error: result.status === 'failed' || !!result.error,
      }])
    } catch (e: any) {
      setMessages(prev => [...prev, {
        id: uid(),
        role: 'assistant',
        text: e?.response?.data?.detail ?? 'Request failed. Is the backend running?',
        error: true,
      }])
    } finally {
      setThinking(false)
      setTimeout(() => textareaRef.current?.focus(), 50)
    }
  }

  const loadedModel = models.find(m => m.is_loaded)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 56px)', overflow: 'hidden' }}>

      {/* ── Toolbar ── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '10px 20px',
        borderBottom: '1px solid var(--color-border)',
        background: 'var(--color-surface)',
        flexShrink: 0,
      }}>
        <span style={{ fontSize: 13, color: 'var(--color-muted)', fontWeight: 500 }}>Capability</span>
        <Select
          value={capability}
          onChange={setCapability}
          options={CAPS}
        />
        {loadedModel && (
          <>
            <div style={{ width: 1, height: 18, background: 'var(--color-border)' }} />
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--color-success)' }} />
              <span style={{ fontSize: 12, color: 'var(--color-muted)' }}>{loadedModel.model_name}</span>
            </div>
          </>
        )}
        <div style={{ flex: 1 }} />
        {messages.length > 0 && (
          <button
            onClick={() => setMessages([])}
            style={{ ...S.btnGhost, fontSize: 12, padding: '5px 12px' }}
          >
            Clear chat
          </button>
        )}
      </div>

      {/* ── Message area ── */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px 20px 16px' }}>

        {messages.length === 0 && (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
            height: '100%', gap: 16, color: 'var(--color-muted)',
          }}>
            <div style={{
              width: 52, height: 52, borderRadius: 14,
              background: 'var(--color-surface2)', border: '1px solid var(--color-border)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--color-text)', marginBottom: 6 }}>
                Start a conversation
              </div>
              <div style={{ fontSize: 13, lineHeight: 1.6, maxWidth: 360 }}>
                Type a message below. Use the{' '}
                <span style={{
                  display: 'inline-flex', alignItems: 'center', gap: 3,
                  background: 'var(--color-surface2)', border: '1px solid var(--color-border)',
                  borderRadius: 5, padding: '1px 7px', fontSize: 12, color: 'var(--color-text)',
                }}>
                  <Plus size={11} /> attach
                </span>{' '}
                button to add a document to the conversation.
              </div>
            </div>
          </div>
        )}

        {messages.map(msg => <Bubble key={msg.id} msg={msg} />)}
        {thinking && <Thinking />}
        <div ref={bottomRef} />
      </div>

      {/* ── Input area ── */}
      <div style={{
        borderTop: '1px solid var(--color-border)',
        background: 'var(--color-surface)',
        padding: '14px 20px 16px',
        flexShrink: 0,
      }}>
        {/* Attached doc pill */}
        {attachedDoc && (
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 7,
            background: 'rgba(99,102,241,0.1)',
            border: '1px solid rgba(99,102,241,0.3)',
            borderRadius: 20, padding: '4px 10px 4px 8px',
            fontSize: 12, color: 'var(--color-accent-hover)',
            marginBottom: 10,
          }}>
            <Paperclip size={11} />
            <span style={{ fontWeight: 500 }}>{attachedDoc.file.name}</span>
            <span style={{ color: 'var(--color-muted)', fontSize: 11 }}>
              · {attachedDoc.result.chunks_created} chunks
            </span>
            <button
              onClick={() => setAttachedDoc(null)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', color: 'var(--color-muted)', padding: 0, marginLeft: 2 }}
            >
              <X size={12} />
            </button>
          </div>
        )}

        {/* Input row */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          {/* + button (anchor for attach popover) */}
          <div ref={attachAnchorRef} style={{ position: 'relative', flexShrink: 0 }}>
            <button
              onClick={() => setShowAttach(v => !v)}
              title="Attach document"
              style={{
                width: 36, height: 36,
                background: showAttach ? 'var(--color-accent)' : 'var(--color-surface2)',
                border: `1px solid ${showAttach ? 'var(--color-accent)' : 'var(--color-border)'}`,
                borderRadius: 8,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                cursor: 'pointer',
                transition: 'all 0.15s',
                flexShrink: 0,
              }}
            >
              <Plus size={16} color={showAttach ? '#fff' : 'var(--color-muted)'} />
            </button>

            {showAttach && (
              <AttachPopover
                onClose={() => setShowAttach(false)}
                onAttached={doc => {
                  setAttachedDoc(doc)
                  setShowAttach(false)
                  // Switch to doc capability automatically
                  setCapability('document_understanding')
                  setTimeout(() => textareaRef.current?.focus(), 80)
                }}
              />
            )}
          </div>

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                submit()
              }
            }}
            placeholder="Message… (Enter to send, Shift+Enter for newline)"
            rows={1}
            style={{
              ...S.input,
              flex: 1,
              resize: 'none',
              fontFamily: 'inherit',
              lineHeight: 1.6,
              maxHeight: 140,
              overflowY: 'auto',
            }}
            onInput={e => {
              const el = e.currentTarget
              el.style.height = 'auto'
              el.style.height = Math.min(el.scrollHeight, 140) + 'px'
            }}
          />

          {/* Send */}
          <button
            onClick={submit}
            disabled={!draft.trim() || thinking}
            style={{
              ...S.btn,
              flexShrink: 0,
              width: 36, height: 36,
              padding: 0,
              justifyContent: 'center',
              opacity: (!draft.trim() || thinking) ? 0.45 : 1,
              transition: 'opacity 0.15s',
            }}
          >
            {thinking ? <Spinner size={14} /> : <Send size={15} />}
          </button>
        </div>

        <div style={{ fontSize: 11, color: 'var(--color-muted)', marginTop: 7, paddingLeft: 44 }}>
          Enter to send · Shift+Enter for newline · + to attach a document
        </div>
      </div>
    </div>
  )
}
